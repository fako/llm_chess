"""
Link preview images of puzzles: the og:image that LinkedIn, Facebook, WhatsApp and others show with a shared link.

A preview is the starting position on a 1200x630 canvas, the size LinkedIn and Facebook show without cropping.
There is no text in the image, so one preview serves every language: the title and the "White to play and ..."
sentence travel next to it as og:title and og:description.

Previews get drawn on the first request for them and kept in MEDIA_ROOT, because a starting position never changes.
Their name holds a digest of everything that decides what they look like, so a changed position or a new DESIGN
gets a new name, which also tells platforms that cache previews to fetch the new one.

The pieces in assets/pieces are the cburnett set python-chess has, which the site uses too, rendered once to PNG
with resvg, because Pillow can't draw SVG.
"""
import hashlib
import os
import tempfile
from pathlib import Path

import chess
from django.conf import settings
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from puzzles.models import ChessPuzzle


DESIGN = 1  # raise this when the drawing changes, so that every preview gets drawn again

WIDTH, HEIGHT = 1200, 630
SCALE = 2  # drawn at twice the size and scaled down, which smooths edges, corners and text
SQUARE = 68
FRAME = (6, 1)  # the inner and outer border around the board, like .board in main.css
PIECE_RATIO = 0.92

PAPER = "#FAF6EE"
INK = (58, 46, 37)
FRAME_INNER = "#6F4A2F"
FRAME_OUTER = "#4E3420"
LIGHT_SQUARE = "#F1E9DA"
DARK_SQUARE = "#C9AE88"
LIGHT_COORDINATE = "#A8875E"
DARK_COORDINATE = "#F1E9DA"

PIECES_DIR = Path(__file__).resolve().parent / "assets" / "pieces"
PREVIEWS_DIR = "previews/puzzles"


def digest(puzzle: ChessPuzzle) -> str:
    return hashlib.sha256(f"{DESIGN}:{puzzle.fen}:{puzzle.perspective}".encode()).hexdigest()[:12]


def preview_path(puzzle: ChessPuzzle) -> Path:
    return Path(settings.MEDIA_ROOT) / PREVIEWS_DIR / f"{puzzle.pk}-{digest(puzzle)}.png"


def get_preview(puzzle: ChessPuzzle) -> Path:
    """
    The path of the preview of a puzzle, which gets drawn when it doesn't exist yet.
    """
    path = preview_path(puzzle)
    if not path.exists():
        save_preview(puzzle, path)
    return path


def save_preview(puzzle: ChessPuzzle, path: Path) -> None:
    # Saved under a temporary name first, so that two crawlers asking at once never get half a file
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as file:
            draw_preview(puzzle).save(file, format="PNG", optimize=True)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def outdated_previews(puzzles) -> list[Path]:
    """
    Previews of puzzles that changed or are gone, and previews of an earlier design.
    """
    directory = Path(settings.MEDIA_ROOT) / PREVIEWS_DIR
    if not directory.is_dir():
        return []
    current = {preview_path(puzzle).name for puzzle in puzzles}
    return [path for path in directory.iterdir() if path.name not in current]


#####################
# Drawing
#####################


def _piece_image(symbol: str, size: int) -> Image.Image:
    piece = chess.Piece.from_symbol(symbol)
    name = f"{chess.COLOR_NAMES[piece.color]}-{chess.PIECE_NAMES[piece.piece_type]}.png"
    with Image.open(PIECES_DIR / name) as image:
        return image.convert("RGBA").resize((size, size), Image.LANCZOS)


def draw_preview(puzzle: ChessPuzzle) -> Image.Image:
    """
    The starting position as the solving side sees it, like on the puzzle page: the side to play at the bottom.
    """
    square = SQUARE * SCALE
    inner, outer = FRAME[0] * SCALE, FRAME[1] * SCALE
    board_size = 8 * square
    framed = board_size + 2 * (inner + outer)
    left = (WIDTH * SCALE - framed) // 2
    top = (HEIGHT * SCALE - framed) // 2

    canvas = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), PAPER)

    # The shadow below the board
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (left, top + 8 * SCALE, left + framed, top + framed + 8 * SCALE), radius=12 * SCALE, fill=(*INK, 64),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(12 * SCALE))
    canvas.paste(shadow, (0, 0), shadow)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((left, top, left + framed - 1, top + framed - 1), radius=8 * SCALE, fill=FRAME_OUTER)
    draw.rounded_rectangle((left + outer, top + outer, left + framed - outer - 1, top + framed - outer - 1),
                           radius=7 * SCALE, fill=FRAME_INNER)

    board = puzzle.board
    color = puzzle.color
    ranks = range(7, -1, -1) if color == chess.WHITE else range(8)
    files = range(8) if color == chess.WHITE else range(7, -1, -1)
    origin_x, origin_y = left + outer + inner, top + outer + inner
    font = ImageFont.load_default(size=13 * SCALE)
    piece_size = round(square * PIECE_RATIO)
    piece_offset = (square - piece_size) // 2
    pieces = {}
    for row, rank in enumerate(ranks):
        for column, file in enumerate(files):
            x, y = origin_x + column * square, origin_y + row * square
            is_light = (file + rank) % 2 == 1
            draw.rectangle((x, y, x + square - 1, y + square - 1), fill=LIGHT_SQUARE if is_light else DARK_SQUARE)
            coordinate = LIGHT_COORDINATE if is_light else DARK_COORDINATE
            if column == 0:
                draw.text((x + 3 * SCALE, y + 2 * SCALE), str(rank + 1), font=font, fill=coordinate)
            if row == 7:
                draw.text((x + square - 3 * SCALE, y + square - 2 * SCALE), chess.FILE_NAMES[file], font=font,
                          fill=coordinate, anchor="rd")
            piece = board.piece_at(chess.square(file, rank))
            if piece:
                symbol = piece.symbol()
                if symbol not in pieces:
                    pieces[symbol] = _piece_image(symbol, piece_size)
                canvas.paste(pieces[symbol], (x + piece_offset, y + piece_offset), pieces[symbol])

    return canvas.resize((WIDTH, HEIGHT), Image.LANCZOS)
