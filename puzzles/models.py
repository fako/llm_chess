from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.translation import get_language, gettext

import chess


class Perspective(models.TextChoices):
    WHITE = "white", "White"
    BLACK = "black", "Black"


class Goal(models.TextChoices):
    MATE = "mate", "Forced mate"
    PIN = "pin", "Pin a piece"


class LLM(models.TextChoices):
    OPUS_5 = "claude-opus-5", "Claude Opus 5"
    OPUS_5_5 = "claude-opus-5-5", "Claude Opus 5.5"
    SONNET_5 = "claude-sonnet-5", "Claude Sonnet 5"
    FABLE_5_1 = "claude-fable-5-1", "Claude Fable 5.1"


class Effort(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    XHIGH = "xhigh", "Extra high"
    MAX = "max", "Max"


def localized(instance: models.Model, field: str) -> str:
    """
    The value of a field like title_en or title_nl in the active language, falling back to English when empty.
    """
    value = getattr(instance, f"{field}_{get_language()}", "")
    return value or getattr(instance, f"{field}_en")


class ChessPuzzleCategory(models.Model):
    """
    A kind of puzzle like "mate in 2". The prompt is what an LLM gets to generate puzzles in this category.
    """
    slug = models.SlugField(unique=True)
    name_en = models.CharField(max_length=100)
    name_nl = models.CharField(max_length=100, blank=True)
    description_en = models.CharField(max_length=255, blank=True)
    description_nl = models.CharField(max_length=255, blank=True)
    prompt = models.TextField(
        help_text="Jinja2 template sent to the LLM. Available variables: count, mate_in."
    )
    goal = models.CharField(max_length=10, choices=Goal.choices, default=Goal.MATE,
                            help_text="Decides how the solver verifies puzzles in this category.")
    mate_in = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="For forced mates: puzzles are verified to force mate in exactly this many moves."
    )
    model = models.CharField(max_length=50, choices=LLM.choices, default=LLM.OPUS_5,
                             help_text="The LLM that generates puzzles, unless the generate command overrides it.")
    effort = models.CharField(max_length=10, choices=Effort.choices, default=Effort.LOW,
                              help_text="How much the LLM thinks per request. More effort costs more tokens.")
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name_en"]
        verbose_name_plural = "chess puzzle categories"

    def __str__(self) -> str:
        return self.name_en

    @property
    def name(self) -> str:
        return localized(self, "name")

    @property
    def description(self) -> str:
        return localized(self, "description")

    @property
    def depth(self) -> int:
        """
        The amount of moves the solving side makes to solve a puzzle.
        """
        return self.mate_in if self.goal == Goal.MATE and self.mate_in else 1

    @property
    def task(self) -> str:
        """
        What the player has to do, in the active language. It completes the "White to play and ..." sentence.
        """
        if self.goal == Goal.PIN:
            return gettext("puzzles.goal.pin")
        return gettext("puzzles.goal.mate_in") % {"depth": self.depth}


class ChessPuzzle(models.Model):
    category = models.ForeignKey(ChessPuzzleCategory, on_delete=models.PROTECT, related_name="puzzles")
    fen = models.CharField(max_length=100)
    position = models.CharField(max_length=100, unique=True, help_text="FEN without move counters, to deduplicate.")
    perspective = models.CharField(max_length=5, choices=Perspective.choices)
    solution = models.JSONField(help_text="Solution tree verified and completed by the solver.")
    title_en = models.CharField(max_length=255, blank=True)
    title_nl = models.CharField(max_length=255, blank=True)
    hint_en = models.CharField(max_length=255, blank=True)
    hint_nl = models.CharField(max_length=255, blank=True)
    tags = ArrayField(models.CharField(max_length=50), default=list, blank=True,
                      help_text="What the puzzle is about, as detected on the solution (see puzzles/tags.py). "
                                "Only used to vary generation, never shown to users.")
    model = models.CharField(max_length=50, choices=LLM.choices, blank=True,
                             help_text="The LLM that was asked to generate this puzzle.")
    effort = models.CharField(max_length=10, choices=Effort.choices, blank=True,
                              help_text="The effort the LLM was asked to put into generating this puzzle.")
    generation = models.JSONField(default=dict, blank=True, help_text="LLM proposal and metadata of the generation.")
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, through="UserChessPuzzle", related_name="chess_puzzles")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.category} #{self.pk}"

    @property
    def title(self) -> str:
        return localized(self, "title")

    @property
    def hint(self) -> str:
        return localized(self, "hint")

    @property
    def board(self) -> chess.Board:
        return chess.Board(self.fen)

    @property
    def color(self) -> chess.Color:
        return chess.WHITE if self.perspective == Perspective.WHITE else chess.BLACK


class UserChessPuzzle(models.Model):
    """
    The progress of a user on a puzzle. The line of the attempt in progress is stored,
    so an attempt survives reloads and switching devices.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="puzzle_progress")
    puzzle = models.ForeignKey(ChessPuzzle, on_delete=models.CASCADE, related_name="user_progress")
    wrong_moves = models.PositiveIntegerField(default=0)
    hints_used = models.PositiveIntegerField(default=0)
    solved_at = models.DateTimeField(null=True, blank=True, help_text="When the user first solved the puzzle.")
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
    def is_solved(self) -> bool:
        return self.solved_at is not None
