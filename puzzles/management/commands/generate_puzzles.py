from django.core.management.base import BaseCommand, CommandError

from puzzles.generation import generate_puzzles
from puzzles.models import ChessPuzzleCategory


class Command(BaseCommand):
    help = "Generates puzzles for a category with an LLM and stores the ones that the solver verifies."

    def add_arguments(self, parser):
        parser.add_argument("category", help="Slug of the puzzle category, for instance mate-in-2")
        parser.add_argument("count", type=int, help="Amount of verified puzzles to create")
        parser.add_argument("--max-requests", type=int, default=None,
                            help="Maximum amount of LLM requests, defaults to max(3, count)")
        parser.add_argument("--batch-size", type=int, default=None,
                            help="Puzzles to ask for per request, defaults to twice the amount still needed")
        parser.add_argument("--effort", default="low", choices=["low", "medium", "high", "xhigh", "max"],
                            help="How much the LLM thinks per request, more effort costs more tokens")

    def handle(self, *args, **options):
        try:
            category = ChessPuzzleCategory.objects.get(slug=options["category"])
        except ChessPuzzleCategory.DoesNotExist:
            slugs = ", ".join(ChessPuzzleCategory.objects.values_list("slug", flat=True))
            raise CommandError(f"Unknown category '{options['category']}'. Available: {slugs}")

        report = generate_puzzles(category, options["count"], max_requests=options["max_requests"],
                                  batch_size=options["batch_size"], effort=options["effort"])

        for puzzle in report.created:
            self.stdout.write(self.style.SUCCESS(
                f"created #{puzzle.pk} {puzzle.fen} ({len(puzzle.branches)} branches)"
            ))
        for rejection in report.rejected:
            self.stdout.write(f"rejected {rejection.fen}: {rejection.reason}")
        for error in report.errors:
            self.stdout.write(self.style.ERROR(error))
        self.stdout.write(
            f"{len(report.created)}/{report.requested} puzzles created in {report.requests} requests, "
            f"{len(report.rejected)} proposals rejected, tokens: {report.tokens}"
        )
