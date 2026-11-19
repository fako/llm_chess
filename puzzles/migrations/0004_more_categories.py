from django.db import migrations


MATE_IN_ONE_PROMPT = """You are a chess problem composer. Compose {{ count }} original "mate in 1" puzzles.

In a mate in 1 the solving side checkmates with its first move. That move must be the only move that mates.

Guidelines:
- Keep positions compact, with at most 12 pieces in total.
- Make the mate a little hidden: a mate by a piece that is easy to overlook, a mate that needs a capture, a discovered \
or double check, a knight mate, or an underpromotion. Avoid positions where several checks look equally natural \
and one of them simply mates.
- Make sure no second move mates as well: check every other check, capture and promotion of the solving side.
- Base positions on reliable mating patterns: back rank mates, smothered mates, Anastasia's mate, Boden's mate, \
Arabian mate, Damiano's mate, epaulette mate and mates with queen and bishop.
- Mix puzzles where white solves with puzzles where black solves.
- Vary the patterns within this batch."""


MATE_IN_THREE_PROMPT = """You are a chess problem composer. Compose {{ count }} original "mate in {{ mate_in }}" puzzles.

In a mate in {{ mate_in }} the solving side moves first and forces checkmate with its third move, whatever the \
opponent replies. The first move (the key) must be the only move that forces mate in {{ mate_in }}, and there must be \
no mate in 1 or mate in 2.

Guidelines:
- Keep positions compact, with at most 12 pieces in total. Fewer pieces make the puzzle cleaner and easier to verify.
- Good mates in 3 combine two ideas: a sacrifice that opens the king, followed by a quiet move or a second sacrifice \
before the mate. A king hunt with forcing checks works well too.
- Base positions on reliable mating patterns: back rank mates, smothered mates (Philidor's legacy), Anastasia's mate, \
Boden's mate, Arabian mate, Greco's mate and mates with two rooks or queen and bishop.
- Mix puzzles where white solves with puzzles where black solves.
- Vary the patterns within this batch."""


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
- Keep positions compact and realistic, with 8 to 16 pieces in total, as if taken from a middlegame or endgame.
- Use different pinning pieces (bishop, rook, queen) and both pins along files, ranks and diagonals.
- Mix puzzles where white solves with puzzles where black solves."""


CATEGORIES = [
    {
        "slug": "mate-in-1",
        "name": "Mate in 1",
        "description": "Find the one move that checkmates.",
        "prompt": MATE_IN_ONE_PROMPT,
        "goal": "mate",
        "mate_in": 1,
        "order": 1,
    },
    {
        "slug": "mate-in-3",
        "name": "Mate in 3",
        "description": "Force checkmate in three moves, against every defence.",
        "prompt": MATE_IN_THREE_PROMPT,
        "goal": "mate",
        "mate_in": 3,
        "order": 3,
    },
    {
        "slug": "pin-a-piece",
        "name": "Pin a piece",
        "description": "Pin an enemy piece to its king or queen.",
        "prompt": PIN_PROMPT,
        "goal": "pin",
        "mate_in": None,
        "order": 4,
    },
]


def rename_key(node, old: str, new: str):
    if isinstance(node, dict):
        return {(new if key == old else key): rename_key(value, old, new) for key, value in node.items()}
    return node


def forwards(apps, schema_editor):
    ChessPuzzleCategory = apps.get_model("puzzles", "ChessPuzzleCategory")
    ChessPuzzle = apps.get_model("puzzles", "ChessPuzzle")
    for category in CATEGORIES:
        ChessPuzzleCategory.objects.update_or_create(slug=category["slug"], defaults=category)
    # Lines in solution trees now end with "end" instead of "mate", because not every puzzle ends in a mate
    for puzzle in ChessPuzzle.objects.all():
        puzzle.solution = rename_key(puzzle.solution, "mate", "end")
        puzzle.save(update_fields=["solution"])


def backwards(apps, schema_editor):
    ChessPuzzleCategory = apps.get_model("puzzles", "ChessPuzzleCategory")
    ChessPuzzle = apps.get_model("puzzles", "ChessPuzzle")
    for puzzle in ChessPuzzle.objects.all():
        puzzle.solution = rename_key(puzzle.solution, "end", "mate")
        puzzle.save(update_fields=["solution"])
    ChessPuzzleCategory.objects.filter(slug__in=[category["slug"] for category in CATEGORIES],
                                       puzzles__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("puzzles", "0003_category_goal"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
