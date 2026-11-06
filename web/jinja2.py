from pathlib import Path

import chess
import chess.svg
from django.apps import apps
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import reverse
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup


class HtmxLoader(FileSystemLoader):
    """
    Loads templates from the htmx directory of every installed project app.
    """
    def __init__(self) -> None:
        paths = []
        for config in apps.get_app_configs():
            htmx_dir = Path(settings.BASE_DIR) / config.label / "htmx"
            if htmx_dir.is_dir():
                paths.append(str(htmx_dir))
        super().__init__(paths)


def piece_id(symbol: str) -> str:
    piece = chess.Piece.from_symbol(symbol)
    return f"piece-{chess.COLOR_NAMES[piece.color]}-{chess.PIECE_NAMES[piece.piece_type]}"


def piece_sprite() -> Markup:
    """
    The python-chess piece set (cburnett) as SVG symbols, so the board can reference pieces with <use>.
    """
    symbols = []
    for symbol, svg in chess.svg.PIECES.items():
        symbols.append(f'<symbol id="{piece_id(symbol)}" viewBox="0 0 45 45">{svg}</symbol>')
    return Markup(f'<svg xmlns="http://www.w3.org/2000/svg" hidden>{"".join(symbols)}</svg>')


def environment(**options):
    options["loader"] = HtmxLoader()
    options.setdefault("autoescape", True)
    env = Environment(**options)
    env.globals["static"] = staticfiles_storage.url
    env.globals["url"] = reverse
    env.globals["piece_sprite"] = piece_sprite
    env.globals["piece_id"] = piece_id
    return env
