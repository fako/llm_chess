from django.db import migrations


MATE_IN_TWO_PROMPT = """You are a chess problem composer. Compose {{ count }} original "mate in {{ mate_in }}" puzzles.

In a mate in {{ mate_in }} the solving side moves first and forces checkmate with its second move, whatever the \
opponent replies. The first move (the key) must be the only move that forces mate in {{ mate_in }}, and there must be \
no mate in 1.

Guidelines:
- Keep positions compact, with at most 12 pieces in total. Fewer pieces make the puzzle cleaner and easier to verify.
- The best puzzles have a quiet or surprising key: a sacrifice, a quiet move that creates a zugzwang, a deflection, \
or a move that clears a line. Avoid keys that are obvious checks when a quieter idea works.
- Base positions on reliable mating patterns: back rank mates, smothered mates, Anastasia's mate, Boden's mate, \
Arabian mate, mates with two rooks or queen and bishop, and king hunts against an exposed king.
- Mix puzzles where white solves with puzzles where black solves.
- Vary the patterns within this batch."""


def create_category(apps, schema_editor):
    ChessPuzzleCategory = apps.get_model("puzzles", "ChessPuzzleCategory")
    ChessPuzzleCategory.objects.update_or_create(
        slug="mate-in-2",
        defaults={
            "name": "Mate in 2",
            "description": "Force checkmate in two moves, whatever your opponent tries.",
            "prompt": MATE_IN_TWO_PROMPT,
            "mate_in": 2,
            "order": 2,
        },
    )


def delete_category(apps, schema_editor):
    ChessPuzzleCategory = apps.get_model("puzzles", "ChessPuzzleCategory")
    ChessPuzzleCategory.objects.filter(slug="mate-in-2", puzzles__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("puzzles", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_category, delete_category),
    ]
