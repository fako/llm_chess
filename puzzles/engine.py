"""
Runs puzzles for users. The engine only knows verified solution trees (see solver.py) and user progress.
It doesn't know anything about how puzzles got generated.

An attempt is a line of UCI moves that alternates between moves of the user and replies of the opponent.
Users play their own moves on the board without any help. The engine replies for the opponent right away,
with a random pick among the replies that hold out the longest against best play.
"""
import random
from dataclasses import dataclass, field
from enum import Enum

import chess
from django.utils import timezone

from puzzles.models import ChessPuzzle, ChessPuzzleCategory, UserChessPuzzle


MAX_HINT_LEVEL = 2  # 1 shows the piece to move, 2 shows the move itself


class Phase(Enum):
    MOVE = "move"
    SOLVED = "solved"


class Outcome(Enum):
    CORRECT = "correct"
    SOLVED = "solved"
    WRONG = "wrong"
    ILLEGAL = "illegal"


@dataclass
class PuzzleState:
    progress: UserChessPuzzle
    board: chess.Board
    phase: Phase
    last_move: chess.Move | None
    moves_left: int = 0
    legal_moves: list[str] = field(default_factory=list)
    hint_squares: list[str] = field(default_factory=list)

    @property
    def puzzle(self) -> ChessPuzzle:
        return self.progress.puzzle

    @property
    def final_move(self) -> dict | None:
        """
        The tree node of the move that solved the puzzle, which describes a pin for pin puzzles.
        """
        if self.phase != Phase.SOLVED:
            return None
        node = self.puzzle.solution
        for index, uci in enumerate(self.progress.line):
            node = node["moves"][uci] if index % 2 == 0 else node["replies"][uci]
        return node


#####################
# Solution tree
#####################


def _move_distance(move_node: dict) -> int:
    if move_node["end"]:
        return 1
    return 1 + max(moves_to_solve(reply_node) for reply_node in move_node["replies"].values())


def moves_to_solve(node: dict) -> int:
    """
    The amount of moves the user needs from a user node, when both sides play their best.
    """
    return min(_move_distance(move_node) for move_node in node["moves"].values())


def longest_replies(move_node: dict) -> list[str]:
    """
    The replies to a move that hold out the longest against the fastest solution.
    """
    distances = {uci: moves_to_solve(reply_node) for uci, reply_node in move_node["replies"].items()}
    longest = max(distances.values())
    return sorted(uci for uci, distance in distances.items() if distance == longest)


def _walk(puzzle: ChessPuzzle, line: list[str]) -> tuple[chess.Board, dict, Phase, chess.Move | None]:
    """
    Plays a line on the puzzle and returns the board, the current tree node, the phase and the last move.
    Raises KeyError when the line isn't part of the solution tree or doesn't end with a position to play or a solve.
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
            phase = Phase.SOLVED if node["end"] else Phase.MOVE
        else:
            node = node["replies"][uci]
        last_move = chess.Move.from_uci(uci)
        board.push(last_move)
    if phase == Phase.MOVE and "moves" not in node:  # the line stops before the opponent replied
        raise KeyError(line[-1])
    return board, node, phase, last_move


def _hint_move(node: dict) -> chess.Move:
    fastest = min(node["moves"], key=lambda uci: (_move_distance(node["moves"][uci]), uci))
    return chess.Move.from_uci(fastest)


#####################
# Playing
#####################


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
        state.moves_left = moves_to_solve(node)
        state.legal_moves = [move.uci() for move in board.legal_moves]
        if progress.hint_level:
            hint = _hint_move(node)
            state.hint_squares = [chess.square_name(hint.from_square)]
            if progress.hint_level >= 2:
                state.hint_squares.append(chess.square_name(hint.to_square))
    return state


def play_move(progress: UserChessPuzzle, uci: str) -> Outcome:
    """
    Plays a move of the user. When the move is correct, but doesn't solve the puzzle yet, the opponent replies.
    """
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
    move_node = node["moves"][uci]
    progress.hint_level = 0
    if not move_node["end"]:
        progress.line = progress.line + [uci, random.choice(longest_replies(move_node))]
        progress.save(update_fields=["line", "hint_level", "updated_at"])
        return Outcome.CORRECT
    progress.line = progress.line + [uci]
    if progress.solved_at is None:
        progress.solved_at = timezone.now()
    progress.save(update_fields=["line", "hint_level", "solved_at", "updated_at"])
    return Outcome.SOLVED


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


def adjacent_puzzles(puzzle: ChessPuzzle) -> tuple[ChessPuzzle | None, ChessPuzzle | None]:
    """
    Returns the previous and next puzzle in the category of the given puzzle, in creation order.
    """
    siblings = ChessPuzzle.objects.filter(category_id=puzzle.category_id)
    previous = siblings.filter(pk__lt=puzzle.pk).order_by("-pk").first()
    following = siblings.filter(pk__gt=puzzle.pk).order_by("pk").first()
    return previous, following


def next_puzzle(user, category: ChessPuzzleCategory) -> ChessPuzzle | None:
    """
    Returns a puzzle the user didn't solve yet, preferring puzzles that the user already started.
    """
    started = UserChessPuzzle.objects \
        .filter(user=user, puzzle__category=category, solved_at__isnull=True) \
        .order_by("-updated_at") \
        .select_related("puzzle") \
        .first()
    if started is not None:
        return started.puzzle
    solved = UserChessPuzzle.objects \
        .filter(user=user, puzzle__category=category, solved_at__isnull=False) \
        .values("puzzle_id")
    return ChessPuzzle.objects \
        .filter(category=category) \
        .exclude(id__in=solved) \
        .order_by("?") \
        .first()


def get_progress(user, puzzle: ChessPuzzle) -> UserChessPuzzle:
    progress, _ = UserChessPuzzle.objects.select_related("puzzle", "puzzle__category") \
        .get_or_create(user=user, puzzle=puzzle)
    return progress
