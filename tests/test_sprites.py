"""Unit tests for the 24x22 Jules pixel-art sprite engine and hue recoloring."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from jules_pet.config import GRID_HEIGHT, GRID_WIDTH, PIXEL_SCALES
from jules_pet.sprites import (
    TENTACLE_FRAMES,
    create_tray_icon,
    get_sprite_pixmap,
    recolor_palette,
)

EXPECTED_FRAMES: tuple[str, ...] = (
    "idle_0",
    "idle_1",
    "idle_2",
    "idle_3",
    "walk_0",
    "walk_1",
    "drag_0",
    "drag_1",
    "coding_0",
    "coding_1",
    "high_five_0",
    "high_five_1",
    "sleep_0",
)

EXPECTED_EYE_MODES: tuple[str, ...] = (
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


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _count_opaque_segments(img, row: int) -> int:
    segments = 0
    in_segment = False
    for x in range(img.width()):
        opaque = img.pixelColor(x, row).alpha() > 0
        if opaque and not in_segment:
            segments += 1
            in_segment = True
        elif not opaque:
            in_segment = False
    return segments


def test_grid_dimensions_are_24x22() -> None:
    assert GRID_WIDTH == 24
    assert GRID_HEIGHT == 22


def test_all_scales_frames_and_eye_modes_render(qapp: QApplication) -> None:
    for frame in EXPECTED_FRAMES:
        assert frame in TENTACLE_FRAMES

    for scale in PIXEL_SCALES.values():
        for frame in EXPECTED_FRAMES:
            for eye_mode in EXPECTED_EYE_MODES:
                pix = get_sprite_pixmap(frame, eye_mode=eye_mode, scale=scale)
                assert not pix.isNull()
                assert pix.width() == 24 * scale
                assert pix.height() == 22 * scale
                img = pix.toImage()
                assert img.pixelColor(0, 0).alpha() == 0
                assert img.pixelColor(pix.width() - 1, 0).alpha() == 0
                assert img.pixelColor(0, pix.height() - 1).alpha() == 0
                assert img.pixelColor(pix.width() - 1, pix.height() - 1).alpha() == 0


def test_silhouette_has_four_distinct_tentacles(qapp: QApplication) -> None:
    pix = get_sprite_pixmap("idle_0", eye_mode="normal", scale=1)
    img = pix.toImage()
    assert img.width() == 24
    assert img.height() == 22

    # Lower tentacle rows (row 17 and row 18) must clearly show 4 separated segments
    segments_by_row = [_count_opaque_segments(img, r) for r in (17, 18)]
    assert any(count == 4 for count in segments_by_row), (
        f"Expected 4 distinct tentacle segments in row 17 or 18, got {segments_by_row}"
    )


def test_hue_recoloring_palette_and_sprite(qapp: QApplication) -> None:
    base_palette = recolor_palette(0.0)
    shifted_palette = recolor_palette(0.35)

    for key in ("O", "B", "H", "S", "E", "G", "P"):
        assert key in base_palette
        assert key in shifted_palette
        assert isinstance(base_palette[key], QColor)
        assert isinstance(shifted_palette[key], QColor)
        assert base_palette[key].isValid()
        assert shifted_palette[key].isValid()

    assert shifted_palette["B"].rgb() != base_palette["B"].rgb()
    assert shifted_palette["H"].rgb() != base_palette["H"].rgb()
    assert shifted_palette["S"].rgb() != base_palette["S"].rgb()

    # Contrast/accent tokens remain intact
    assert shifted_palette["E"].rgb() == base_palette["E"].rgb()
    assert shifted_palette["G"].rgb() == base_palette["G"].rgb()
    assert shifted_palette["P"].rgb() == base_palette["P"].rgb()
    assert shifted_palette["O"].rgb() == base_palette["O"].rgb()

    img_base = get_sprite_pixmap("idle_0", "normal", scale=1, hue_shift=0.0).toImage()
    img_shifted = get_sprite_pixmap("idle_0", "normal", scale=1, hue_shift=0.35).toImage()

    # Sample body pixel in the middle of the dome (row 5, col 12)
    c_base = img_base.pixelColor(12, 5)
    c_shifted = img_shifted.pixelColor(12, 5)
    assert c_base.alpha() == 255
    assert c_shifted.alpha() == 255
    assert c_shifted.rgb() != c_base.rgb()


def test_create_tray_icon_returns_valid_icon(qapp: QApplication) -> None:
    icon = create_tray_icon()
    assert not icon.isNull()


def test_hue_quantization_and_flip_x(qapp: QApplication) -> None:
    get_sprite_pixmap.cache_clear()
    p1 = get_sprite_pixmap("idle_0", "normal", scale=2, hue_shift=0.3501)
    p2 = get_sprite_pixmap("idle_0", "normal", scale=2, hue_shift=0.3504)
    p3 = get_sprite_pixmap("idle_0", "normal", scale=2, hue_shift=1.35)
    info = get_sprite_pixmap.cache_info()
    assert info.misses == 1
    assert info.hits == 2
    assert p1.cacheKey() == p2.cacheKey() == p3.cacheKey()

    # Flipping horizontally mirrors asymmetric highlight pixels (top-left dome highlight)
    img_normal = get_sprite_pixmap("idle_0", "normal", scale=1, flip_x=False).toImage()
    img_flipped = get_sprite_pixmap("idle_0", "normal", scale=1, flip_x=True).toImage()
    assert img_normal.pixelColor(7, 2).rgb() == img_flipped.pixelColor(24 - 1 - 7, 2).rgb()
    assert img_normal.pixelColor(7, 2).rgb() != img_normal.pixelColor(24 - 1 - 7, 2).rgb()


def _row_span(img, row: int) -> int:
    xs = [x for x in range(img.width()) if img.pixelColor(x, row).alpha() > 0]
    if not xs:
        return 0
    return max(xs) - min(xs) + 1


def test_idle_squeeze_and_flare_hydrodynamic_cycle(qapp: QApplication) -> None:
    imgs = {
        name: get_sprite_pixmap(name, eye_mode="normal", scale=1).toImage()
        for name in ("idle_0", "idle_1", "idle_2", "idle_3")
    }

    # idle_0 (Repouso / Planando): flared out to edges with 4 distinct tentacles
    assert _row_span(imgs["idle_0"], 17) >= 22
    assert _count_opaque_segments(imgs["idle_0"], 17) == 4

    # idle_1 (Contração / Squeeze): narrower than idle_0
    assert _row_span(imgs["idle_1"], 17) < _row_span(imgs["idle_0"], 17)

    # idle_2 (Propulsão): even narrower at row 18 and stretches down to row 20
    assert _row_span(imgs["idle_2"], 18) < _row_span(imgs["idle_1"], 18)
    assert _row_span(imgs["idle_2"], 20) > 0

    # idle_3 (Abertura / Flare): opens wide again with 4 distinct tentacles
    assert _row_span(imgs["idle_3"], 17) > _row_span(imgs["idle_2"], 17)
    assert _row_span(imgs["idle_3"], 17) >= 22
    assert _count_opaque_segments(imgs["idle_3"], 17) == 4
