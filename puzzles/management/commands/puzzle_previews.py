from django.core.management.base import BaseCommand

from puzzles import previews
from puzzles.models import ChessPuzzle


class Command(BaseCommand):
    help = "Draws the link previews that don't exist yet and removes outdated ones. " \
           "Previews also get drawn on their first request, so this is optional."

    def handle(self, *args, **options):
        puzzles = list(ChessPuzzle.objects.all())
        drawn = 0
        for puzzle in puzzles:
            path = previews.preview_path(puzzle)
            if not path.exists():
                previews.save_preview(puzzle, path)
                drawn += 1
        outdated = previews.outdated_previews(puzzles)
        for path in outdated:
            path.unlink()
        self.stdout.write(f"Drew {drawn} previews, removed {len(outdated)} outdated ones, "
                          f"{len(puzzles)} puzzles have a preview.")
