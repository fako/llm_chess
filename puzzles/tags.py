"""
Tags describe what a puzzle is about, like "two bishops" or "smothered mate". They steer the LLM towards variety
and are never shown to users, because they would give the solution away.

Every tag has a check that runs on verified puzzles, so a tag stored on a puzzle is true, whatever the LLM claims.
Tags marked as heuristic recognise a pattern by its typical shape and can be wrong in unusual positions.
Requested tags are soft constraints: a sound puzzle without them is kept with the tags it does have.
"""
import random
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from typing import Callable, Iterator

import chess

from puzzles.engine import longest_replies
from puzzles.models import ChessPuzzle, ChessPuzzleCategory, Goal
from puzzles.solver import PIECE_VALUES, forces_mate


class Kind(Enum):
    MATERIAL = "material"  # what is on the board
    IDEA = "idea"  # what happens in the solution
    MATE = "mate"  # the shape of the final mate
    PIN = "pin"  # the kind of pin


@dataclass
class Puzzle:
    """
    A verified puzzle as the checks see it: the starting position and the solution tree of the solver.
    """
    board: chess.Board
    tree: dict
    category: ChessPuzzleCategory

    @property
    def color(self) -> chess.Color:
        return self.board.turn

    @property
    def key(self) -> chess.Move:
        return chess.Move.from_uci(next(iter(self.tree["moves"])))

    @cached_property
    def lines(self) -> list[list[chess.Move]]:
        """
        The lines users get to see: any move of the user, against the replies that hold out the longest.
        Lines alternate between moves of the solving side and replies.
        """
        lines = []

        def walk(node: dict, line: list[chess.Move]) -> None:
            for uci, move_node in node["moves"].items():
                move_line = line + [chess.Move.from_uci(uci)]
                if move_node["end"]:
                    lines.append(move_line)
                    continue
                for reply in longest_replies(move_node):
                    walk(move_node["replies"][reply], move_line + [chess.Move.from_uci(reply)])

        walk(self.tree, [])
        return lines

    def own_moves(self) -> Iterator[tuple[chess.Board, chess.Move]]:
        """
        Every move of the solving side in the lines, with the position before the move.
        """
        for line in self.lines:
            board = self.board.copy(stack=False)
            for index, move in enumerate(line):
                if index % 2 == 0:
                    yield board.copy(stack=False), move
                board.push(move)

    def final_positions(self) -> list[tuple[chess.Board, chess.Move]]:
        """
        The position after the last move of every line, with that move on the board's move stack.
        """
        finals = []
        for line in self.lines:
            board = self.board.copy(stack=False)
            for move in line:
                board.push(move)
            finals.append((board, line[-1]))
        return finals

    @property
    def pin(self) -> dict:
        return next(iter(self.tree["moves"].values()))["pin"]


@dataclass(frozen=True)
class Tag:
    slug: str
    kind: Kind
    instruction: str  # completes "Every puzzle in this batch must have these features:"
    check: Callable[[Puzzle], bool]
    goals: frozenset[Goal] = frozenset({Goal.MATE, Goal.PIN})
    min_depth: int = 1
    heuristic: bool = False

    def applies_to(self, category: ChessPuzzleCategory) -> bool:
        return category.goal in self.goals and category.depth >= self.min_depth


#####################
# Helpers
#####################


def officers(board: chess.Board, color: chess.Color) -> Counter:
    """
    The pieces of a side besides king and pawns, by type.
    """
    return Counter({piece_type: len(board.pieces(piece_type, color))
                    for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
                    if board.pieces(piece_type, color)})


def material(board: chess.Board, color: chess.Color) -> int:
    return sum(PIECE_VALUES[piece_type] * len(board.pieces(piece_type, color))
               for piece_type in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN))


def bishop_colors(board: chess.Board, color: chess.Color) -> set[bool]:
    return {bool(chess.BB_SQUARES[square] & chess.BB_LIGHT_SQUARES) for square in board.pieces(chess.BISHOP, color)}


def moved_squares(board: chess.Board, move: chess.Move) -> set[chess.Square]:
    """
    Where the moved pieces end up. Castling moves the rook too, while python-chess sees it as a king move.
    """
    if not board.is_castling(move):
        return {move.to_square}
    rank = chess.square_rank(move.to_square)
    rook_file = 3 if board.is_queenside_castling(move) else 5
    return {chess.square(6 if rook_file == 5 else 2, rank), chess.square(rook_file, rank)}


def is_discovered_check(board: chess.Board, move: chess.Move) -> bool:
    moved = moved_squares(board, move)
    board.push(move)
    try:
        return any(square not in moved for square in board.checkers())
    finally:
        board.pop()


def is_double_check(board: chess.Board, move: chess.Move) -> bool:
    board.push(move)
    try:
        return len(board.checkers()) > 1
    finally:
        board.pop()


def neighbours(square: chess.Square) -> list[chess.Square]:
    return list(chess.SquareSet(chess.BB_KING_ATTACKS[square]))


def mated_king(board: chess.Board) -> chess.Square:
    return board.king(board.turn)


def mating_piece(board: chess.Board, move: chess.Move) -> int:
    return board.piece_type_at(move.to_square)


def every_line_ends(predicate: Callable[[chess.Board, chess.Move], bool]) -> Callable[[Puzzle], bool]:
    """
    A check that holds when every line the user can get ends in a final position that matches the predicate.
    """
    def check(puzzle: Puzzle) -> bool:
        finals = puzzle.final_positions()
        return bool(finals) and all(predicate(board, move) for board, move in finals)
    return check


def some_own_move(predicate: Callable[[chess.Board, chess.Move], bool]) -> Callable[[Puzzle], bool]:
    def check(puzzle: Puzzle) -> bool:
        return any(predicate(board, move) for board, move in puzzle.own_moves())
    return check


#####################
# Material and board
#####################


def two_bishops(puzzle: Puzzle) -> bool:
    board = puzzle.board
    return len(bishop_colors(board, puzzle.color)) == 2 and len(bishop_colors(board, not puzzle.color)) < 2


def opposite_coloured_bishops(puzzle: Puzzle) -> bool:
    board = puzzle.board
    if len(board.pieces(chess.BISHOP, chess.WHITE)) != 1 or len(board.pieces(chess.BISHOP, chess.BLACK)) != 1:
        return False
    return bishop_colors(board, chess.WHITE) != bishop_colors(board, chess.BLACK)


def rook_endgame(puzzle: Puzzle) -> bool:
    board = puzzle.board
    sides = [officers(board, color) for color in chess.COLORS]
    return all(side and set(side) == {chess.ROOK} for side in sides)


def minor_pieces_only(puzzle: Puzzle) -> bool:
    board = puzzle.board
    types = set(officers(board, chess.WHITE)) | set(officers(board, chess.BLACK))
    return bool(types) and types <= {chess.KNIGHT, chess.BISHOP}


def queen_against_rook(puzzle: Puzzle) -> bool:
    board = puzzle.board
    return officers(board, puzzle.color) == Counter({chess.QUEEN: 1}) and \
        officers(board, not puzzle.color) == Counter({chess.ROOK: 1})


def knight_and_bishop(puzzle: Puzzle) -> bool:
    return officers(puzzle.board, puzzle.color) == Counter({chess.KNIGHT: 1, chess.BISHOP: 1})


def material_down(puzzle: Puzzle) -> bool:
    return material(puzzle.board, puzzle.color) <= material(puzzle.board, not puzzle.color) - 3


def few_pieces(puzzle: Puzzle) -> bool:
    return len(puzzle.board.piece_map()) <= 7


def crowded_board(puzzle: Puzzle) -> bool:
    return len(puzzle.board.piece_map()) >= 16


def king_in_centre(puzzle: Puzzle) -> bool:
    king = puzzle.board.king(not puzzle.color)
    home_ranks = (0, 1) if puzzle.color == chess.BLACK else (6, 7)
    return chess.square_file(king) in (3, 4) and chess.square_rank(king) in home_ranks


#####################
# Ideas
#####################


def quiet_key(puzzle: Puzzle) -> bool:
    board, key = puzzle.board, puzzle.key
    return not board.gives_check(key) and not board.is_capture(key)


def zugzwang(puzzle: Puzzle) -> bool:
    """
    A quiet key that threatens nothing: if the opponent could pass, there would be no mate. The opponent loses because
    every move of theirs makes things worse.
    """
    if not quiet_key(puzzle):
        return False
    board = puzzle.board.copy(stack=False)
    board.push(puzzle.key)
    board.push(chess.Move.null())
    return not forces_mate(board, puzzle.category.depth - 1)


def sacrifice(puzzle: Puzzle) -> bool:
    """
    The key offers material: the opponent can take the moved piece and comes out ahead on that exchange.
    """
    board, key = puzzle.board, puzzle.key
    gain = 1 if board.is_en_passant(key) else PIECE_VALUES.get(board.piece_type_at(key.to_square), 0)
    moved = board.piece_type_at(key.from_square) if not key.promotion else key.promotion
    if moved == chess.KING:
        return False
    after = board.copy(stack=False)
    after.push(key)
    for reply in after.legal_moves:
        if reply.to_square != key.to_square:
            continue
        capturer = after.piece_type_at(reply.from_square)
        defended = after.is_attacked_by(puzzle.color, key.to_square)
        loss = PIECE_VALUES[moved] - (PIECE_VALUES[capturer] if defended and capturer != chess.KING else 0)
        if loss - gain >= 2:
            return True
    return False


def only_checks(puzzle: Puzzle) -> bool:
    moves = list(puzzle.own_moves())
    return bool(moves) and all(board.gives_check(move) for board, move in moves)


def promotion(puzzle: Puzzle) -> bool:
    return any(move.promotion for _, move in puzzle.own_moves())


def underpromotion(puzzle: Puzzle) -> bool:
    return any(move.promotion and move.promotion != chess.QUEEN for _, move in puzzle.own_moves())


def king_joins(puzzle: Puzzle) -> bool:
    return any(board.piece_type_at(move.from_square) == chess.KING and not board.is_castling(move)
               for board, move in puzzle.own_moves())


def castling(puzzle: Puzzle) -> bool:
    return any(board.is_castling(move) for board, move in puzzle.own_moves())


#####################
# Mates, on the final position with the mated side to move
#####################


def back_rank_mate(board: chess.Board, move: chess.Move) -> bool:
    king = mated_king(board)
    back_rank = 0 if board.turn == chess.WHITE else 7
    forward = 1 if board.turn == chess.WHITE else -1
    if chess.square_rank(king) != back_rank or chess.square_rank(move.to_square) != back_rank:
        return False
    if mating_piece(board, move) not in (chess.ROOK, chess.QUEEN):
        return False
    in_front = [square for square in neighbours(king) if chess.square_rank(square) == back_rank + forward]
    return all(board.color_at(square) == board.turn for square in in_front)


def smothered_mate(board: chess.Board, move: chess.Move) -> bool:
    king = mated_king(board)
    return mating_piece(board, move) == chess.KNIGHT and \
        all(board.color_at(square) == board.turn for square in neighbours(king))


def anastasia_mate(board: chess.Board, move: chess.Move) -> bool:
    """
    A rook or queen mates along the edge file, while a knight takes the escape squares next to the defender's own
    piece that blocks the king in.
    """
    king = mated_king(board)
    file = chess.square_file(king)
    if file not in (0, 7) or chess.square_file(move.to_square) != file:
        return False
    if mating_piece(board, move) not in (chess.ROOK, chess.QUEEN):
        return False
    knights = board.pieces(chess.KNIGHT, not board.turn)
    inner = [square for square in neighbours(king) if chess.square_file(square) != file]
    blocked = any(board.color_at(square) == board.turn for square in inner)
    covered = any(board.attackers(not board.turn, square) & knights for square in inner)
    return blocked and covered


def boden_mate(board: chess.Board, move: chess.Move) -> bool:
    """
    Two bishops on crossing diagonals mate a king that is boxed in by its own pieces.
    """
    if mating_piece(board, move) != chess.BISHOP or len(board.pieces(chess.BISHOP, not board.turn)) < 2:
        return False
    bishops = board.pieces(chess.BISHOP, not board.turn)
    others_needed = False
    covering_bishops: set[chess.Square] = set()
    for square in neighbours(mated_king(board)):
        if board.color_at(square) == board.turn:
            continue
        attackers = board.attackers(not board.turn, square)
        if attackers & bishops:
            covering_bishops |= set(attackers & bishops)
        else:
            others_needed = True
    return not others_needed and bool(covering_bishops - {move.to_square})


def arabian_mate(board: chess.Board, move: chess.Move) -> bool:
    king = mated_king(board)
    if king not in (chess.A1, chess.H1, chess.A8, chess.H8) or mating_piece(board, move) != chess.ROOK:
        return False
    if move.to_square not in neighbours(king):
        return False
    knights = board.pieces(chess.KNIGHT, not board.turn)
    return bool(board.attackers(not board.turn, move.to_square) & knights)


def epaulette_mate(board: chess.Board, move: chess.Move) -> bool:
    """
    The queen mates a king whose squares to the left and right are taken by its own pieces, like epaulettes.
    """
    king = mated_king(board)
    file, rank = chess.square_file(king), chess.square_rank(king)
    if file in (0, 7) or mating_piece(board, move) != chess.QUEEN:
        return False
    sides = [chess.square(file - 1, rank), chess.square(file + 1, rank)]
    return all(board.color_at(square) == board.turn and board.piece_type_at(square) != chess.PAWN for square in sides)


def mate_by(piece_type: int) -> Callable[[chess.Board, chess.Move], bool]:
    return lambda board, move: mating_piece(board, move) == piece_type and not move.promotion


#####################
# Pins
#####################


def pin_against(piece_name: str) -> Callable[[Puzzle], bool]:
    return lambda puzzle: puzzle.pin["target_piece"] == piece_name


def _pinner_type(puzzle: Puzzle) -> int:
    board = puzzle.board.copy(stack=False)
    board.push(puzzle.key)
    return board.piece_type_at(chess.parse_square(puzzle.pin["pinner"]))


def pin_line(line: str) -> Callable[[Puzzle], bool]:
    def check(puzzle: Puzzle) -> bool:
        pinner = chess.parse_square(puzzle.pin["pinner"])
        target = chess.parse_square(puzzle.pin["target"])
        if chess.square_file(pinner) == chess.square_file(target):
            return line == "file"
        if chess.square_rank(pinner) == chess.square_rank(target):
            return line == "rank"
        return line == "diagonal"
    return check


#####################
# Registry
#####################


MATE = frozenset({Goal.MATE})
PIN = frozenset({Goal.PIN})

TAGS: dict[str, Tag] = {tag.slug: tag for tag in [
    # Material and board
    Tag("two-bishops", Kind.MATERIAL, "the solving side has both bishops (the bishop pair) and the opponent doesn't",
        two_bishops),
    Tag("opposite-coloured-bishops", Kind.MATERIAL,
        "both sides have exactly one bishop, and the bishops move on squares of different colours",
        opposite_coloured_bishops),
    Tag("rook-endgame", Kind.MATERIAL, "a rook endgame: besides kings and pawns both sides only have rooks",
        rook_endgame),
    Tag("minor-pieces-only", Kind.MATERIAL, "no queens or rooks on the board, only knights and bishops besides kings "
        "and pawns", minor_pieces_only),
    Tag("queen-against-rook", Kind.MATERIAL, "besides kings and pawns, the solving side only has a queen and the "
        "opponent only has a rook", queen_against_rook),
    Tag("knight-and-bishop", Kind.MATERIAL, "besides king and pawns, the solving side only has one knight and one "
        "bishop", knight_and_bishop),
    Tag("material-down", Kind.MATERIAL, "the solving side is at least 3 points of material behind (pawn 1, knight "
        "and bishop 3, rook 5, queen 9)", material_down),
    Tag("few-pieces", Kind.MATERIAL, "at most 7 pieces on the board in total, kings and pawns included", few_pieces),
    Tag("crowded-board", Kind.MATERIAL, "at least 16 pieces on the board in total, kings and pawns included, like in "
        "a middlegame", crowded_board),
    Tag("king-in-centre", Kind.MATERIAL, "the opponent's king hasn't castled and stands on the d or e file of its "
        "first two ranks", king_in_centre),
    # Ideas
    Tag("quiet-key", Kind.IDEA, "the first move is quiet: no check and no capture", quiet_key, MATE),
    Tag("zugzwang", Kind.IDEA, "the first move is quiet and threatens nothing, the opponent loses because any move "
        "they make allows mate (zugzwang)", zugzwang, MATE, min_depth=2),
    Tag("sacrifice", Kind.IDEA, "the first move sacrifices material: the opponent can take the moved piece",
        sacrifice, MATE, heuristic=True),
    Tag("only-checks", Kind.IDEA, "every move of the solving side gives check, like a king hunt", only_checks, MATE,
        min_depth=2),
    Tag("discovered-check", Kind.IDEA, "a move of the solving side gives a discovered check",
        some_own_move(is_discovered_check), MATE),
    Tag("double-check", Kind.IDEA, "a move of the solving side gives a double check", some_own_move(is_double_check),
        MATE),
    Tag("promotion", Kind.IDEA, "a pawn of the solving side promotes", promotion, MATE),
    Tag("underpromotion", Kind.IDEA, "a pawn of the solving side promotes to a knight, bishop or rook instead of a "
        "queen", underpromotion, MATE),
    Tag("king-joins", Kind.IDEA, "the king of the solving side makes a move that matters", king_joins, MATE,
        min_depth=2),
    Tag("castling", Kind.IDEA, "a move of the solving side is castling, so the FEN must allow it", castling),
    Tag("mate-by-knight", Kind.IDEA, "a knight delivers the mate", every_line_ends(mate_by(chess.KNIGHT)), MATE),
    Tag("mate-by-pawn", Kind.IDEA, "a pawn delivers the mate, without promoting", every_line_ends(mate_by(chess.PAWN)),
        MATE),
    # Mates
    Tag("back-rank", Kind.MATE, "a back rank mate: a rook or queen mates on the first rank of the opponent, whose "
        "own pawns block the king in", every_line_ends(back_rank_mate), MATE),
    Tag("smothered", Kind.MATE, "a smothered mate: a knight mates a king that is surrounded by its own pieces",
        every_line_ends(smothered_mate), MATE, heuristic=True),
    Tag("anastasia", Kind.MATE, "Anastasia's mate: a knight and a rook or queen trap the king on the edge of the "
        "board, against one of its own pieces", every_line_ends(anastasia_mate), MATE, heuristic=True),
    Tag("boden", Kind.MATE, "Boden's mate: two bishops on crossing diagonals mate a king blocked by its own pieces",
        every_line_ends(boden_mate), MATE, heuristic=True),
    Tag("arabian", Kind.MATE, "the Arabian mate: a rook next to the king in the corner, protected by a knight",
        every_line_ends(arabian_mate), MATE, heuristic=True),
    Tag("epaulette", Kind.MATE, "the epaulette mate: the queen mates a king whose squares to the left and right are "
        "taken by its own pieces", every_line_ends(epaulette_mate), MATE, heuristic=True),
    # Pins
    Tag("pin-against-king", Kind.PIN, "the pinned piece shields its king", pin_against("king"), PIN),
    Tag("pin-against-queen", Kind.PIN, "the pinned piece shields its queen", pin_against("queen"), PIN),
    Tag("pin-on-file", Kind.PIN, "the pin runs along a file", pin_line("file"), PIN),
    Tag("pin-on-rank", Kind.PIN, "the pin runs along a rank", pin_line("rank"), PIN),
    Tag("pin-on-diagonal", Kind.PIN, "the pin runs along a diagonal", pin_line("diagonal"), PIN),
    Tag("pinned-by-bishop", Kind.PIN, "a bishop pins", lambda puzzle: _pinner_type(puzzle) == chess.BISHOP, PIN),
    Tag("pinned-by-rook", Kind.PIN, "a rook pins", lambda puzzle: _pinner_type(puzzle) == chess.ROOK, PIN),
    Tag("pinned-by-queen", Kind.PIN, "a queen pins", lambda puzzle: _pinner_type(puzzle) == chess.QUEEN, PIN),
]}


def detect_tags(category: ChessPuzzleCategory, board: chess.Board, tree: dict) -> list[str]:
    """
    The tags that apply to a verified puzzle, in registry order.
    """
    puzzle = Puzzle(board=board.copy(stack=False), tree=tree, category=category)
    return [tag.slug for tag in TAGS.values() if tag.applies_to(category) and tag.check(puzzle)]


#####################
# Balancing
#####################


@dataclass
class Coverage:
    category: ChessPuzzleCategory
    tags: Counter = field(default_factory=Counter)
    perspectives: Counter = field(default_factory=Counter)
    total: int = 0

    @classmethod
    def of(cls, category: ChessPuzzleCategory) -> "Coverage":
        coverage = cls(category=category)
        for tags, perspective in ChessPuzzle.objects.filter(category=category).values_list("tags", "perspective"):
            coverage.tags.update(tags)
            coverage.perspectives[perspective] += 1
            coverage.total += 1
        return coverage

    def add(self, puzzle: ChessPuzzle) -> None:
        self.tags.update(puzzle.tags)
        self.perspectives[puzzle.perspective] += 1
        self.total += 1


def applicable_tags(category: ChessPuzzleCategory) -> list[Tag]:
    return [tag for tag in TAGS.values() if tag.applies_to(category)]


GROUPS = ({Kind.MATERIAL}, {Kind.IDEA, Kind.MATE, Kind.PIN})  # balancing picks a tag about the board and the solution


def balanced_tags(coverage: Coverage, fixed: list[Tag] | None = None, rng: random.Random = random) -> list[Tag]:
    """
    Completes the fixed tags with one tag about the material and one about the solution, when the fixed tags have none
    of that group yet. Tags the category has few puzzles of are much more likely to get picked.
    """
    picks = list(fixed or [])
    tags = applicable_tags(coverage.category)
    for kinds in GROUPS:
        if any(tag.kind in kinds for tag in picks):
            continue
        options = [tag for tag in tags if tag.kind in kinds]
        if options:
            weights = [1 / (1 + coverage.tags[tag.slug]) ** 2 for tag in options]
            picks.append(rng.choices(options, weights=weights)[0])
    return picks


def balanced_perspective(coverage: Coverage) -> str:
    return "black" if coverage.perspectives["black"] < coverage.perspectives["white"] else "white"


def parse_tags(category: ChessPuzzleCategory, slugs: list[str]) -> list[Tag]:
    unknown = [slug for slug in slugs if slug not in TAGS]
    if unknown:
        raise ValueError(f"Unknown tags: {', '.join(unknown)}")
    wrong = [slug for slug in slugs if not TAGS[slug].applies_to(category)]
    if wrong:
        raise ValueError(f"Tags that don't apply to {category.slug}: {', '.join(wrong)}")
    return [TAGS[slug] for slug in slugs]
