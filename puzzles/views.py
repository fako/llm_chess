from django.contrib.auth.views import redirect_to_login
from django.db.models import Count, Q
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django_htmx.http import HttpResponseClientRedirect

import chess

from puzzles import engine, previews
from puzzles.models import ChessPuzzle, ChessPuzzleCategory, UserChessPuzzle


# Anyone may browse the categories and look at puzzles. Playing a puzzle needs an account, because the progress
# is stored per user. The puzzle page asks visitors to log in or sign up before they play (see board.js).


def home(request: HttpRequest) -> HttpResponse:
    solved = UserChessPuzzle.objects.filter(user_id=request.user.pk, solved_at__isnull=False).values("puzzle_id")
    categories = ChessPuzzleCategory.objects.filter(is_active=True).annotate(
        total=Count("puzzles"),
        unsolved=Count("puzzles", filter=~Q(puzzles__id__in=solved)),
    )
    return render(request, "puzzles/home.htmx", {"categories": categories})


def category(request: HttpRequest, slug: str) -> HttpResponse:
    puzzle_category = get_object_or_404(ChessPuzzleCategory, slug=slug, is_active=True)
    puzzle = engine.next_puzzle(request.user, puzzle_category)
    if puzzle is not None:
        return redirect("puzzles:puzzle", pk=puzzle.pk)
    return render(request, "puzzles/category.htmx", {
        "category": puzzle_category,
        "has_puzzles": puzzle_category.puzzles.exists(),
    })


def _render_puzzle(request: HttpRequest, progress: UserChessPuzzle, wrong_move: str | None = None) -> HttpResponse:
    state = engine.get_state(progress)
    template = "puzzles/partials/puzzle.htmx" if request.htmx else "puzzles/puzzle.htmx"
    wrong_squares = []
    if wrong_move:
        move = chess.Move.from_uci(wrong_move)
        wrong_squares = [chess.square_name(move.from_square), chess.square_name(move.to_square)]
    previous_puzzle, next_puzzle = engine.adjacent_puzzles(progress.puzzle)
    return render(request, template, {
        "state": state,
        "puzzle": progress.puzzle,
        "category": progress.puzzle.category,
        "preview_url": reverse("puzzle_preview", kwargs={"pk": progress.puzzle.pk,
                                                         "digest": previews.digest(progress.puzzle)}),
        "previous_puzzle": previous_puzzle,
        "next_puzzle": next_puzzle,
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


def puzzle(request: HttpRequest, pk: int) -> HttpResponse:
    chess_puzzle = get_object_or_404(ChessPuzzle.objects.select_related("category"), pk=pk)
    if request.user.is_authenticated:
        progress = engine.get_progress(request.user, chess_puzzle)
    else:  # visitors see the puzzle as a fresh attempt that never gets saved
        progress = UserChessPuzzle(puzzle=chess_puzzle)
    return _render_puzzle(request, progress)


@require_POST
def puzzle_action(request: HttpRequest, pk: int, action: str) -> HttpResponse:
    if not request.user.is_authenticated:  # the page asks visitors to log in first, but sessions may expire
        login_url = redirect_to_login(reverse("puzzles:puzzle", kwargs={"pk": pk})).url
        return HttpResponseClientRedirect(login_url) if request.htmx else redirect(login_url)
    chess_puzzle = get_object_or_404(ChessPuzzle.objects.select_related("category"), pk=pk)
    progress = engine.get_progress(request.user, chess_puzzle)
    wrong_move = None
    if action == "move":
        uci = request.POST.get("move", "")
        if engine.play_move(progress, uci) == engine.Outcome.WRONG:
            wrong_move = uci
    elif action == "hint":
        engine.take_hint(progress)
    elif action == "restart":
        engine.restart(progress)
    else:
        return HttpResponse(status=404)
    if not request.htmx:
        return redirect("puzzles:puzzle", pk=pk)
    return _render_puzzle(request, progress, wrong_move=wrong_move)


def puzzle_preview(request: HttpRequest, pk: int, digest: str) -> HttpResponse:
    """
    The image that apps show with a shared link to a puzzle (see previews.py). The digest in the URL changes with
    the image, so the image may be cached for good, and old URLs move on to the current image.
    """
    chess_puzzle = get_object_or_404(ChessPuzzle, pk=pk)
    current = previews.digest(chess_puzzle)
    if digest != current:
        return redirect("puzzle_preview", pk=pk, digest=current, permanent=True)
    response = FileResponse(previews.get_preview(chess_puzzle).open("rb"), content_type="image/png")
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response
