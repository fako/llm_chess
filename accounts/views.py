from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.hashers import make_password
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from social_core.actions import do_complete
from social_django.utils import load_backend, load_strategy
from social_django.views import _do_login

from accounts.forms import SignupForm
from puzzles.models import ChessPuzzleCategory, UserChessPuzzle


BACKEND = "username"


def _complete(request: HttpRequest, data: dict, **pipeline) -> HttpResponse:
    """
    Hands a validated login or signup to python social auth. The request data is replaced with only the fields the
    pipeline needs, so passwords never reach the pipeline (see accounts/pipeline.py).
    """
    post = QueryDict(mutable=True)
    post.update({key: value for key, value in data.items() if value})
    request.POST = post
    strategy = load_strategy(request)
    backend = load_backend(strategy, BACKEND, redirect_uri=reverse("social:complete", args=(BACKEND,)))
    return do_complete(backend, _do_login, user=request.user, redirect_name=REDIRECT_FIELD_NAME, request=request,
                       **pipeline)


def login(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("puzzles:home")
    next_url = request.POST.get(REDIRECT_FIELD_NAME) or request.GET.get(REDIRECT_FIELD_NAME, "")
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        return _complete(request, {"username": user.get_username(), REDIRECT_FIELD_NAME: next_url},
                         password_user=user)
    return render(request, "accounts/login.htmx", {"form": form, "next": next_url})


def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("puzzles:home")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        return _complete(request, {"username": form.cleaned_data["username"], "email": form.cleaned_data["email"]},
                         password_hash=make_password(form.cleaned_data["password1"]))
    return render(request, "accounts/signup.htmx", {"form": form})


def verify_email(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/verify_email.htmx", {
        "email": request.session.get("email_validation_address"),
    })


@login_required
def profile(request: HttpRequest) -> HttpResponse:
    progress = UserChessPuzzle.objects.filter(user=request.user)
    solved = progress.filter(solved_at__isnull=False)
    totals = solved.aggregate(wrong_moves=Sum("wrong_moves"), hints=Sum("hints_used"))
    solved_ids = solved.values("puzzle_id")
    categories = ChessPuzzleCategory.objects.filter(is_active=True).annotate(
        total=Count("puzzles"),
        solved=Count("puzzles", filter=Q(puzzles__id__in=solved_ids)),
    )
    clean = solved.filter(wrong_moves=0, hints_used=0).count()
    return render(request, "accounts/profile.htmx", {
        "solved_count": solved.count(),
        "clean_count": clean,
        "wrong_moves": totals["wrong_moves"] or 0,
        "hints": totals["hints"] or 0,
        "categories": categories,
        "recent": solved.select_related("puzzle", "puzzle__category").order_by("-solved_at")[:10],
    })
