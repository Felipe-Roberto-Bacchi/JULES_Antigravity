"""Tests for default size 'Pequeno' and persistent settings across sessions."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

from jules_pet.config import DEFAULT_SCALE_NAME, PIXEL_SCALES
from jules_pet.ipc_server import JulesIpcServer
from jules_pet.pet_window import JulesPetWindow
from jules_pet.settings import PetSettings, load_settings, save_settings
from jules_pet.swarm_manager import MascotSquadManager


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_default_size_is_pequeno(qapp: QApplication) -> None:
    assert DEFAULT_SCALE_NAME == "Pequeno"
    pet = JulesPetWindow(persist_settings=False)
    try:
        assert pet.controller.scale == PIXEL_SCALES["Pequeno"]
        assert pet._scale_actions["Pequeno"].isChecked() is True
    finally:
        pet.close()


def test_settings_round_trip_and_corrupt_fallback(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "settings.json"
    assert load_settings(path) == PetSettings()

    custom = PetSettings(
        scale_name="Grande",
        floor_mode=True,
        follow_mouse=True,
        always_on_top=False,
        auto_hide_bubble=False,
        approval_bridge_enabled=True,
        click_through=True,
    )
    save_settings(custom, path)
    assert load_settings(path) == custom

    # Malformed JSON and invalid scale_name fall back cleanly
    path.write_text("{broken json", encoding="utf-8")
    assert load_settings(path) == PetSettings()

    path.write_text('{"scale_name": "Gigante", "floor_mode": true}', encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.scale_name == "Pequeno"
    assert loaded.floor_mode is True


def test_preferences_persist_across_sessions(qapp: QApplication, tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"

    # Session 1: user changes size to Grande, enables taskbar floor walk, follow mouse,
    # approval bridge, and disables auto-hide bubble.
    pet1 = JulesPetWindow(settings_path=settings_file, persist_settings=True)
    mgr1 = MascotSquadManager(
        pet_window=pet1,
        ipc_server=JulesIpcServer(port=0, auto_start=False),
    )
    mgr1.start()
    try:
        pet1._scale_actions["Grande"].trigger()
        pet1._act_floor.trigger()
        pet1._act_follow.setChecked(True)
        pet1._act_top.setChecked(False)
        pet1._act_auto_hide_bubble.setChecked(False)
        pet1._act_approval_bridge.setChecked(True)
    finally:
        mgr1.stop()
        pet1.close()

    assert settings_file.is_file()

    # Session 2: fresh instances load all saved preferences automatically
    pet2 = JulesPetWindow(settings_path=settings_file, persist_settings=True)
    mgr2 = MascotSquadManager(
        pet_window=pet2,
        ipc_server=JulesIpcServer(port=0, auto_start=False),
    )
    mgr2.start()
    try:
        assert pet2.controller.scale == PIXEL_SCALES["Grande"]
        assert pet2._scale_actions["Grande"].isChecked() is True
        assert pet2.controller.floor_mode is True
        assert pet2._act_floor.isChecked() is True
        assert pet2.controller.follow_mouse is True
        assert pet2._act_follow.isChecked() is True
        assert pet2._always_on_top is False
        assert pet2._act_top.isChecked() is False
        assert mgr2.bubble_widget.auto_hide_enabled is False
        assert pet2._act_auto_hide_bubble.isChecked() is False
        assert mgr2.approval_bridge_enabled is True
        assert pet2._act_approval_bridge.isChecked() is True
    finally:
        mgr2.stop()
        pet2.close()
