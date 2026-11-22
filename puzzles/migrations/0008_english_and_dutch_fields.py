from django.db import migrations, models


DUTCH = {
    "mate-in-1": ("Mat in 1", "Vind de enige zet die mat zet."),
    "mate-in-2": ("Mat in 2", "Geef mat in twee zetten, wat je tegenstander ook probeert."),
    "mate-in-3": ("Mat in 3", "Geef mat in drie zetten, tegen elke verdediging."),
    "pin-a-piece": ("Penning", "Pen een stuk van je tegenstander vast tegen zijn koning of dame."),
}


def add_dutch_categories(apps, schema_editor):
    ChessPuzzleCategory = apps.get_model("puzzles", "ChessPuzzleCategory")
    for slug, (name, description) in DUTCH.items():
        ChessPuzzleCategory.objects.filter(slug=slug).update(name_nl=name, description_nl=description)


class Migration(migrations.Migration):

    dependencies = [
        ("puzzles", "0007_single_solution_line"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="chesspuzzlecategory",
            options={"ordering": ["order", "name_en"], "verbose_name_plural": "chess puzzle categories"},
        ),
        migrations.RenameField("chesspuzzlecategory", "name", "name_en"),
        migrations.RenameField("chesspuzzlecategory", "description", "description_en"),
        migrations.RenameField("chesspuzzle", "title", "title_en"),
        migrations.RenameField("chesspuzzle", "hint", "hint_en"),
        migrations.AddField("chesspuzzlecategory", "name_nl", models.CharField(blank=True, max_length=100)),
        migrations.AddField("chesspuzzlecategory", "description_nl", models.CharField(blank=True, max_length=255)),
        migrations.AddField("chesspuzzle", "title_nl", models.CharField(blank=True, max_length=255)),
        migrations.AddField("chesspuzzle", "hint_nl", models.CharField(blank=True, max_length=255)),
        migrations.RunPython(add_dutch_categories, migrations.RunPython.noop),
    ]
