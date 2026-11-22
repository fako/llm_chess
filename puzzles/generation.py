"""
Generates puzzles with an LLM through Datagrowth.

The prompt for a kind of puzzle lives on its ChessPuzzleCategory. This module wraps that prompt in the generic output
contract (puzzles/prompts/puzzles/generate_puzzles.json.tpl), sends it to the LLM and verifies every proposal with the
solver. Only proposals the solver accepts become a ChessPuzzle, with a solution tree computed by the solver.
"""
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

import chess
from jinja2.sandbox import SandboxedEnvironment
from pydantic import BaseModel, ConfigDict, Field

from datagrowth.exceptions import DGHttpError40X, DGHttpError50X
from vendors.anthropic import AnthropicPromptResource, anthropic_llm_tag

from puzzles.models import ChessPuzzle, ChessPuzzleCategory, Goal, Perspective
from puzzles.solver import PuzzleAnalysis, analyse_mate_puzzle, analyse_pin_puzzle, build_pin_tree, build_solution_tree
from puzzles.tags import Coverage, Tag, balanced_perspective, balanced_tags, detect_tags


logger = logging.getLogger(__name__)


GENERATION_TEMPLATE = "puzzles/generate_puzzles.json.tpl"
MAX_BATCH_SIZE = 5
MAX_EXCLUDED_POSITIONS = 100
# Thinking counts towards the output tokens. On high effort mates in 2 and 3 easily think for more than 32k tokens.
MAX_TOKENS = 64_000


class PuzzleProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fen: str = Field(description="The puzzle position in Forsyth-Edwards Notation.")
    perspective: Literal["white", "black"] = Field(description="The side that solves the puzzle and moves first.")
    solution: list[list[str]] = Field(
        description="Main variations as lists of moves in standard algebraic notation (SAN), "
                    "starting with the first move of the solving side, e.g. [\"Qh6+\", \"Kg8\", \"Qg7#\"]."
    )
    title_en: str = Field(description="A short English title for the puzzle that doesn't give away the solution.")
    title_nl: str = Field(description="The same title in Dutch.")
    hint_en: str = Field(description="One English sentence nudging towards the idea, without naming the first move.")
    hint_nl: str = Field(description="The same hint in Dutch.")


class PuzzleProposals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    puzzles: list[PuzzleProposal]


@dataclass
class Rejection:
    fen: str
    reason: str


@dataclass
class GenerationReport:
    category: ChessPuzzleCategory
    requested: int
    model: str
    effort: str
    created: list[ChessPuzzle] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fatal: bool = False  # the API refused, for instance because credits ran out
    requests: int = 0
    tokens: dict[str, int] = field(default_factory=dict)
    requested_tags: Counter = field(default_factory=Counter)  # per requested tag: proposals verified with it asked
    matched_tags: Counter = field(default_factory=Counter)  # per requested tag: puzzles that actually have it

    def add_usage(self, usage: dict[str, int]) -> None:
        for key, value in usage.items():
            self.tokens[key] = self.tokens.get(key, 0) + value


def api_error_message(resource: AnthropicPromptResource) -> str:
    try:
        error = json.loads(resource.result.body)["error"]
        return f"{resource.status} {error['type']}: {error['message']}"
    except (AttributeError, TypeError, ValueError, KeyError):
        return f"{resource.status} {resource.result.errors if resource.result else 'no result'}"


def position_key(board: chess.Board) -> str:
    return board.epd()


def render_category_prompt(category: ChessPuzzleCategory, count: int) -> str:
    template = SandboxedEnvironment().from_string(category.prompt)
    return template.render(count=count, mate_in=category.mate_in)


def analyse_puzzle(category: ChessPuzzleCategory, board: chess.Board) -> PuzzleAnalysis:
    if category.goal == Goal.PIN:
        return analyse_pin_puzzle(board)
    return analyse_mate_puzzle(board, category.mate_in)


def build_tree(category: ChessPuzzleCategory, board: chess.Board) -> dict:
    if category.goal == Goal.PIN:
        return build_pin_tree(board)
    return build_solution_tree(board, category.mate_in)


def verify_proposal(category: ChessPuzzleCategory, proposal: PuzzleProposal) -> ChessPuzzle | Rejection:
    """
    Turns a proposal into an unsaved ChessPuzzle when the solver confirms it, or explains why it got rejected.
    """
    if category.goal == Goal.MATE and category.mate_in is None:
        raise ValueError(f"Category '{category.slug}' is a forced mate without a mate_in value")
    try:
        board = chess.Board(proposal.fen)
    except ValueError as error:
        return Rejection(proposal.fen, f"invalid FEN: {error}")
    color = chess.WHITE if proposal.perspective == Perspective.WHITE else chess.BLACK
    if board.turn != color:
        return Rejection(proposal.fen, f"perspective is {proposal.perspective}, but the other side is to move")
    position = position_key(board)
    if ChessPuzzle.objects.filter(position=position).exists():
        return Rejection(proposal.fen, "position already exists")
    analysis = analyse_puzzle(category, board)
    if not analysis.is_sound:
        return Rejection(proposal.fen, analysis.reason)

    # The position is sound, even when the LLM had the solution wrong. We keep track of whether it was right.
    llm_key = None
    if proposal.solution and proposal.solution[0]:
        try:
            llm_key = board.parse_san(proposal.solution[0][0]).uci()
        except ValueError:
            pass
    llm_was_right = llm_key in analysis.key_moves
    tree = build_tree(category, board)
    return ChessPuzzle(
        tags=detect_tags(category, board, tree),
        category=category,
        fen=board.fen(),
        position=position,
        perspective=proposal.perspective,
        solution=tree,
        title_en=proposal.title_en[:255],
        title_nl=proposal.title_nl[:255],
        hint_en=proposal.hint_en[:255] if llm_was_right else "",
        hint_nl=proposal.hint_nl[:255] if llm_was_right else "",
        generation={
            "proposal": proposal.model_dump(mode="json"),
            "llm_was_right": llm_was_right,
        },
    )


def manual_tags(tags: list[Tag] | None) -> list[str]:
    """
    How the tags picked by hand are stored on a puzzle, so a run can top up puzzles generated with the same tags.
    """
    return sorted(tag.slug for tag in tags or [])


def generate_puzzles(category: ChessPuzzleCategory | str, count: int, max_requests: int | None = None,
                     model: str | None = None, effort: str | None = None,
                     batch_size: int | None = None, tags: list[Tag] | None = None,
                     balance: bool = True) -> GenerationReport:
    """
    Generates count puzzles for a category, by asking the LLM for batches of proposals until enough of them are
    verified or max_requests is reached. Most LLM proposals don't survive verification, so batches are oversized.
    The model and effort default to those of the category.

    Every request asks for the given tags. With balance every request also gets a solving side and tags that the
    category has few puzzles of, for the groups of tags (material, solution) that the given tags leave open.
    Tags are soft: puzzles without them are kept with the tags they do have.
    """
    if isinstance(category, str):
        category = ChessPuzzleCategory.objects.get(slug=category)
    if max_requests is None:
        max_requests = max(3, count)
    model = model or category.model
    effort = effort or category.effort
    report = GenerationReport(category=category, requested=count, model=model, effort=effort)
    coverage = Coverage.of(category)

    while len(report.created) < count and report.requests < max_requests:
        size = batch_size or min(MAX_BATCH_SIZE, max(3, (count - len(report.created)) * 2))
        excluded_positions = list(
            ChessPuzzle.objects.filter(category=category)
            .order_by("-created_at")
            .values_list("fen", flat=True)[:MAX_EXCLUDED_POSITIONS]
        )
        request_tags = balanced_tags(coverage, fixed=tags) if balance else list(tags or [])
        perspective = balanced_perspective(coverage) if balance else None
        context = {
            "prompt": render_category_prompt(category, size),
            "count": size,
            "tags": [tag.instruction for tag in request_tags],
            "perspective": perspective,
            "excluded_positions": excluded_positions,
            "nonce": uuid4().hex,  # every request is a new request, instead of a cached earlier response
        }
        report.requests += 1
        resource = AnthropicPromptResource(llm=anthropic_llm_tag(model))
        try:
            resource = resource.extract(GENERATION_TEMPLATE, PuzzleProposals, context=context,
                                        options={"max_tokens": MAX_TOKENS, "effort": effort})
        except DGHttpError50X as error:
            report.errors.append(f"request {report.requests} failed: {api_error_message(error.resource)}")
            logger.warning(report.errors[-1])
            continue
        except DGHttpError40X as error:  # retrying won't help with problems like authentication or credits
            report.errors.append(f"request {report.requests} failed: {api_error_message(error.resource)}")
            logger.error(report.errors[-1])
            report.fatal = True
            break
        resource.close()
        if not resource.success:
            error = resource.result.errors if resource.result else "no result"
            report.errors.append(f"request {report.requests} failed with status {resource.status}: {error}")
            logger.warning(report.errors[-1])
            continue
        report.add_usage(resource.get_token_usage())
        _, proposals = resource.content
        for proposal in proposals.puzzles:
            if len(report.created) >= count:
                break
            result = verify_proposal(category, proposal)
            if isinstance(result, Rejection):
                report.rejected.append(result)
                continue
            result.model = model
            result.effort = effort
            result.generation["served_by"] = resource.served_by  # differs from model after a fallback
            result.generation["resource"] = str(resource.signature.hash) if resource.signature else None
            result.generation["requested_tags"] = [tag.slug for tag in request_tags]
            result.generation["manual_tags"] = manual_tags(tags)
            result.generation["requested_perspective"] = perspective
            result.save()
            report.created.append(result)
            coverage.add(result)
            for tag in request_tags:
                report.requested_tags[tag.slug] += 1
                report.matched_tags[tag.slug] += tag.slug in result.tags
    return report
