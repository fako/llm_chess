from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

import chess

from puzzles import engine
from puzzles.models import ChessPuzzle, ChessPuzzleCategory, UserChessPuzzle


MESSAGES = {
    engine.Outcome.WRONG: "That's not it. Look again.",
    engine.Outcome.CORRECT: None,
    engine.Outcome.MATE: None,
    engine.Outcome.ILLEGAL: "That move isn't possible right now.",
}


@login_required
def home(request: HttpRequest) -> HttpResponse:
    resolved = UserChessPuzzle.objects.filter(user=request.user).filter(~Q(completed_branches=[])) \
        .values("puzzle_id")
    categories = ChessPuzzleCategory.objects.filter(is_active=True).annotate(
        total=Count("puzzles"),
        unsolved=Count("puzzles", filter=~Q(puzzles__id__in=resolved)),
    )
    return render(request, "puzzles/home.htmx", {"categories": categories})


@login_required
def category(request: HttpRequest, slug: str) -> HttpResponse:
    puzzle_category = get_object_or_404(ChessPuzzleCategory, slug=slug, is_active=True)
    puzzle = engine.next_puzzle(request.user, puzzle_category)
    if puzzle is not None:
        return redirect("puzzles:puzzle", pk=puzzle.pk)
    return render(request, "puzzles/category.htmx", {
        "category": puzzle_category,
        "open_progress": engine.puzzles_with_open_branches(request.user, puzzle_category),
        "has_puzzles": puzzle_category.puzzles.exists(),
    })


def _render_puzzle(request: HttpRequest, progress: UserChessPuzzle, message: str | None = None,
                   wrong_move: str | None = None) -> HttpResponse:
    state = engine.get_state(progress)
    template = "puzzles/partials/puzzle.htmx" if request.htmx else "puzzles/puzzle.htmx"
    wrong_squares = []
    if wrong_move:
        move = chess.Move.from_uci(wrong_move)
        wrong_squares = [chess.square_name(move.from_square), chess.square_name(move.to_square)]
    return render(request, template, {
        "state": state,
        "puzzle": progress.puzzle,
        "category": progress.puzzle.category,
        "message": message,
        "wrong_squares": wrong_squares,
        "squares": _squares(state, wrong_squares),
    })


def _squares(state: engine.PuzzleState, wrong_squares: list[str]) -> list[dict]:
    """
    The squares of the board in display order, so that the solving side plays from the bottom.
    """
    color = state.puzzle.color
    ranks = range(7, -1, -1) if color == chess.WHITE else range(8)
    files = range(8) if color == chess.WHITE else range(7, -1, -1)
    last_move = [state.last_move.from_square, state.last_move.to_square] if state.last_move else []
    squares = []
    for row, rank in enumerate(ranks):
        for column, file in enumerate(files):
            square = chess.square(file, rank)
            name = chess.square_name(square)
            piece = state.board.piece_at(square)
            squares.append({
                "name": name,
                "is_light": (file + rank) % 2 == 1,
                "piece": piece.symbol() if piece else None,
                "is_own": piece is not None and piece.color == color,
                "rank_label": str(rank + 1) if column == 0 else None,
                "file_label": chess.FILE_NAMES[file] if row == 7 else None,
                "is_last_move": square in last_move,
                "is_hint": name in state.hint_squares,
                "is_wrong": name in wrong_squares,
            })
    return squares


@login_required
def puzzle(request: HttpRequest, pk: int) -> HttpResponse:
    chess_puzzle = get_object_or_404(ChessPuzzle.objects.select_related("category"), pk=pk)
    progress = engine.get_progress(request.user, chess_puzzle)
    return _render_puzzle(request, progress)


@login_required
@require_POST
def puzzle_action(request: HttpRequest, pk: int, action: str) -> HttpResponse:
    chess_puzzle = get_object_or_404(ChessPuzzle.objects.select_related("category"), pk=pk)
    progress = engine.get_progress(request.user, chess_puzzle)
    message = None
    wrong_move = None
    if action == "move":
        uci = request.POST.get("move", "")
        outcome = engine.play_move(progress, uci)
        message = MESSAGES[outcome]
        if outcome == engine.Outcome.WRONG:
            wrong_move = uci
    elif action == "reply":
        if not engine.choose_reply(progress, request.POST.get("move", "")):
            message = MESSAGES[engine.Outcome.ILLEGAL]
    elif action == "hint":
        engine.take_hint(progress)
    elif action == "restart":
        engine.restart(progress)
    else:
        return HttpResponse(status=404)
    if not request.htmx:
        return redirect("puzzles:puzzle", pk=pk)
    return _render_puzzle(request, progress, message=message, wrong_move=wrong_move)
