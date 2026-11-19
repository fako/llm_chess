from django.db import migrations


def forwards(apps, schema_editor):
    ChessPuzzleCategory = apps.get_model("puzzles", "ChessPuzzleCategory")
    ChessPuzzle = apps.get_model("puzzles", "ChessPuzzle")
    # Mates in 3 hardly come out sound at low effort, so this category thinks harder by default
    ChessPuzzleCategory.objects.filter(slug="mate-in-3").update(model="claude-opus-5", effort="high")
    # Every puzzle before this migration was requested from Claude Opus 5 at low effort,
    # which the stored Datagrowth requests confirm.
    ChessPuzzle.objects.filter(model="").update(model="claude-opus-5")
    ChessPuzzle.objects.filter(effort="").update(effort="low")
    # The model that answered is kept as served_by, because it differs from the requested model after a fallback
    for puzzle in ChessPuzzle.objects.filter(generation__has_key="model"):
        puzzle.generation["served_by"] = puzzle.generation.pop("model")
        puzzle.save(update_fields=["generation"])


class Migration(migrations.Migration):

    dependencies = [
        ("puzzles", "0005_generation_model_and_effort"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
