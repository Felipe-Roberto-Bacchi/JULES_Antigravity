"""Pixel-art sprite generator for the Jules desktop pet (24x22 grid + hue recoloring)."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap

from jules_pet.config import (
    BLUSH,
    BODY,
    EYE,
    EYE_GLINT,
    GRID_HEIGHT,
    GRID_WIDTH,
    HIGHLIGHT,
    OUTLINE,
    SHADOW,
)

PALETTE: dict[str, QColor] = {
    "O": QColor(OUTLINE),
    "B": QColor(BODY),
    "H": QColor(HIGHLIGHT),
    "S": QColor(SHADOW),
    "E": QColor(EYE),
    "G": QColor(EYE_GLINT),
    "P": QColor(BLUSH),
}

_SHIFTED_TOKENS: frozenset[str] = frozenset({"B", "H", "S"})

EYE_MODES: tuple[str, ...] = (
    "normal",
    "blink",
    "happy",
    "surprised",
    "sleep",
    "thinking",
    "coding",
    "scanning",
    "annoyed_side_eye",
    "shocked_ink",
    "high_five",
    "approval_waiting",
)

# 24x13 wide, slightly flattened dome head + upper body (rows 0..12)
HEAD_ROWS: tuple[str, ...] = (
    ".......OOOOOOOOOO.......",  # 0
    ".....OOBBBBBBBBBBOO.....",  # 1
    "....OBBHHHHBBBBBBBBO....",  # 2
    "...OBBHHHBBBBBBBBBBBO...",  # 3
    "..OBBHHBBBBBBBBBBBBBBO..",  # 4
    "..OBHBBBBBBBBBBBBBBBBO..",  # 5
    "..OBBBBBBBBBBBBBBBBBBO..",  # 6
    "..OBBBBBBBBBBBBBBBBBBO..",  # 7
    "..OBBBBBBBBBBBBBBBBBBO..",  # 8
    "..OBBBBBBBBBBBBBBBBBBO..",  # 9
    "..OBBBBBBBBBBBBBBBBBBO..",  # 10
    "..OSBBBBBBBBBBBBBBBBSO..",  # 11
    "..OSSBBBBBBBBBBBBBBSSO..",  # 12
)

# 24x9 lower body + 4 distinct articulated tentacles (rows 13..21)
TENTACLE_FRAMES: dict[str, tuple[str, ...]] = {
    "idle_0": (
        "..OBBSSBBBBBBBBBBSSBBO..",  # 13
        "..OBBOOBBBBOOBBBBOOBBO..",  # 14
        ".OBBO..OBBO..OBBO..OBBO.",  # 15
        ".OBO...OBBO..OBBO...OBO.",  # 16
        "OSSO...OBBO..OBBO...OSSO",  # 17
        "OOSS...OSSO..OSSO...SSOO",  # 18
        ".OOO...OOO....OOO...OOO.",  # 19
        "........................",  # 20
        "........................",  # 21
    ),
    "idle_1": (
        "..OBBSSBBBBBBBBBBSSBBO..",  # 13
        "...OBBOOBBBOOBBBOOBBO...",  # 14
        "...OBO..OBBOOBBO..OBO...",  # 15
        "...OBO..OBBOOBBO..OBO...",  # 16
        "...OSSO.OBBOOBBO.OSSO...",  # 17
        "....OOO.OSSOOSSO.OOO....",  # 18
        "........OOO..OOO........",  # 19
        "........................",  # 20
        "........................",  # 21
    ),
    "idle_2": (
        "..OBBSSBBBBBBBBBBSSBBO..",  # 13
        "...OOBBOBBBOOBBBOBBOO...",  # 14
        "....OBBOOBBOOBBOOBBO....",  # 15
        "....OBO.OBBOOBBO.OBO....",  # 16
        "....OBO.OBBOOBBO.OBO....",  # 17
        ".....OBOOBBOOBBOOBO.....",  # 18
        ".....OSSOSSOOSSOSSO.....",  # 19
        "......OOO.OOOO.OOO......",  # 20
        "........................",  # 21
    ),
    "idle_3": (
        "..OBBSSBBBBBBBBBBSSBBO..",  # 13
        "..OBBOOBBBBOOBBBBOOBBO..",  # 14
        ".OBBO..OBBO..OBBO..OBBO.",  # 15
        "OSSO...OBBO..OBBO...OSSO",  # 16
        "OOSS...OSSO..OSSO...SSOO",  # 17
        ".OOO...OOO....OOO...OOO.",  # 18
        "........................",  # 19
        "........................",  # 20
        "........................",  # 21
    ),
    "walk_0": (
        "..OBBSSBBBBBBBBBBSSBBO..",  # 13
        "..OBBOOBBBBOOBBBBOOBBO..",  # 14
        ".OBBO..OBBO..OBBO..OBBO.",  # 15
        "OSSO...OBBO..OSSO...OBO.",  # 16
        "OOO....OSSO..OOO....OSSO",  # 17
        ".......OOO...........OOO",  # 18
        "........................",  # 19
        "........................",  # 20
        "........................",  # 21
    ),
    "walk_1": (
        "..OBBSSBBBBBBBBBBSSBBO..",  # 13
        "..OBBOOBBBBOOBBBBOOBBO..",  # 14
        ".OBBO..OBBO..OBBO..OBBO.",  # 15
        ".OBO...OSSO..OBBO...OSSO",  # 16
        "OSSO...OOO...OSSO....OOO",  # 17
        "OOO..........OOO........",  # 18
        "........................",  # 19
        "........................",  # 20
        "........................",  # 21
    ),
    "drag_0": (
        "..OBBSSBBBBBBBBBBSSBBO..",  # 13
        "..OBBOOBBBBOOBBBBOOBBO..",  # 14
        "..OBO..OBBO..OBBO..OBO..",  # 15
        "..OBO..OBBO..OBBO..OBO..",  # 16
        "..OSSO..OBBO..OBBO..OBO.",  # 17
        "...OOO..OBBO..OBBO..OSSO",  # 18
        "........OSSO..OSSO...OOO",  # 19
        "........OOO...OOO.......",  # 20
        "........................",  # 21
    ),
    "drag_1": (
        "..OBBSSBBBBBBBBBBSSBBO..",  # 13
        "..OBBOOBBBBOOBBBBOOBBO..",  # 14
        "..OBO..OBBO..OBBO..OBO..",  # 15
        "..OBO..OBBO..OBBO..OBO..",  # 16
        ".OBO..OBBO..OBBO..OSSO..",  # 17
        "OSSO..OBBO..OBBO..OOO...",  # 18
        "OOO...OSSO..OSSO........",  # 19
        "......OOO...OOO.........",  # 20
        "........................",  # 21
    ),
    "coding_0": (
        "..OBBSSBBBBBBBBBBSSBBO..",  # 13
        "..OBBOOBBBBOOBBBBOOBBO..",  # 14
        ".OBBO..OBBO..OBBO..OBBO.",  # 15
        ".OSSO..OSSO..OSSO..OSSO.",  # 16
        "..OOO..OBBO..OBBO..OOO..",  # 17
        ".......OOO....OOO.......",  # 18
        "........................",  # 19
        "........................",  # 20
        "........................",  # 21
    ),
    "coding_1": (
        "..OBBSSBBBBBBBBBBSSBBO..",  # 13
        "..OBBOOBBBBOOBBBBOOBBO..",  # 14
        ".OBBO..OBBO..OBBO..OBBO.",  # 15
        ".OBO...OSSO..OBBO..OSSO.",  # 16
        ".OSSO..OOO...OSSO...OOO.",  # 17
        "..OOO........OOO........",  # 18
        "........................",  # 19
        "........................",  # 20
        "........................",  # 21
    ),
    "high_five_0": (
        "..OBBSSBBBBBBBBBBSSBBO..",  # 13
        ".OOBBOOBBBBOOBBBBOOBBOO.",  # 14
        "OSSO...OBBO..OBBO...OSSO",  # 15
        "OOO....OBBO..OBBO....OOO",  # 16
        ".......OSSO..OSSO.......",  # 17
        ".......OOO....OOO.......",  # 18
        "........................",  # 19
        "........................",  # 20
        "........................",  # 21
    ),
    "high_five_1": (
        ".OOBBSSBBBBBBBBBBSSBBOO.",  # 13
        "OSSO..OBBBBOOBBBBO..OSSO",  # 14
        "OOO....OBBO..OBBO....OOO",  # 15
        ".......OSSO..OSSO.......",  # 16
        ".......OOO....OOO.......",  # 17
        "........................",  # 18
        "........................",  # 19
        "........................",  # 20
        "........................",  # 21
    ),
    "sleep_0": (
        "..OBBSSBBBBBBBBBBSSBBO..",  # 13
        "..OBBOOBBBBOOBBBBOOBBO..",  # 14
        ".OBBO..OBBO..OBBO..OBBO.",  # 15
        ".OSSO..OSSO..OSSO..OSSO.",  # 16
        "..OOO..OOO....OOO..OOO..",  # 17
        "........................",  # 18
        "........................",  # 19
        "........................",  # 20
        "........................",  # 21
    ),
}

# Validate grid dimensions at import time
for _row in HEAD_ROWS:
    assert len(_row) == GRID_WIDTH, f"HEAD_ROWS width mismatch: {len(_row)}"
for _name, _rows in TENTACLE_FRAMES.items():
    assert len(_rows) == GRID_HEIGHT - len(HEAD_ROWS), f"{_name} height mismatch"
    for _row in _rows:
        assert len(_row) == GRID_WIDTH, f"{_name} width mismatch: {len(_row)}"


def recolor_palette(hue_shift: float = 0.0) -> dict[str, QColor]:
    """Return a palette with B/H/S shifted in HSV hue while preserving E/G/P/O contrast."""
    shift = hue_shift % 1.0
    if shift == 0.0:
        return {key: QColor(color) for key, color in PALETTE.items()}

    recolored: dict[str, QColor] = {}
    for key, base in PALETTE.items():
        if key in _SHIFTED_TOKENS:
            h, s, v, a = base.getHsvF()
            recolored[key] = QColor.fromHsvF((h + shift) % 1.0, s, v, a)
        else:
            recolored[key] = QColor(base)
    return recolored


def _fill_rect(
    grid: list[list[str]],
    xs: tuple[int, ...] | range,
    ys: tuple[int, ...] | range,
    token: str,
) -> None:
    """Paint a rectangular region of pixels in the logical sprite grid."""
    for y in ys:
        for x in xs:
            grid[y][x] = token


def _add_blush(grid: list[list[str]]) -> None:
    """Paint symmetrical pink cheeks beneath the eyes."""
    _fill_rect(grid, (4, 5, 18, 19), (9,), "P")


def _build_grid(
    frame_name: str,
    eye_mode: str,
    eye_dx: int,
    eye_dy: int,
) -> list[list[str]]:
    """Construct the 24x22 character grid for the given frame and eye expression."""
    rows = list(HEAD_ROWS) + list(TENTACLE_FRAMES[frame_name])
    grid = [list(r) for r in rows]

    # Clamp eye offset so eyes stay comfortably inside the dome outline
    dx = max(-1, min(1, eye_dx))
    dy = max(-1, min(1, eye_dy))

    # Base eye anchors (left: cols 7..8, right: cols 15..16, rows 6..8)
    lx = 7 + dx
    rx = 15 + dx
    ey = 6 + dy

    if eye_mode == "normal":
        _fill_rect(grid, (lx, lx + 1, rx, rx + 1), range(ey, ey + 3), "E")
    elif eye_mode == "blink":
        _fill_rect(grid, (lx - 1, lx, lx + 1, rx, rx + 1, rx + 2), (ey + 1,), "E")
    elif eye_mode == "happy":
        _fill_rect(grid, (7, 8, 15, 16), (6,), "E")
        _fill_rect(grid, (6, 9, 14, 17), (7,), "E")
        _add_blush(grid)
    elif eye_mode == "surprised":
        _fill_rect(grid, (6, 7, 8, 15, 16, 17), (6, 7, 8), "E")
        grid[6][6] = "G"
        grid[6][15] = "G"
        _add_blush(grid)
    elif eye_mode == "sleep":
        _fill_rect(grid, (6, 9, 14, 17), (7,), "E")
        _fill_rect(grid, (7, 8, 15, 16), (8,), "E")
    elif eye_mode == "thinking":
        _fill_rect(grid, (6, 7, 8), (7,), "E")
        _fill_rect(grid, (15, 16), (5, 6, 7), "E")
        grid[5][15] = "G"
    elif eye_mode == "coding":
        _fill_rect(grid, (6, 7, 8, 15, 16, 17), (6, 7), "E")
        _fill_rect(grid, (6, 7, 15, 16), (6,), "G")
    elif eye_mode == "scanning":
        _fill_rect(
            grid,
            (lx - 1, lx, lx + 1, rx, rx + 1, rx + 2),
            (ey, ey + 1),
            "E",
        )
        grid[ey][lx + 1] = "G"
        grid[ey][rx + 2] = "G"
    elif eye_mode == "annoyed_side_eye":
        _fill_rect(grid, (6, 7, 8, 15, 16, 17), (6,), "S")
        _fill_rect(grid, (6, 7, 15, 16), (7, 8), "G")
        _fill_rect(grid, (8, 17), (7, 8), "E")
    elif eye_mode == "shocked_ink":
        _fill_rect(grid, (6, 7, 8, 15, 16, 17), (6, 7, 8), "G")
        grid[7][7] = "E"
        grid[7][16] = "E"
        _add_blush(grid)
    elif eye_mode == "high_five":
        _fill_rect(grid, (7, 8, 15, 16), (6, 7, 8), "E")
        grid[6][7] = "G"
        grid[8][8] = "G"
        grid[6][15] = "G"
        grid[8][16] = "G"
        _add_blush(grid)
    elif eye_mode == "approval_waiting":
        _fill_rect(grid, (6, 7, 8, 15, 16, 17), (6, 7, 8), "E")
        _fill_rect(grid, (6, 7, 15, 16), (6,), "G")
        grid[7][6] = "G"
        grid[7][15] = "G"
        grid[9][5] = "P"
        grid[9][18] = "P"
    else:
        _fill_rect(grid, (lx, lx + 1, rx, rx + 1), range(ey, ey + 3), "E")

    return grid


@lru_cache(maxsize=512)
def _render_sprite_pixmap(
    frame_name: str,
    eye_mode: str,
    eye_dx: int,
    eye_dy: int,
    scale: int,
    flip_x: bool,
    quantized_hue: float,
) -> QPixmap:
    palette = recolor_palette(quantized_hue)
    grid = _build_grid(frame_name, eye_mode, eye_dx, eye_dy)
    img = QImage(GRID_WIDTH, GRID_HEIGHT, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)

    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch != ".":
                draw_x = (GRID_WIDTH - 1 - x) if flip_x else x
                img.setPixelColor(draw_x, y, palette[ch])

    scaled = img.scaled(
        GRID_WIDTH * scale,
        GRID_HEIGHT * scale,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
    return QPixmap.fromImage(scaled)


def get_sprite_pixmap(
    frame_name: str,
    eye_mode: str = "normal",
    eye_dx: int = 0,
    eye_dy: int = 0,
    scale: int = 4,
    flip_x: bool = False,
    hue_shift: float = 0.0,
) -> QPixmap:
    """Render and cache a crisp nearest-neighbor pixel-art QPixmap for Jules."""
    if frame_name not in TENTACLE_FRAMES:
        frame_name = "idle_0"

    dx = max(-1, min(1, eye_dx))
    dy = max(-1, min(1, eye_dy))
    quantized_hue = round(hue_shift % 1.0, 3)
    if quantized_hue == 1.0:
        quantized_hue = 0.0

    return _render_sprite_pixmap(
        frame_name,
        eye_mode,
        dx,
        dy,
        scale,
        flip_x,
        quantized_hue,
    )


get_sprite_pixmap.cache_info = _render_sprite_pixmap.cache_info  # type: ignore[attr-defined]
get_sprite_pixmap.cache_clear = _render_sprite_pixmap.cache_clear  # type: ignore[attr-defined]


def create_tray_icon() -> QIcon:
    """Create a crisp pixel-art Jules icon for the Windows system tray."""
    pixmap = get_sprite_pixmap("idle_0", "normal", 0, 0, scale=2, flip_x=False)
    return QIcon(pixmap)
