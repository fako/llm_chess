from django.contrib.auth import login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from accounts.forms import SignupForm


def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("puzzles:home")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("puzzles:home")
    return render(request, "accounts/signup.htmx", {"form": form})
