from django.conf import settings
from django.db import models

import chess


class Perspective(models.TextChoices):
    WHITE = "white", "White"
    BLACK = "black", "Black"


class ChessPuzzleCategory(models.Model):
    """
    A kind of puzzle like "mate in 2". The prompt is what an LLM gets to generate puzzles in this category.
    """
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    prompt = models.TextField(
        help_text="Jinja2 template sent to the LLM. Available variables: count, mate_in."
    )
    mate_in = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Puzzles in this category are verified to force mate in exactly this many moves."
    )
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "chess puzzle categories"

    def __str__(self) -> str:
        return self.name


class ChessPuzzle(models.Model):
    category = models.ForeignKey(ChessPuzzleCategory, on_delete=models.PROTECT, related_name="puzzles")
    fen = models.CharField(max_length=100)
    position = models.CharField(max_length=100, unique=True, help_text="FEN without move counters, to deduplicate.")
    perspective = models.CharField(max_length=5, choices=Perspective.choices)
    solution = models.JSONField(help_text="Solution tree verified and completed by the solver.")
    branches = models.JSONField(default=list, help_text="Every line of opponent replies the user can complete.")
    title = models.CharField(max_length=255, blank=True)
    hint = models.CharField(max_length=255, blank=True)
    generation = models.JSONField(default=dict, blank=True, help_text="LLM proposal and metadata of the generation.")
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, through="UserChessPuzzle", related_name="chess_puzzles")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.category} #{self.pk}"

    @property
    def board(self) -> chess.Board:
        return chess.Board(self.fen)

    @property
    def color(self) -> chess.Color:
        return chess.WHITE if self.perspective == Perspective.WHITE else chess.BLACK


class UserChessPuzzle(models.Model):
    """
    The progress of a user on a puzzle. Every solve completes one branch of the solution tree.
    The line of the attempt in progress is stored, so an attempt survives reloads and switching devices.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="puzzle_progress")
    puzzle = models.ForeignKey(ChessPuzzle, on_delete=models.CASCADE, related_name="user_progress")
    wrong_moves = models.PositiveIntegerField(default=0)
    hints_used = models.PositiveIntegerField(default=0)
    completed_branches = models.JSONField(default=list, blank=True)
    line = models.JSONField(default=list, blank=True, help_text="UCI moves of the attempt in progress.")
    hint_level = models.PositiveSmallIntegerField(default=0, help_text="Hints shown for the current position.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "puzzle"], name="unique_user_chess_puzzle"),
        ]

    def __str__(self) -> str:
        return f"{self.user} on {self.puzzle}"

    @property
    def open_branches(self) -> list[str]:
        completed = set(self.completed_branches)
        return [branch for branch in self.puzzle.branches if branch not in completed]

    @property
    def is_fully_solved(self) -> bool:
        return not self.open_branches
