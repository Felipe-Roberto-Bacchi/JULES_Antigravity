"""Persistent JSON user preferences for Jules Desktop Pet."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from jules_pet.config import DEFAULT_SCALE_NAME, PIXEL_SCALES


@dataclass
class PetSettings:
    """User preferences persisted across sessions."""

    scale_name: str = DEFAULT_SCALE_NAME
    floor_mode: bool = False
    follow_mouse: bool = False
    always_on_top: bool = True
    auto_hide_bubble: bool = True
    approval_bridge_enabled: bool = False
    click_through: bool = False
    accessory_mode: str = "auto"
    custom_accessory_id: str = ""
    perch_enabled: bool = False
    sounds_enabled: bool = False


def default_settings_path() -> Path:
    """Return the platform settings file path (overridable via JULES_PET_SETTINGS_PATH)."""
    override = os.environ.get("JULES_PET_SETTINGS_PATH", "").strip()
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        return Path(appdata) / "JulesDesktopPet" / "settings.json"
    return Path.home() / ".config" / "jules-desktop-pet" / "settings.json"


def load_settings(path: Path | None = None) -> PetSettings:
    """Load preferences from JSON, falling back cleanly to defaults on any error."""
    target = path or default_settings_path()
    if not target.is_file():
        return PetSettings()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return PetSettings()
    if not isinstance(raw, dict):
        return PetSettings()

    scale_name = raw.get("scale_name", DEFAULT_SCALE_NAME)
    if scale_name not in PIXEL_SCALES:
        scale_name = DEFAULT_SCALE_NAME

    raw_mode = raw.get("accessory_mode", "auto")
    accessory_mode = raw_mode.strip() if isinstance(raw_mode, str) and raw_mode.strip() else "auto"

    raw_custom_id = raw.get("custom_accessory_id", "")
    custom_accessory_id = raw_custom_id.strip() if isinstance(raw_custom_id, str) else ""

    return PetSettings(
        scale_name=scale_name,
        floor_mode=bool(raw.get("floor_mode", False)),
        follow_mouse=bool(raw.get("follow_mouse", False)),
        always_on_top=bool(raw.get("always_on_top", True)),
        auto_hide_bubble=bool(raw.get("auto_hide_bubble", True)),
        approval_bridge_enabled=bool(raw.get("approval_bridge_enabled", False)),
        click_through=bool(raw.get("click_through", False)),
        accessory_mode=accessory_mode,
        custom_accessory_id=custom_accessory_id,
        perch_enabled=bool(raw.get("perch_enabled", False)),
        sounds_enabled=bool(raw.get("sounds_enabled", False)),
    )


def save_settings(settings: PetSettings, path: Path | None = None) -> None:
    """Persist preferences to JSON, creating parent directories if needed."""
    target = path or default_settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(asdict(settings), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
