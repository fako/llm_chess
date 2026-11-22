"""
Version 2 of the puzzles: puzzles get tags, and category prompts leave variety to the tags the generator asks for.
Existing puzzles are deleted (along with the progress of users on them), because they were generated in English only
and without tags. The v2_puzzles command set in workspace.json loads the regenerated puzzles afterwards.
"""
import django.contrib.postgres.fields
from django.db import migrations, models


MATE_IN_ONE_PROMPT = """You are a chess problem composer. Compose {{ count }} original "mate in 1" puzzles.

In a mate in 1 the solving side checkmates with its first move. That move must be the only move that mates.

Guidelines:
- Keep positions compact, with at most 12 pieces in total.
- Make the mate a little hidden: avoid positions where several checks look equally natural and one of them simply \
mates.
- Make sure no second move mates as well: check every other check, capture and promotion of the solving side."""


MATE_IN_TWO_PROMPT = """You are a chess problem composer. Compose {{ count }} original "mate in {{ mate_in }}" puzzles.

In a mate in {{ mate_in }} the solving side moves first and forces checkmate with its second move, whatever the \
opponent replies. The first move (the key) must be the only move that forces mate in {{ mate_in }}, and there must be \
no mate in 1.

Guidelines:
- Keep positions compact, with at most 12 pieces in total. Fewer pieces make the puzzle cleaner and easier to verify.
- The best puzzles have a surprising key. Avoid keys that are the most obvious check on the board."""


MATE_IN_THREE_PROMPT = """You are a chess problem composer. Compose {{ count }} original "mate in {{ mate_in }}" puzzles.

In a mate in {{ mate_in }} the solving side moves first and forces checkmate with its third move, whatever the \
opponent replies. The first move (the key) must be the only move that forces mate in {{ mate_in }}, and there must be \
no mate in 1 or mate in 2.

Guidelines:
- Keep positions compact, with at most 12 pieces in total. Fewer pieces make the puzzle cleaner and easier to verify.
- Good mates in 3 combine two ideas, for instance a move that opens the king followed by a second blow before the \
mate."""


PIN_PROMPT = """You are a chess trainer. Compose {{ count }} original "pin a piece" puzzles.

In these puzzles the solving side has exactly one move that pins a piece of the opponent: after the move a bishop, \
rook or queen of the solving side attacks an opponent piece that can't move away (or shouldn't), because the \
opponent's king or queen stands behind it on the same line.

Rules the puzzle must follow:
- Exactly one legal move creates a new pin against the king or the queen. Pins that already exist before the move \
don't count, and no other move may create a pin as well.
- After the move the pinning piece is safe: the opponent can't capture it, or only with a piece that is worth at \
least as much while the pinning piece is defended.
- A pin against the queen only counts when the pinning piece is a bishop or rook.
- There is no checkmate in 1 for the solving side.

Guidelines:
- Make the pin worth something: the pinned piece is undefended, attacked a second time, or the pin wins the piece \
behind it.
- Keep positions compact and realistic, with 8 to 16 pieces in total, as if taken from a middlegame or endgame."""


PROMPTS = {
    "mate-in-1": MATE_IN_ONE_PROMPT,
    "mate-in-2": MATE_IN_TWO_PROMPT,
    "mate-in-3": MATE_IN_THREE_PROMPT,
    "pin-a-piece": PIN_PROMPT,
}


def start_version_two(apps, schema_editor):
    ChessPuzzle = apps.get_model("puzzles", "ChessPuzzle")
    ChessPuzzleCategory = apps.get_model("puzzles", "ChessPuzzleCategory")
    ChessPuzzle.objects.all().delete()
    for slug, prompt in PROMPTS.items():
        ChessPuzzleCategory.objects.filter(slug=slug).update(prompt=prompt)


class Migration(migrations.Migration):

    dependencies = [
        ("puzzles", "0008_english_and_dutch_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="chesspuzzle",
            name="tags",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=50), blank=True, default=list, size=None,
                help_text="What the puzzle is about, as detected on the solution (see puzzles/tags.py). "
                          "Only used to vary generation, never shown to users.",
            ),
        ),
        migrations.RunPython(start_version_two, migrations.RunPython.noop),
    ]
