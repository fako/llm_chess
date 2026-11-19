"""
Forced mate search on top of python-chess.

The LLM proposes puzzles, but it is this module that decides whether a proposal is a sound puzzle and that builds the
solution tree the play engine runs on. Nothing an LLM claims about a position ends up in front of a user unverified.

A solution tree alternates two kinds of nodes:

    user node:   {"moves": {<uci>: <move node>, ...}}                  every move that keeps a forced mate
    move node:   {"san": "Qh7+", "end": true}                          the move solves the puzzle
                 {"san": "Qh7+", "end": false, "replies": {<uci>: <user node + "san">, ...}}
                                                                       every legal defence of the opponent

A branch is the sequence of opponent replies along one line of the tree, joined with "/".
Completing a branch means solving the puzzle after the opponent defended along exactly that line.
Puzzles that are solved with a single move, like a mate in 1, have one empty branch.
"""
from dataclasses import dataclass

import chess


BRANCH_SEPARATOR = "/"


def _mates_in_one(board: chess.Board) -> list[chess.Move]:
    mates = []
    for move in board.legal_moves:
        if not board.gives_check(move):
            continue
        board.push(move)
        if board.is_checkmate():
            mates.append(move)
        board.pop()
    return mates


def forces_mate(board: chess.Board, depth: int) -> bool:
    """
    Returns whether the side to move can force mate within depth moves of its own.
    """
    if depth == 1:
        return bool(_mates_in_one(board))
    return any(_move_forces_mate(board, move, depth) for move in board.legal_moves)


def _move_forces_mate(board: chess.Board, move: chess.Move, depth: int) -> bool:
    board.push(move)
    try:
        if board.is_checkmate():
            return True
        if depth == 1 or board.is_game_over():  # stalemate and draws end the line without a mate
            return False
        return all(_reply_allows_mate(board, reply, depth - 1) for reply in list(board.legal_moves))
    finally:
        board.pop()


def _reply_allows_mate(board: chess.Board, reply: chess.Move, depth: int) -> bool:
    board.push(reply)
    try:
        return forces_mate(board, depth)
    finally:
        board.pop()


def mating_moves(board: chess.Board, depth: int) -> list[chess.Move]:
    """
    Returns all moves for the side to move that force mate within depth moves.
    """
    if depth == 1:
        return _mates_in_one(board)
    return [move for move in board.legal_moves if _move_forces_mate(board, move, depth)]


def build_solution_tree(board: chess.Board, depth: int) -> dict:
    """
    Builds a user node for a position where the side to move forces mate within depth moves.
    """
    moves = {}
    for move in mating_moves(board, depth):
        node: dict = {"san": board.san(move)}
        board.push(move)
        if board.is_checkmate():
            node["end"] = True
        else:
            node["end"] = False
            node["replies"] = {}
            for reply in list(board.legal_moves):
                reply_san = board.san(reply)
                board.push(reply)
                reply_node = build_solution_tree(board, depth - 1)
                reply_node["san"] = reply_san
                node["replies"][reply.uci()] = reply_node
                board.pop()
        board.pop()
        moves[move.uci()] = node
    return {"moves": moves}


def list_branches(tree: dict, path: tuple[str, ...] = tuple()) -> list[str]:
    """
    Lists every branch of a solution tree as a "/" joined sequence of opponent replies.
    Branches reached through different correct user moves are merged.
    """
    branches: set[str] = set()
    for node in tree["moves"].values():
        if node["end"]:
            branches.add(BRANCH_SEPARATOR.join(path))
            continue
        for reply, reply_node in node["replies"].items():
            branches.update(list_branches(reply_node, path + (reply,)))
    return sorted(branches)


@dataclass(frozen=True)
class PuzzleAnalysis:
    is_sound: bool
    reason: str
    key_moves: tuple[str, ...] = tuple()  # in UCI


def analyse_mate_puzzle(board: chess.Board, depth: int) -> PuzzleAnalysis:
    """
    Checks the classic composition rules for a "mate in depth" puzzle:
    the position is legal, there is no faster mate and exactly one first move (the key) forces mate in time.
    Alternative mating moves later in a line ("duals") are accepted, because users may play any of them.
    """
    if not board.is_valid():
        return PuzzleAnalysis(False, f"illegal position ({board.status()!r})")
    if board.is_game_over():
        return PuzzleAnalysis(False, "the game is already over")
    for shorter in range(1, depth):
        if forces_mate(board, shorter):
            return PuzzleAnalysis(False, f"there is already a mate in {shorter}")
    keys = mating_moves(board, depth)
    if not keys:
        return PuzzleAnalysis(False, f"there is no forced mate in {depth}")
    key_moves = tuple(move.uci() for move in keys)
    if len(keys) > 1:
        return PuzzleAnalysis(False, f"more than one first move works: {', '.join(board.san(m) for m in keys)}",
                            key_moves)
    return PuzzleAnalysis(True, "sound", key_moves)


#####################
# Pins
#####################


PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}


@dataclass(frozen=True)
class Pin:
    pinned: chess.Square
    pinner: chess.Square
    target: chess.Square  # the king or queen behind the pinned piece

    def describe(self, board: chess.Board) -> dict:
        return {
            "pinned": chess.square_name(self.pinned),
            "pinned_piece": chess.piece_name(board.piece_type_at(self.pinned)),
            "pinner": chess.square_name(self.pinner),
            "target": chess.square_name(self.target),
            "target_piece": chess.piece_name(board.piece_type_at(self.target)),
        }


def find_pins(board: chess.Board, color: chess.Color) -> set[Pin]:
    """
    Finds the pieces of the opponent that pieces of color pin against the king (absolute) or the queen (relative).
    A pin against the queen only counts when the pinning piece is worth less than the queen.
    """
    pins = set()
    targets = board.pieces(chess.KING, not color) | board.pieces(chess.QUEEN, not color)
    for pinner in board.pieces(chess.BISHOP, color) | board.pieces(chess.ROOK, color) | board.pieces(chess.QUEEN, color):
        pinner_type = board.piece_type_at(pinner)
        for target in targets:
            target_type = board.piece_type_at(target)
            if target_type == chess.QUEEN and PIECE_VALUES[pinner_type] >= PIECE_VALUES[chess.QUEEN]:
                continue
            ray = chess.ray(pinner, target)
            if not ray:
                continue
            is_diagonal = chess.square_file(pinner) != chess.square_file(target) and \
                chess.square_rank(pinner) != chess.square_rank(target)
            if is_diagonal and pinner_type == chess.ROOK or not is_diagonal and pinner_type == chess.BISHOP:
                continue
            between = list(chess.SquareSet(chess.between(pinner, target)) & board.occupied)
            if len(between) != 1:
                continue
            pinned = between[0]
            pinned_piece = board.piece_at(pinned)
            if pinned_piece.color == color or pinned_piece.piece_type == chess.KING:
                continue
            if target_type == chess.QUEEN and pinned_piece.piece_type == chess.QUEEN:
                continue
            pins.add(Pin(pinned=pinned, pinner=pinner, target=target))
    return pins


def _is_safe_pinner(board: chess.Board, pinner: chess.Square) -> bool:
    """
    A pinning piece is safe when the opponent can't take it, or only with pieces worth at least as much
    while the pinning piece is defended.
    """
    value = PIECE_VALUES[board.piece_type_at(pinner)]
    captures = [move for move in board.legal_moves if move.to_square == pinner]
    if not captures:
        return True
    if not board.is_attacked_by(not board.turn, pinner):
        return False
    return all(PIECE_VALUES[board.piece_type_at(move.from_square)] >= value for move in captures)


def pinning_moves(board: chess.Board) -> dict[chess.Move, Pin]:
    """
    Returns the moves that create a new, safe pin, with the pin they create.
    """
    color = board.turn
    existing = {(pin.pinned, pin.target) for pin in find_pins(board, color)}
    moves = {}
    for move in list(board.legal_moves):
        board.push(move)
        try:
            if board.is_checkmate():
                continue
            for pin in sorted(find_pins(board, color), key=lambda pin: -PIECE_VALUES[board.piece_type_at(pin.target)]):
                if (pin.pinned, pin.target) not in existing and _is_safe_pinner(board, pin.pinner):
                    moves[move] = pin
                    break
        finally:
            board.pop()
    return moves


def analyse_pin_puzzle(board: chess.Board) -> PuzzleAnalysis:
    """
    Checks a "pin a piece" puzzle: the position is legal, there is no mate in 1 and exactly one move creates a safe
    new pin against the king or the queen.
    """
    if not board.is_valid():
        return PuzzleAnalysis(False, f"illegal position ({board.status()!r})")
    if board.is_game_over():
        return PuzzleAnalysis(False, "the game is already over")
    if forces_mate(board, 1):
        return PuzzleAnalysis(False, "there is a mate in 1")
    moves = pinning_moves(board)
    if not moves:
        return PuzzleAnalysis(False, "no move creates a safe pin")
    key_moves = tuple(move.uci() for move in moves)
    if len(moves) > 1:
        return PuzzleAnalysis(False, f"more than one move pins: {', '.join(board.san(m) for m in moves)}", key_moves)
    return PuzzleAnalysis(True, "sound", key_moves)


def build_pin_tree(board: chess.Board) -> dict:
    moves = {}
    for move, pin in pinning_moves(board).items():
        san = board.san(move)
        board.push(move)
        moves[move.uci()] = {"san": san, "end": True, "pin": pin.describe(board)}
        board.pop()
    return {"moves": moves}
