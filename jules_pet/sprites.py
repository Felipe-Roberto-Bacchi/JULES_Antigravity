"""Pixel-art sprite generator for the Jules desktop pet."""

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

# 18x13 dome head + upper body (rows 0..12)
HEAD_ROWS: tuple[str, ...] = (
    "......OOOOOO......",  # 0
    "....OOBBBBBBOO....",  # 1
    "...OBBHHHBBBBBO...",  # 2
    "..OBBHHBBBBBBBBO..",  # 3
    "..OBHBBBBBBBBBBO..",  # 4
    "..OBBBBBBBBBBBBO..",  # 5
    "..OBBBBBBBBBBBBO..",  # 6
    "..OBBBBBBBBBBBBO..",  # 7
    "..OBBBBBBBBBBBBO..",  # 8
    "..OBBBBBBBBBBBBO..",  # 9
    "..OBBBBBBBBBBBBO..",  # 10
    "..OSBBBBBBBBBBSO..",  # 11
)

# 18x8 lower body + 4 tentacles (rows 12..19) for each animation frame
TENTACLE_FRAMES: dict[str, tuple[str, ...]] = {
    "idle_0": (
        "..OBBSSBBBBSSBBO..",  # 12
        "..OBBOOBBBBOOBBO..",  # 13
        ".OBBO.OBBBO.OBBO..",  # 14
        ".OBO..OBBO..OBO...",  # 15
        "OSSO..OBBO..OSSO..",  # 16
        "OOO...OSSO...OOO..",  # 17
        "......OOOO........",  # 18
        "..................",  # 19
    ),
    "idle_1": (
        "..OBBSSBBBBSSBBO..",  # 12
        "..OBBOOBBBBOOBBO..",  # 13
        ".OBBO.OBBBO.OBBO..",  # 14
        "OBBO..OBBO..OBBO..",  # 15
        "OSSO..OSSO..OSSO..",  # 16
        ".OOO...OO....OOO..",  # 17
        "..................",  # 18
        "..................",  # 19
    ),
    "idle_2": (
        "..OBBSSBBBBSSBBO..",  # 12
        "..OBBOOBBBBOOBBO..",  # 13
        ".OBBO.OBBBO.OBBO..",  # 14
        ".OBO..OBBO..OBO...",  # 15
        ".OSSO.OBBO.OSSO...",  # 16
        "..OOO.OSSO.OOO....",  # 17
        "......OOOO........",  # 18
        "..................",  # 19
    ),
    "idle_3": (
        "..OBBSSBBBBSSBBO..",  # 12
        "..OBBOOBBBBOOBBO..",  # 13
        "..OBO.OBBBO.OBO...",  # 14
        ".OBBO.OBBO..OBBO..",  # 15
        ".OSSO.OSSO..OSSO..",  # 16
        "..OOO..OO....OOO..",  # 17
        "..................",  # 18
        "..................",  # 19
    ),
    "walk_0": (
        "..OBBSSBBBBSSBBO..",  # 12
        "..OBBOOBBBBOOBBO..",  # 13
        ".OBBO.OBBBO.OBBO..",  # 14
        "OBBO..OBBO...OBO..",  # 15
        "OSSO..OSSO...OSSO.",  # 16
        ".OOO...OO.....OOO.",  # 17
        "..................",  # 18
        "..................",  # 19
    ),
    "walk_1": (
        "..OBBSSBBBBSSBBO..",  # 12
        "..OBBOOBBBBOOBBO..",  # 13
        ".OBBO.OBBBO.OBBO..",  # 14
        ".OBO..OBBO..OBBO..",  # 15
        "OSSO..OBBO..OSSO..",  # 16
        "OOO...OSSO...OOO..",  # 17
        "..................",  # 18
        "..................",  # 19
    ),
    "drag_0": (
        "..OBBSSBBBBSSBBO..",  # 12
        "..OBBOOBBBBOOBBO..",  # 13
        "..OBO.OBBBO.OBO...",  # 14
        "..OBO.OBBO..OBO...",  # 15
        "..OSSOOBBO..OSSO..",  # 16
        "...OOO.OSSO..OOO..",  # 17
        ".......OOOO.......",  # 18
        "..................",  # 19
    ),
    "drag_1": (
        "..OBBSSBBBBSSBBO..",  # 12
        "..OBBOOBBBBOOBBO..",  # 13
        "..OBO.OBBBO.OBO...",  # 14
        "..OBO..OBBO.OBO...",  # 15
        ".OSSO..OBBOOSSO...",  # 16
        ".OOO...OSSO.OOO...",  # 17
        ".......OOOO.......",  # 18
        "..................",  # 19
    ),
    "sleep_0": (
        "..OBBSSBBBBSSBBO..",  # 12
        "..OBBOOBBBBOOBBO..",  # 13
        ".OBBO.OBBBO.OBBO..",  # 14
        "OSSO..OSSO..OSSO..",  # 15
        "OOO....OO....OOO..",  # 16
        "..................",  # 17
        "..................",  # 18
        "..................",  # 19
    ),
}

# Validate grid dimensions at import time
for _row in HEAD_ROWS:
    assert len(_row) == GRID_WIDTH, f"HEAD_ROWS width mismatch: {len(_row)}"
for _name, _rows in TENTACLE_FRAMES.items():
    assert len(_rows) == GRID_HEIGHT - len(HEAD_ROWS), f"{_name} height mismatch"
    for _row in _rows:
        assert len(_row) == GRID_WIDTH, f"{_name} width mismatch: {len(_row)}"


def _build_grid(
    frame_name: str,
    eye_mode: str,
    eye_dx: int,
    eye_dy: int,
) -> list[list[str]]:
    """Construct the 18x20 character grid for the given frame and eye expression."""
    rows = list(HEAD_ROWS) + list(TENTACLE_FRAMES[frame_name])
    grid = [list(r) for r in rows]

    # Clamp eye offset so eyes never touch the outline
    dx = max(-1, min(1, eye_dx))
    dy = max(-1, min(1, eye_dy))

    # Base eye centers (left: col 5..6, right: col 11..12, row 6..7)
    lx = 5 + dx
    rx = 11 + dx
    ey = 6 + dy

    if eye_mode == "normal":
        for x in (lx, lx + 1, rx, rx + 1):
            grid[ey][x] = "E"
            grid[ey + 1][x] = "E"
    elif eye_mode == "blink":
        for x in (5, 6, 11, 12):
            grid[7][x] = "E"
    elif eye_mode == "happy":
        # ^ ^ happy squint eyes + pink blush
        grid[6][5] = "E"
        grid[6][6] = "E"
        grid[7][4] = "E"
        grid[7][7] = "E"

        grid[6][11] = "E"
        grid[6][12] = "E"
        grid[7][10] = "E"
        grid[7][13] = "E"

        grid[9][4] = "P"
        grid[9][5] = "P"
        grid[9][12] = "P"
        grid[9][13] = "P"
    elif eye_mode == "surprised":
        # Wide eyes with white glint
        for x in (5, 6, 11, 12):
            grid[6][x] = "E"
            grid[7][x] = "E"
            grid[8][x] = "E"
        grid[6][5] = "G"
        grid[6][11] = "G"
        grid[9][4] = "P"
        grid[9][13] = "P"
    elif eye_mode == "sleep":
        # Relaxed closed eyes
        grid[7][5] = "E"
        grid[7][6] = "E"
        grid[8][4] = "E"
        grid[8][7] = "E"

        grid[7][11] = "E"
        grid[7][12] = "E"
        grid[8][10] = "E"
        grid[8][13] = "E"

    return grid


@lru_cache(maxsize=256)
def get_sprite_pixmap(
    frame_name: str,
    eye_mode: str = "normal",
    eye_dx: int = 0,
    eye_dy: int = 0,
    scale: int = 4,
    flip_x: bool = False,
) -> QPixmap:
    """Render and cache a crisp nearest-neighbor pixel-art QPixmap for Jules."""
    if frame_name not in TENTACLE_FRAMES:
        frame_name = "idle_0"

    grid = _build_grid(frame_name, eye_mode, eye_dx, eye_dy)
    img = QImage(GRID_WIDTH, GRID_HEIGHT, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)

    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch != ".":
                draw_x = (GRID_WIDTH - 1 - x) if flip_x else x
                img.setPixelColor(draw_x, y, PALETTE[ch])

    scaled = img.scaled(
        GRID_WIDTH * scale,
        GRID_HEIGHT * scale,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
    return QPixmap.fromImage(scaled)


def create_tray_icon() -> QIcon:
    """Create a crisp pixel-art Jules icon for the Windows system tray."""
    pixmap = get_sprite_pixmap("idle_0", "normal", 0, 0, scale=2, flip_x=False)
    return QIcon(pixmap)
