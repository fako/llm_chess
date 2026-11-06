"""
Forced mate search on top of python-chess.

The LLM proposes puzzles, but it is this module that decides whether a proposal is a sound puzzle and that builds the
solution tree the play engine runs on. Nothing an LLM claims about a position ends up in front of a user unverified.

A solution tree alternates two kinds of nodes:

    user node:   {"moves": {<uci>: <move node>, ...}}                  every move that keeps a forced mate
    move node:   {"san": "Qh7+", "mate": true}                         the move mates
                 {"san": "Qh7+", "mate": false, "replies": {<uci>: <user node + "san">, ...}}
                                                                       every legal defence of the opponent

A branch is the sequence of opponent replies along one line of the tree, joined with "/".
Completing a branch means mating the opponent after they defended along exactly that line.
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
            node["mate"] = True
        else:
            node["mate"] = False
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
        if node["mate"]:
            if path:
                branches.add(BRANCH_SEPARATOR.join(path))
            continue
        for reply, reply_node in node["replies"].items():
            branches.update(list_branches(reply_node, path + (reply,)))
    return sorted(branches)


@dataclass(frozen=True)
class MateAnalysis:
    is_sound: bool
    reason: str
    key_moves: tuple[str, ...] = tuple()  # in UCI


def analyse_mate_puzzle(board: chess.Board, depth: int) -> MateAnalysis:
    """
    Checks the classic composition rules for a "mate in depth" puzzle:
    the position is legal, there is no faster mate and exactly one first move (the key) forces mate in time.
    Alternative mating moves later in a line ("duals") are accepted, because users may play any of them.
    """
    if not board.is_valid():
        return MateAnalysis(False, f"illegal position ({board.status()!r})")
    if board.is_game_over():
        return MateAnalysis(False, "the game is already over")
    for shorter in range(1, depth):
        if forces_mate(board, shorter):
            return MateAnalysis(False, f"there is already a mate in {shorter}")
    keys = mating_moves(board, depth)
    if not keys:
        return MateAnalysis(False, f"there is no forced mate in {depth}")
    key_moves = tuple(move.uci() for move in keys)
    if len(keys) > 1:
        return MateAnalysis(False, f"more than one first move works: {', '.join(board.san(m) for m in keys)}",
                            key_moves)
    return MateAnalysis(True, "sound", key_moves)
