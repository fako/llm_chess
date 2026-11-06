from django.urls import path

from puzzles import views


app_name = "puzzles"
urlpatterns = [
    path("", views.home, name="home"),
    path("categories/<slug:slug>/", views.category, name="category"),
    path("puzzles/<int:pk>/", views.puzzle, name="puzzle"),
    path("puzzles/<int:pk>/<slug:action>/", views.puzzle_action, name="puzzle_action"),
]
