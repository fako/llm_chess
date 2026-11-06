from pathlib import Path

from django.apps import AppConfig
from django.conf import settings


class PuzzlesConfig(AppConfig):
    name = "puzzles"
    verbose_name = "Puzzles"

    def ready(self) -> None:
        from datagrowth.configuration import register_defaults
        from datagrowth.registry import DATAGROWTH_REGISTRY, Tag

        generation_dir = Path(settings.PUZZLE_GENERATION_DIR)
        register_defaults("anthropic", {"api_key": settings.ANTHROPIC_API_KEY})
        register_defaults("storage", {
            "directories": {
                "tmp": str(generation_dir / "tmp"),
                "project": str(settings.BASE_DIR),
                "data": str(generation_dir / "resources"),
                "snapshots": str(generation_dir / "snapshots"),
                "templates": str(Path(__file__).parent / "prompts"),
            },
        })
        DATAGROWTH_REGISTRY.register_directory(
            Tag(category="templates", value="puzzles"), Path(__file__).parent / "prompts"
        )
