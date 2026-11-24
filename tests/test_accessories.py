"""Unit tests for Jules official accessories and custom modding engine."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from jules_pet.accessories_manager import (
    AccessoriesManager,
    AccessorySpec,
    default_custom_accessory_dirs,
    render_accessory_pixmap,
)


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_transparent_png(path: Path, width: int, height: int, pixels: dict[tuple[int, int], str]) -> None:
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    for (x, y), hex_color in pixels.items():
        img.setPixelColor(x, y, QColor(hex_color))
    assert img.save(str(path), "PNG")


def test_builtin_accessories_resolution_and_no_space_helmet(tmp_path: Path) -> None:
    mgr = AccessoriesManager(custom_dirs=[tmp_path])
    builtin_ids = {spec.id for spec in mgr.list_builtins()}

    assert builtin_ids == {"dev_glasses", "detective_loupe", "hard_hat"}
    assert "space_helmet" not in builtin_ids
    assert mgr.get("space_helmet") is None

    dev_edit = mgr.resolve_active_accessory("auto", "", "edit_write", 0)
    assert dev_edit is not None
    assert dev_edit.id == "dev_glasses"

    dev_term = mgr.resolve_active_accessory("auto", "", "terminal", 0)
    assert dev_term is not None
    assert dev_term.id == "dev_glasses"

    loupe = mgr.resolve_active_accessory("auto", "", "read_search", 0)
    assert loupe is not None
    assert loupe.id == "detective_loupe"

    hard_hat = mgr.resolve_active_accessory("auto", "", "", 2)
    assert hard_hat is not None
    assert hard_hat.id == "hard_hat"

    hard_hat_over_tool = mgr.resolve_active_accessory("auto", "", "edit_write", 2)
    assert hard_hat_over_tool is not None
    assert hard_hat_over_tool.id == "hard_hat"

    assert mgr.resolve_active_accessory("none", "", "edit_write", 2) is None
    assert mgr.resolve_active_accessory("auto", "", "", 0) is None


def test_custom_png_and_json_loader(qapp: QApplication, tmp_path: Path) -> None:
    png_path = tmp_path / "monoculo.png"
    _make_transparent_png(
        png_path,
        12,
        10,
        {
            (2, 3): "#FACC15",
            (3, 3): "#38BDF8",
            (2, 4): "#140B29",
        },
    )
    meta_path = tmp_path / "monoculo.json"
    meta_path.write_text(
        json.dumps(
            {
                "name": "Monóculo Elegante",
                "anchor": "eyes",
                "offset_x": 1,
                "offset_y": 0,
                "scale_with_pet": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    mgr = AccessoriesManager(custom_dirs=[tmp_path])
    spec = mgr.resolve_active_accessory("custom", "monoculo", "", 0)
    assert isinstance(spec, AccessorySpec)
    assert spec.id == "monoculo"
    assert spec.name == "Monóculo Elegante"
    assert spec.anchor == "eyes"
    assert spec.offset_x == 1
    assert spec.offset_y == 0
    assert spec.scale_with_pet is True
    assert spec.builtin is False

    pixmap, draw_x, draw_y = render_accessory_pixmap(spec, scale=4, flip_x=False)
    assert isinstance(pixmap, QPixmap)
    assert not pixmap.isNull()
    assert pixmap.width() == 12 * 4
    assert pixmap.height() == 10 * 4
    assert isinstance(draw_x, int)
    assert isinstance(draw_y, int)


def test_custom_matrix_json_and_txt_loaders(qapp: QApplication, tmp_path: Path) -> None:
    json_matrix = tmp_path / "coroa.json"
    json_matrix.write_text(
        json.dumps(
            {
                "name": "Coroa Pixel",
                "anchor": "head_top",
                "offset_x": 0,
                "offset_y": 0,
                "scale_with_pet": True,
                "palette": {
                    "Y": "#FACC15",
                    "W": "#FFFFFF",
                },
                "rows": [
                    "Y..W..Y",
                    "YYYYYYY",
                ],
            }
        ),
        encoding="utf-8",
    )

    txt_matrix = tmp_path / "laco.txt"
    txt_matrix.write_text(
        "\n".join(
            [
                "name: Laço Rosa",
                "anchor: head_top",
                "offset_x: 2",
                "offset_y: 1",
                "P=#F472B6",
                "O=#140B29",
                "",
                "PP.PP",
                "POPOP",
                "PP.PP",
            ]
        ),
        encoding="utf-8",
    )

    mgr = AccessoriesManager(custom_dirs=[tmp_path])
    coroa = mgr.resolve_active_accessory("custom", "coroa", "", 0)
    laco = mgr.resolve_active_accessory("custom", "laco", "", 0)

    assert coroa is not None
    assert coroa.name == "Coroa Pixel"
    pix_coroa, _, _ = render_accessory_pixmap(coroa, scale=3, flip_x=False)
    assert not pix_coroa.isNull()
    assert pix_coroa.width() == 7 * 3
    assert pix_coroa.height() == 2 * 3

    assert laco is not None
    assert laco.name == "Laço Rosa"
    assert laco.offset_x == 2
    assert laco.offset_y == 1
    pix_laco, _, _ = render_accessory_pixmap(laco, scale=4, flip_x=False)
    assert not pix_laco.isNull()
    assert pix_laco.width() == 5 * 4
    assert pix_laco.height() == 3 * 4


def test_corrupt_json_and_missing_png_skipped_gracefully(qapp: QApplication, tmp_path: Path) -> None:
    (tmp_path / "quebrado.json").write_text("{not valid json", encoding="utf-8")
    (tmp_path / "fantasma.json").write_text(
        json.dumps({"name": "Fantasma", "anchor": "head_top"}),
        encoding="utf-8",
    )
    (tmp_path / "referencia_quebrada.json").write_text(
        json.dumps({"name": "Sem PNG", "image": "inexistente.png"}),
        encoding="utf-8",
    )
    (tmp_path / "vazio.txt").write_text("# apenas comentario\n", encoding="utf-8")

    # Valid sibling still loads
    _make_transparent_png(tmp_path / "valido.png", 6, 4, {(1, 1): "#38BDF8"})

    mgr = AccessoriesManager(custom_dirs=[tmp_path])
    assert mgr.get("quebrado") is None
    assert mgr.get("fantasma") is None
    assert mgr.get("referencia_quebrada") is None
    assert mgr.get("vazio") is None

    valido = mgr.resolve_active_accessory("custom", "valido", "", 0)
    assert valido is not None
    pix, _, _ = render_accessory_pixmap(valido, scale=2, flip_x=False)
    assert not pix.isNull()


def test_render_accessory_pixmap_nearest_neighbor_and_flip_x(qapp: QApplication, tmp_path: Path) -> None:
    # Asymmetric custom matrix so flip_x is unambiguously verifiable
    asym_path = tmp_path / "assim.json"
    asym_path.write_text(
        json.dumps(
            {
                "name": "Assimétrico",
                "anchor": "eyes",
                "offset_x": 1,
                "offset_y": 0,
                "scale_with_pet": True,
                "palette": {"R": "#EF4444", "B": "#38BDF8"},
                "rows": [
                    "R...",
                    "..BB",
                ],
            }
        ),
        encoding="utf-8",
    )
    mgr = AccessoriesManager(custom_dirs=[tmp_path])
    spec = mgr.resolve_active_accessory("custom", "assim", "", 0)
    assert spec is not None

    pix_normal, dx_normal, dy_normal = render_accessory_pixmap(spec, scale=4, flip_x=False)
    pix_flipped, dx_flipped, dy_flipped = render_accessory_pixmap(spec, scale=4, flip_x=True)

    assert not pix_normal.isNull()
    assert not pix_flipped.isNull()
    assert pix_normal.size() == pix_flipped.size()
    assert pix_normal.width() == 4 * 4
    assert pix_normal.height() == 2 * 4
    assert dy_normal == dy_flipped
    assert dx_normal == -dx_flipped or dx_normal != dx_flipped

    img_n = pix_normal.toImage()
    img_f = pix_flipped.toImage()

    # Nearest-neighbor block check: entire 4x4 block at (0..3, 0..3) is solid red
    for py in range(4):
        for px in range(4):
            assert img_n.pixelColor(px, py) == QColor("#EF4444")
            # Mirrored: red block moves to rightmost 4x4 block (12..15, 0..3)
            assert img_f.pixelColor(12 + px, py) == QColor("#EF4444")
            assert img_f.pixelColor(px, py).alpha() == 0

    # Built-ins also render non-null and flip horizontally cleanly
    for builtin_id in ("dev_glasses", "detective_loupe", "hard_hat"):
        b_spec = mgr.get(builtin_id)
        assert b_spec is not None
        bp_n, _, _ = render_accessory_pixmap(b_spec, scale=4, flip_x=False)
        bp_f, _, _ = render_accessory_pixmap(b_spec, scale=4, flip_x=True)
        assert not bp_n.isNull()
        assert not bp_f.isNull()
        assert bp_n.size() == bp_f.size()


def test_default_custom_accessory_dirs() -> None:
    dirs = default_custom_accessory_dirs()
    assert len(dirs) == 2
    assert dirs[1].name == "custom"
    assert dirs[1].parent.name == "accessories"
