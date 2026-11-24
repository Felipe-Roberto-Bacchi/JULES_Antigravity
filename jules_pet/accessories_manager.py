"""Official pixel-art accessories and custom modding engine for Jules Desktop Pet."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap

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

BUILTIN_ACCESSORIES: tuple[str, ...] = (
    "dev_glasses",
    "detective_loupe",
    "hard_hat",
)

VALID_ANCHORS: frozenset[str] = frozenset({"head_top", "eyes", "body", "full"})

DEFAULT_TXT_PALETTE: dict[str, str] = {
    "O": OUTLINE,
    "B": BODY,
    "H": HIGHLIGHT,
    "S": SHADOW,
    "E": EYE,
    "G": EYE_GLINT,
    "P": BLUSH,
    "K": "#140B29",
    "W": "#FFFFFF",
    "R": "#EF4444",
    "Y": "#FACC15",
    "C": "#38BDF8",
    "M": "#A855F7",
    "N": "#22C55E",
}


@dataclass(frozen=True)
class AccessorySpec:
    """Descriptor for either a built-in or user-modded pixel-art accessory."""

    id: str
    name: str
    anchor: str = "head_top"
    offset_x: int = 0
    offset_y: int = 0
    scale_with_pet: bool = True
    builtin: bool = False
    source_kind: str = "matrix"
    rows: tuple[str, ...] = ()
    palette: dict[str, str] = field(default_factory=dict)
    image_path: Path | None = None
    base_width: int = 0
    base_height: int = 0


def _build_builtin_specs() -> tuple[AccessorySpec, ...]:
    """Return the curated set of official built-in Jules accessories."""
    dev_glasses = AccessorySpec(
        id="dev_glasses",
        name="Óculos Dev",
        anchor="eyes",
        offset_x=0,
        offset_y=0,
        scale_with_pet=True,
        builtin=True,
        source_kind="builtin",
        rows=(
            ".KKKKKK..KKKKKK.",
            "KKWCCCKDDKWCCCKK",
            ".KCBBBK..KCBBBK.",
            ".KBBBBK..KBBBBK.",
            ".KKKKKK..KKKKKK.",
        ),
        palette={
            "K": "#0F172A",
            "D": "#1E293B",
            "B": "#0284C7",
            "C": "#38BDF8",
            "W": "#E0F2FE",
        },
        base_width=16,
        base_height=5,
    )

    detective_loupe = AccessorySpec(
        id="detective_loupe",
        name="Lupa de Detetive",
        anchor="full",
        offset_x=0,
        offset_y=-2,
        scale_with_pet=True,
        builtin=True,
        source_kind="builtin",
        rows=(
            "........OOOOOO..........",
            "......OOBBBBBBOO........",
            ".....OBBDDDDDDBBO.......",
            "...OOOBBBBBBBBBBOOO.....",
            "..OSSSSSSSSSSSSSSSO.....",
            "........................",
            "........................",
            ".............GGGG.......",
            "............GLLCCG......",
            "............GLCCCG......",
            "............GCCCCG......",
            ".............GGGG.......",
            "................GHO.....",
            ".................HO.....",
            "..................HO....",
        ),
        palette={
            "O": "#27180E",
            "B": "#92400E",
            "D": "#451A03",
            "S": "#78350F",
            "G": "#F59E0B",
            "C": "#38BDF8AA",
            "L": "#E0F2FECC",
            "H": "#78350F",
        },
        base_width=24,
        base_height=15,
    )

    hard_hat = AccessorySpec(
        id="hard_hat",
        name="Capacete de Obra",
        anchor="head_top",
        offset_x=0,
        offset_y=1,
        scale_with_pet=True,
        builtin=True,
        source_kind="builtin",
        rows=(
            "......OOOOOO......",
            "....OOHHYYYYOO....",
            "..OOHHYYYYBYYYOO..",
            ".OYYYYYYYYBYYYYYO.",
            "OSSSSSSSSSSSSSSSSO",
            ".OOOOOOOOOOOOOOOO.",
        ),
        palette={
            "O": "#422006",
            "Y": "#FACC15",
            "H": "#FEF08A",
            "S": "#EAB308",
            "B": "#FFFBEB",
        },
        base_width=18,
        base_height=6,
    )

    return (dev_glasses, detective_loupe, hard_hat)


def default_custom_accessory_dirs(repo_root: Path | None = None) -> list[Path]:
    """Return platform user accessories directory followed by the repo custom folder."""
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        user_dir = Path(appdata) / "JulesDesktopPet" / "accessories"
    else:
        user_dir = Path.home() / ".config" / "jules-desktop-pet" / "accessories"

    root = repo_root or Path(__file__).resolve().parent.parent
    repo_dir = root / "accessories" / "custom"
    return [user_dir, repo_dir]


def _parse_color(value: object) -> QColor | None:
    """Parse #RGB, #RRGGBB, #RRGGBBAA (CSS RGBA), or named Qt colors safely."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.startswith("#"):
        hex_part = text[1:]
        try:
            if len(hex_part) == 3:
                r = int(hex_part[0] * 2, 16)
                g = int(hex_part[1] * 2, 16)
                b = int(hex_part[2] * 2, 16)
                return QColor(r, g, b)
            if len(hex_part) == 6:
                r = int(hex_part[0:2], 16)
                g = int(hex_part[2:4], 16)
                b = int(hex_part[4:6], 16)
                return QColor(r, g, b)
            if len(hex_part) == 8:
                r = int(hex_part[0:2], 16)
                g = int(hex_part[2:4], 16)
                b = int(hex_part[4:6], 16)
                a = int(hex_part[6:8], 16)
                return QColor(r, g, b, a)
        except ValueError:
            return None
        return None

    color = QColor(text)
    return color if color.isValid() else None


def _normalize_anchor(value: object) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_ANCHORS:
            return normalized
    return "head_top"


def _coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _coerce_bool(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "sim"}:
            return True
        if lowered in {"false", "0", "no", "nao", "não"}:
            return False
    return default


def _normalize_rows_and_palette(
    raw_rows: object,
    raw_palette: object,
) -> tuple[tuple[str, ...], dict[str, str], int, int] | None:
    if not isinstance(raw_rows, list) or not raw_rows:
        return None
    if not isinstance(raw_palette, dict):
        return None

    rows_str: list[str] = []
    for item in raw_rows:
        if not isinstance(item, str):
            return None
        rows_str.append(item.rstrip("\r\n"))

    max_width = max((len(row) for row in rows_str), default=0)
    if max_width <= 0:
        return None

    padded_rows = tuple(row.ljust(max_width, ".") for row in rows_str)

    clean_palette: dict[str, str] = {}
    for key, val in raw_palette.items():
        if isinstance(key, str) and len(key) == 1 and key not in {".", " "}:
            if _parse_color(val) is not None and isinstance(val, str):
                clean_palette[key] = val.strip()

    has_colored_pixel = any(
        ch in clean_palette for row in padded_rows for ch in row
    )
    if not has_colored_pixel:
        return None

    return padded_rows, clean_palette, max_width, len(padded_rows)


def _parse_matrix_txt(stem: str, txt_path: Path) -> AccessorySpec | None:
    try:
        content = txt_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    name = stem.replace("_", " ").title()
    anchor = "head_top"
    offset_x = 0
    offset_y = 0
    scale_with_pet = True
    palette: dict[str, str] = dict(DEFAULT_TXT_PALETTE)
    rows: list[str] = []

    for raw_line in content.splitlines():
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Header key-value before/outside grid
        if not rows and (":" in stripped or "=" in stripped):
            sep = ":" if ":" in stripped else "="
            key_raw, val_raw = stripped.split(sep, 1)
            key = key_raw.strip()
            val = val_raw.strip()
            key_lower = key.lower()

            if key_lower == "name" and val:
                name = val
                continue
            if key_lower == "anchor":
                anchor = _normalize_anchor(val)
                continue
            if key_lower == "offset_x":
                offset_x = _coerce_int(val, 0)
                continue
            if key_lower == "offset_y":
                offset_y = _coerce_int(val, 0)
                continue
            if key_lower == "scale_with_pet":
                scale_with_pet = _coerce_bool(val, True)
                continue
            if key_lower == "palette":
                for pair in val.split(","):
                    if "=" in pair:
                        tok, col = pair.split("=", 1)
                        tok = tok.strip()
                        col = col.strip()
                        if len(tok) == 1 and _parse_color(col) is not None:
                            palette[tok] = col
                continue
            if len(key) == 1 and key not in {".", " "} and _parse_color(val) is not None:
                palette[key] = val
                continue

        rows.append(line)

    normalized = _normalize_rows_and_palette(rows, palette)
    if normalized is None:
        return None

    padded_rows, clean_palette, width, height = normalized
    return AccessorySpec(
        id=stem,
        name=name,
        anchor=anchor,
        offset_x=offset_x,
        offset_y=offset_y,
        scale_with_pet=scale_with_pet,
        builtin=False,
        source_kind="matrix_txt",
        rows=padded_rows,
        palette=clean_palette,
        base_width=width,
        base_height=height,
    )


def resolve_builtin_accessory_id(
    mode: str,
    custom_id: str = "",
    category: str = "",
    swarm_count: int = 0,
) -> str | None:
    """Resolve the active accessory ID from mode, active tool category, and swarm size."""
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode in {"none", "off", ""}:
        return None

    if normalized_mode == "custom":
        cid = (custom_id or "").strip()
        return cid or None

    if normalized_mode == "auto":
        if swarm_count > 0:
            return "hard_hat"
        cat = (category or "").strip().lower()
        if cat in {"edit_write", "terminal"}:
            return "dev_glasses"
        if cat == "read_search":
            return "detective_loupe"
        return None

    return (mode or "").strip() or None


def _compute_base_position(spec: AccessorySpec, width: int, height: int) -> tuple[int, int]:
    """Compute top-left logical pixel coordinates on Jules's 24x22 grid."""
    if spec.anchor == "full" or (width == GRID_WIDTH and height == GRID_HEIGHT):
        return (0, 0)
    if spec.anchor == "eyes":
        return ((GRID_WIDTH - width) // 2, 7 - (height // 2))
    if spec.anchor == "body":
        return ((GRID_WIDTH - width) // 2, 12 - (height // 2))
    return ((GRID_WIDTH - width) // 2, 2 - height)


def _mirror_image_horizontally(img: QImage) -> QImage:
    if hasattr(img, "flipped"):
        return img.flipped(Qt.Orientation.Horizontal)
    return img.mirrored(True, False)


@lru_cache(maxsize=256)
def _render_cached(
    spec_id: str,
    source_kind: str,
    anchor: str,
    offset_x: int,
    offset_y: int,
    scale_with_pet: bool,
    rows: tuple[str, ...],
    palette_items: tuple[tuple[str, str], ...],
    image_path_str: str,
    image_mtime_ns: int,
    scale: int,
    flip_x: bool,
) -> tuple[QPixmap, int, int]:
    del spec_id, source_kind, image_mtime_ns
    pet_scale = max(1, int(scale))
    pixel_scale = pet_scale if scale_with_pet else 1

    if image_path_str:
        img = QImage(image_path_str)
        if img.isNull():
            return (QPixmap(), 0, 0)
        img = img.convertToFormat(QImage.Format.Format_ARGB32)
        if flip_x:
            img = _mirror_image_horizontally(img)
    else:
        if not rows:
            return (QPixmap(), 0, 0)
        width = len(rows[0])
        height = len(rows)
        palette_map = {k: _parse_color(v) for k, v in palette_items}
        img = QImage(width, height, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                color = palette_map.get(ch)
                if color is not None:
                    draw_x = (width - 1 - x) if flip_x else x
                    img.setPixelColor(draw_x, y, color)

    width = img.width()
    height = img.height()
    if width <= 0 or height <= 0:
        return (QPixmap(), 0, 0)

    if pixel_scale != 1:
        img = img.scaled(
            width * pixel_scale,
            height * pixel_scale,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )

    dummy_spec = AccessorySpec(
        id="",
        name="",
        anchor=anchor,
        offset_x=offset_x,
        offset_y=offset_y,
        scale_with_pet=scale_with_pet,
    )
    base_x, base_y = _compute_base_position(dummy_spec, width, height)
    if flip_x:
        mirrored_base_x = GRID_WIDTH - width - base_x
        effective_offset_x = -offset_x
    else:
        mirrored_base_x = base_x
        effective_offset_x = offset_x

    draw_x_offset = (mirrored_base_x + effective_offset_x) * pet_scale
    draw_y_offset = (base_y + offset_y) * pet_scale
    return (QPixmap.fromImage(img), draw_x_offset, draw_y_offset)


def render_accessory_pixmap(
    spec: AccessorySpec,
    scale: int = 4,
    flip_x: bool = False,
) -> tuple[QPixmap, int, int]:
    """Render an accessory spec with crisp nearest-neighbor scaling and offset."""
    image_path_str = ""
    image_mtime_ns = 0
    if spec.image_path is not None:
        image_path_str = str(spec.image_path)
        try:
            image_mtime_ns = spec.image_path.stat().st_mtime_ns
        except OSError:
            return (QPixmap(), 0, 0)

    return _render_cached(
        spec_id=spec.id,
        source_kind=spec.source_kind,
        anchor=spec.anchor,
        offset_x=spec.offset_x,
        offset_y=spec.offset_y,
        scale_with_pet=spec.scale_with_pet,
        rows=spec.rows,
        palette_items=tuple(sorted(spec.palette.items())),
        image_path_str=image_path_str,
        image_mtime_ns=image_mtime_ns,
        scale=scale,
        flip_x=flip_x,
    )


class AccessoriesManager:
    """Registry and modding loader for official and user-supplied Jules accessories."""

    def __init__(
        self,
        custom_dirs: Sequence[Path | str] | None = None,
        *,
        include_builtins: bool = True,
    ) -> None:
        if custom_dirs is None:
            self._custom_dirs: tuple[Path, ...] = tuple(default_custom_accessory_dirs())
        else:
            self._custom_dirs = tuple(Path(p) for p in custom_dirs)
        self._include_builtins = bool(include_builtins)
        self._accessories: dict[str, AccessorySpec] = {}
        self.reload()

    @property
    def custom_dirs(self) -> tuple[Path, ...]:
        """Return the configured custom accessory search directories."""
        return self._custom_dirs

    def reload(self) -> None:
        """Reload built-in and custom accessories from disk."""
        registry: dict[str, AccessorySpec] = {}
        if self._include_builtins:
            for spec in _build_builtin_specs():
                registry[spec.id] = spec

        custom_loaded: dict[str, AccessorySpec] = {}
        for directory in self._custom_dirs:
            for spec in self._scan_directory(directory):
                if spec.id not in custom_loaded:
                    custom_loaded[spec.id] = spec

        registry.update(custom_loaded)
        self._accessories = registry

    def _scan_directory(self, directory: Path) -> Iterable[AccessorySpec]:
        if not directory.is_dir():
            return ()

        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return ()

        specs: list[AccessorySpec] = []
        handled_stems: set[str] = set()
        used_png_paths: set[Path] = set()

        # Pass 1: JSON descriptors (either matrix JSON or PNG sidecar metadata)
        for entry in entries:
            if not entry.is_file() or entry.suffix.lower() != ".json":
                continue
            if entry.name.startswith("."):
                continue

            stem = entry.stem
            handled_stems.add(stem)
            try:
                raw_text = entry.read_text(encoding="utf-8")
                data = json.loads(raw_text)
            except (OSError, UnicodeDecodeError, ValueError, TypeError):
                continue

            if not isinstance(data, dict):
                continue

            name = str(data.get("name") or stem.replace("_", " ").title()).strip() or stem
            anchor = _normalize_anchor(data.get("anchor", "head_top"))
            offset_x = _coerce_int(data.get("offset_x", 0), 0)
            offset_y = _coerce_int(data.get("offset_y", 0), 0)
            scale_with_pet = _coerce_bool(data.get("scale_with_pet", True), True)

            if "rows" in data:
                normalized = _normalize_rows_and_palette(data.get("rows"), data.get("palette"))
                if normalized is None:
                    continue
                padded_rows, clean_palette, width, height = normalized
                specs.append(
                    AccessorySpec(
                        id=stem,
                        name=name,
                        anchor=anchor,
                        offset_x=offset_x,
                        offset_y=offset_y,
                        scale_with_pet=scale_with_pet,
                        builtin=False,
                        source_kind="matrix_json",
                        rows=padded_rows,
                        palette=clean_palette,
                        base_width=width,
                        base_height=height,
                    )
                )
            else:
                image_ref = data.get("image")
                if isinstance(image_ref, str) and image_ref.strip():
                    png_path = directory / image_ref.strip()
                else:
                    png_path = directory / f"{stem}.png"

                if not png_path.is_file():
                    continue
                img = QImage(str(png_path))
                if img.isNull() or img.width() <= 0 or img.height() <= 0:
                    continue
                used_png_paths.add(png_path.resolve())
                specs.append(
                    AccessorySpec(
                        id=stem,
                        name=name,
                        anchor=anchor,
                        offset_x=offset_x,
                        offset_y=offset_y,
                        scale_with_pet=scale_with_pet,
                        builtin=False,
                        source_kind="png",
                        image_path=png_path,
                        base_width=img.width(),
                        base_height=img.height(),
                    )
                )

        # Pass 2: standalone PNGs (without sidecar JSON)
        for entry in entries:
            if not entry.is_file() or entry.suffix.lower() != ".png":
                continue
            if entry.name.startswith("."):
                continue
            stem = entry.stem
            if stem in handled_stems or entry.resolve() in used_png_paths:
                continue
            img = QImage(str(entry))
            if img.isNull() or img.width() <= 0 or img.height() <= 0:
                continue
            handled_stems.add(stem)
            default_anchor = (
                "full"
                if (img.width() == GRID_WIDTH and img.height() == GRID_HEIGHT)
                else "head_top"
            )
            specs.append(
                AccessorySpec(
                    id=stem,
                    name=stem.replace("_", " ").title(),
                    anchor=default_anchor,
                    offset_x=0,
                    offset_y=0,
                    scale_with_pet=True,
                    builtin=False,
                    source_kind="png",
                    image_path=entry,
                    base_width=img.width(),
                    base_height=img.height(),
                )
            )

        # Pass 3: matrix TXT files
        for entry in entries:
            if not entry.is_file() or entry.suffix.lower() != ".txt":
                continue
            if entry.name.startswith("."):
                continue
            stem = entry.stem
            if stem in handled_stems:
                continue
            spec = _parse_matrix_txt(stem, entry)
            if spec is not None:
                handled_stems.add(stem)
                specs.append(spec)

        return specs

    def get(self, accessory_id: str) -> AccessorySpec | None:
        """Return an accessory spec by ID if registered."""
        return self._accessories.get(accessory_id)

    def list_accessories(self) -> list[AccessorySpec]:
        """Return all registered accessories (built-ins + custom)."""
        return list(self._accessories.values())

    def list_builtins(self) -> list[AccessorySpec]:
        """Return only official built-in accessories."""
        return [spec for spec in self._accessories.values() if spec.builtin]

    def list_custom(self) -> list[AccessorySpec]:
        """Return only user-modded custom accessories."""
        return [spec for spec in self._accessories.values() if not spec.builtin]

    def resolve_active_accessory(
        self,
        mode: str,
        custom_id: str = "",
        category: str = "",
        swarm_count: int = 0,
    ) -> AccessorySpec | None:
        """Resolve which AccessorySpec should be drawn for the current state."""
        resolved_id = resolve_builtin_accessory_id(
            mode=mode,
            custom_id=custom_id,
            category=category,
            swarm_count=swarm_count,
        )
        if not resolved_id:
            return None
        return self._accessories.get(resolved_id)
