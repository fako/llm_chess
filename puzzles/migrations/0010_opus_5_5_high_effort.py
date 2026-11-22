"""
Generates the v2 puzzles of every category with Claude Opus 5.5 on high effort.
"""
from django.db import migrations


def use_opus_5_5(apps, schema_editor):
    ChessPuzzleCategory = apps.get_model("puzzles", "ChessPuzzleCategory")
    ChessPuzzleCategory.objects.update(model="claude-opus-5-5", effort="high")


class Migration(migrations.Migration):

    dependencies = [
        ("puzzles", "0009_tags_and_v2_prompts"),
    ]

    operations = [
        migrations.RunPython(use_opus_5_5, migrations.RunPython.noop),
    ]
