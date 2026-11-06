"""
Runs puzzles for users. The engine only knows verified solution trees (see solver.py) and user progress.
It doesn't know anything about how puzzles got generated.

An attempt is a line of UCI moves that alternates between moves of the user and replies of the opponent.
Users play their own moves on the board without any help, but pick the replies of the opponent from a list.
"""
from dataclasses import dataclass, field
from enum import Enum

import chess
from django.db.models import Q

from puzzles.models import ChessPuzzle, ChessPuzzleCategory, UserChessPuzzle
from puzzles.solver import BRANCH_SEPARATOR


MAX_HINT_LEVEL = 2  # 1 shows the piece to move, 2 shows the move itself


class Phase(Enum):
    MOVE = "move"
    REPLY = "reply"
    SOLVED = "solved"


class Outcome(Enum):
    CORRECT = "correct"
    MATE = "mate"
    WRONG = "wrong"
    ILLEGAL = "illegal"


@dataclass
class Reply:
    uci: str
    san: str
    is_completed: bool


@dataclass
class PuzzleState:
    progress: UserChessPuzzle
    board: chess.Board
    phase: Phase
    last_move: chess.Move | None
    replies: list[Reply] = field(default_factory=list)
    legal_moves: list[str] = field(default_factory=list)
    hint_squares: list[str] = field(default_factory=list)
    branch: str | None = None  # the branch that a solved attempt completed

    @property
    def puzzle(self) -> ChessPuzzle:
        return self.progress.puzzle

    @property
    def moves_left(self) -> int:
        mate_in = self.puzzle.category.mate_in or 0
        return mate_in - (len(self.progress.line) + 1) // 2


def _walk(puzzle: ChessPuzzle, line: list[str]) -> tuple[chess.Board, dict, Phase, chess.Move | None]:
    """
    Plays a line on the puzzle and returns the board, the current tree node, the phase and the last move.
    Raises KeyError when the line isn't part of the solution tree.
    """
    board = puzzle.board
    node = puzzle.solution
    phase = Phase.MOVE
    last_move = None
    for index, uci in enumerate(line):
        if phase == Phase.SOLVED:
            raise KeyError(uci)
        if index % 2 == 0:
            node = node["moves"][uci]
            phase = Phase.SOLVED if node["mate"] else Phase.REPLY
        else:
            node = node["replies"][uci]
            phase = Phase.MOVE
        last_move = chess.Move.from_uci(uci)
        board.push(last_move)
    return board, node, phase, last_move


def _branch_prefix(line: list[str]) -> str:
    return BRANCH_SEPARATOR.join(line[1::2])


def _is_branch_completed(progress: UserChessPuzzle, prefix: str) -> bool:
    completed = set(progress.completed_branches)
    branches = [
        branch for branch in progress.puzzle.branches
        if branch == prefix or branch.startswith(prefix + BRANCH_SEPARATOR)
    ]
    return bool(branches) and all(branch in completed for branch in branches)


def _hint_move(node: dict) -> chess.Move:
    return chess.Move.from_uci(sorted(node["moves"])[0])


def get_state(progress: UserChessPuzzle) -> PuzzleState:
    try:
        board, node, phase, last_move = _walk(progress.puzzle, progress.line)
    except KeyError:  # the solution changed since the attempt started, so we start over
        progress.line = []
        progress.hint_level = 0
        progress.save(update_fields=["line", "hint_level", "updated_at"])
        board, node, phase, last_move = _walk(progress.puzzle, progress.line)
    state = PuzzleState(progress=progress, board=board, phase=phase, last_move=last_move)
    if phase == Phase.MOVE:
        state.legal_moves = [move.uci() for move in board.legal_moves]
        if progress.hint_level:
            hint = _hint_move(node)
            state.hint_squares = [chess.square_name(hint.from_square)]
            if progress.hint_level >= 2:
                state.hint_squares.append(chess.square_name(hint.to_square))
    elif phase == Phase.REPLY:
        for uci, reply_node in node["replies"].items():
            prefix = _branch_prefix(progress.line + [uci])
            state.replies.append(Reply(uci=uci, san=reply_node["san"],
                                       is_completed=_is_branch_completed(progress, prefix)))
        state.replies.sort(key=lambda reply: (reply.is_completed, reply.san))
    else:
        state.branch = _branch_prefix(progress.line)
    return state


def play_move(progress: UserChessPuzzle, uci: str) -> Outcome:
    board, node, phase, _ = _walk(progress.puzzle, progress.line)
    if phase != Phase.MOVE:
        return Outcome.ILLEGAL
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return Outcome.ILLEGAL
    if move not in board.legal_moves:
        return Outcome.ILLEGAL
    if uci not in node["moves"]:
        progress.wrong_moves += 1
        progress.save(update_fields=["wrong_moves", "updated_at"])
        return Outcome.WRONG
    progress.line = progress.line + [uci]
    progress.hint_level = 0
    if not node["moves"][uci]["mate"]:
        progress.save(update_fields=["line", "hint_level", "updated_at"])
        return Outcome.CORRECT
    branch = _branch_prefix(progress.line)
    if branch not in progress.completed_branches:
        progress.completed_branches = progress.completed_branches + [branch]
    progress.save(update_fields=["line", "hint_level", "completed_branches", "updated_at"])
    return Outcome.MATE


def choose_reply(progress: UserChessPuzzle, uci: str) -> bool:
    _, node, phase, _ = _walk(progress.puzzle, progress.line)
    if phase != Phase.REPLY or uci not in node["replies"]:
        return False
    progress.line = progress.line + [uci]
    progress.save(update_fields=["line", "updated_at"])
    return True


def take_hint(progress: UserChessPuzzle) -> None:
    _, _, phase, _ = _walk(progress.puzzle, progress.line)
    if phase != Phase.MOVE or progress.hint_level >= MAX_HINT_LEVEL:
        return
    progress.hint_level += 1
    progress.hints_used += 1
    progress.save(update_fields=["hint_level", "hints_used", "updated_at"])


def restart(progress: UserChessPuzzle) -> None:
    progress.line = []
    progress.hint_level = 0
    progress.save(update_fields=["line", "hint_level", "updated_at"])


#####################
# Puzzle selection
#####################


def next_puzzle(user, category: ChessPuzzleCategory) -> ChessPuzzle | None:
    """
    Returns a puzzle the user didn't resolve any branches for yet, preferring puzzles that the user already started.
    """
    started = UserChessPuzzle.objects \
        .filter(user=user, puzzle__category=category, completed_branches=[]) \
        .order_by("-updated_at") \
        .select_related("puzzle") \
        .first()
    if started is not None:
        return started.puzzle
    resolved = UserChessPuzzle.objects \
        .filter(user=user, puzzle__category=category) \
        .filter(~Q(completed_branches=[])) \
        .values("puzzle_id")
    return ChessPuzzle.objects \
        .filter(category=category) \
        .exclude(id__in=resolved) \
        .order_by("?") \
        .first()


def puzzles_with_open_branches(user, category: ChessPuzzleCategory) -> list[UserChessPuzzle]:
    progresses = UserChessPuzzle.objects \
        .filter(user=user, puzzle__category=category) \
        .filter(~Q(completed_branches=[])) \
        .select_related("puzzle", "puzzle__category") \
        .order_by("puzzle__created_at")
    return [progress for progress in progresses if not progress.is_fully_solved]


def get_progress(user, puzzle: ChessPuzzle) -> UserChessPuzzle:
    progress, _ = UserChessPuzzle.objects.select_related("puzzle", "puzzle__category") \
        .get_or_create(user=user, puzzle=puzzle)
    return progress
