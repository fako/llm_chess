from django.core.management.base import BaseCommand, CommandError

from puzzles.generation import generate_puzzles
from puzzles.models import ChessPuzzleCategory, Effort, LLM
from puzzles.tags import applicable_tags, parse_tags


class Command(BaseCommand):
    help = "Generates puzzles for a category with an LLM and stores the ones that the solver verifies."

    def add_arguments(self, parser):
        parser.add_argument("category", help="Slug of the puzzle category, for instance mate-in-2")
        parser.add_argument("count", type=int, help="Amount of verified puzzles to create")
        parser.add_argument("--max-requests", type=int, default=None,
                            help="Maximum amount of LLM requests, defaults to max(3, count)")
        parser.add_argument("--batch-size", type=int, default=None,
                            help="Puzzles to ask for per request, defaults to twice the amount still needed")
        parser.add_argument("--model", default=None, choices=LLM.values,
                            help="The LLM that generates puzzles, defaults to the model of the category")
        parser.add_argument("--effort", default=None, choices=Effort.values,
                            help="How much the LLM thinks per request, defaults to the effort of the category")
        parser.add_argument("--tags", default="",
                            help="Comma separated tags every request asks for (see puzzles/tags.py). "
                                 "Without it every request picks tags the category has few puzzles of")
        parser.add_argument("--no-tags", action="store_true",
                            help="Don't ask for tags or a solving side, and let the LLM pick freely")

    def handle(self, *args, **options):
        try:
            category = ChessPuzzleCategory.objects.get(slug=options["category"])
        except ChessPuzzleCategory.DoesNotExist:
            slugs = ", ".join(ChessPuzzleCategory.objects.values_list("slug", flat=True))
            raise CommandError(f"Unknown category '{options['category']}'. Available: {slugs}")

        try:
            tags = parse_tags(category, [slug.strip() for slug in options["tags"].split(",") if slug.strip()])
        except ValueError as error:
            available = ", ".join(tag.slug for tag in applicable_tags(category))
            raise CommandError(f"{error}. Available for {category.slug}: {available}")

        report = generate_puzzles(category, options["count"], max_requests=options["max_requests"],
                                  model=options["model"], effort=options["effort"],
                                  batch_size=options["batch_size"], tags=tags, balance=not options["no_tags"])
        self.stdout.write(f"generated with {report.model} at {report.effort} effort")

        for puzzle in report.created:
            requested = ", ".join(puzzle.generation["requested_tags"]) or "-"
            self.stdout.write(self.style.SUCCESS(
                f"created #{puzzle.pk} {puzzle.fen} asked: {requested} got: {', '.join(puzzle.tags) or '-'}"
            ))
        for rejection in report.rejected:
            self.stdout.write(f"rejected {rejection.fen}: {rejection.reason}")
        for slug, requested in report.requested_tags.items():
            self.stdout.write(f"tag {slug}: {report.matched_tags[slug]}/{requested} puzzles have it")
        for error in report.errors:
            self.stdout.write(self.style.ERROR(error))
        self.stdout.write(
            f"{len(report.created)}/{report.requested} puzzles created in {report.requests} requests, "
            f"{len(report.rejected)} proposals rejected, tokens: {report.tokens}"
        )
