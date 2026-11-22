from django.core.management.base import BaseCommand

from puzzles.models import ChessPuzzleCategory
from puzzles.tags import Coverage, applicable_tags


class Command(BaseCommand):
    help = "Shows how many puzzles every category has per tag and solving side, to see where variety is missing."

    def add_arguments(self, parser):
        parser.add_argument("category", nargs="?", help="Slug of a puzzle category, defaults to all categories")

    def handle(self, *args, **options):
        categories = ChessPuzzleCategory.objects.all()
        if options["category"]:
            categories = categories.filter(slug=options["category"])
        for category in categories:
            coverage = Coverage.of(category)
            sides = ", ".join(f"{side} {coverage.perspectives[side]}" for side in ("white", "black"))
            self.stdout.write(self.style.MIGRATE_HEADING(f"{category.slug}: {coverage.total} puzzles ({sides})"))
            for tag in applicable_tags(category):
                marker = " (heuristic)" if tag.heuristic else ""
                self.stdout.write(f"  {coverage.tags[tag.slug]:>4}  {tag.kind.value:<8} {tag.slug}{marker}")
