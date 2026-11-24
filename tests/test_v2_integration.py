"""End-to-end integration tests for V2 (accessories, perch, 8-bit sounds, Tamagotchi)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import pytest
from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication, QMenu

from jules_pet.accessories_manager import AccessoriesManager, render_accessory_pixmap
from jules_pet.bubble_widget import BubbleWidget
from jules_pet.buddy import BuddySessionModel
from jules_pet.coffee_window import CoffeeCupWindow
from jules_pet.config import OUTLINE
from jules_pet.ipc_server import JulesIpcServer
from jules_pet.perch_controller import PerchController, WindowInfo
from jules_pet.pet_window import JulesPetWindow
from jules_pet.physics import Particle, PetState
from jules_pet.settings import PetSettings, load_settings, save_settings
from jules_pet.sound_effects import RetroSoundEngine, SoundEffect
from jules_pet.stats_window import StatsCardWindow
from jules_pet.swarm_manager import MascotSquadManager
from jules_pet.transcript_watcher import TranscriptWatcher


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _find_submenu(menu: QMenu, title: str) -> QMenu | None:
    for act in menu.actions():
        sub = act.menu()
        if sub is not None and act.text() == title:
            return sub
    return None


def _make_custom_accessory_dir(tmp_path: Path) -> Path:
    custom_dir = tmp_path / "custom_acc"
    custom_dir.mkdir(parents=True, exist_ok=True)
    (custom_dir / "party_crown.txt").write_text(
        "\n".join(
            [
                "name: Coroa VIP",
                "anchor: head_top",
                "Y.Y.Y",
                "YYYYY",
                "YYYYY",
            ]
        ),
        encoding="utf-8",
    )
    return custom_dir


def test_v2_settings_round_trip_and_persistence_across_sessions(
    qapp: QApplication, tmp_path: Path
) -> None:
    defaults = PetSettings()
    assert defaults.accessory_mode == "auto"
    assert defaults.custom_accessory_id == ""
    assert defaults.perch_enabled is False
    assert defaults.sounds_enabled is False

    settings_file = tmp_path / "v2_settings.json"
    assert load_settings(settings_file) == defaults

    custom = PetSettings(
        accessory_mode="custom",
        custom_accessory_id="party_crown",
        perch_enabled=True,
        sounds_enabled=True,
    )
    save_settings(custom, settings_file)
    assert load_settings(settings_file) == custom

    # Session 1 -> user toggles V2 options via MascotSquadManager / JulesPetWindow
    custom_dir = _make_custom_accessory_dir(tmp_path)
    acc_mgr_1 = AccessoriesManager(custom_dirs=[custom_dir])
    session_file = tmp_path / "session_v2.json"

    pet1 = JulesPetWindow(
        settings_path=session_file,
        persist_settings=True,
        accessories_manager=acc_mgr_1,
    )
    mgr1 = MascotSquadManager(
        pet_window=pet1,
        ipc_server=JulesIpcServer(port=0, auto_start=False),
        accessories_manager=acc_mgr_1,
        perch_controller=PerchController(window_provider=lambda: None),
        sound_engine=RetroSoundEngine(enabled=False, player=lambda _b: None),
    )
    try:
        pet1.accessory_selected.emit("custom", "party_crown")
        pet1._act_perch.setChecked(True)
        pet1._act_sounds.setChecked(True)
    finally:
        mgr1.stop()
        pet1.close()

    assert session_file.is_file()

    # Session 2 -> fresh instances restore V2 preferences automatically
    acc_mgr_2 = AccessoriesManager(custom_dirs=[custom_dir])
    pet2 = JulesPetWindow(
        settings_path=session_file,
        persist_settings=True,
        accessories_manager=acc_mgr_2,
    )
    mgr2 = MascotSquadManager(
        pet_window=pet2,
        ipc_server=JulesIpcServer(port=0, auto_start=False),
        accessories_manager=acc_mgr_2,
        perch_controller=PerchController(window_provider=lambda: None),
        sound_engine=RetroSoundEngine(enabled=False, player=lambda _b: None),
    )
    try:
        assert pet2.settings.accessory_mode == "custom"
        assert pet2.settings.custom_accessory_id == "party_crown"
        assert pet2.settings.perch_enabled is True
        assert pet2.settings.sounds_enabled is True

        assert mgr2.accessory_mode == "custom"
        assert mgr2.custom_accessory_id == "party_crown"
        assert mgr2.active_accessory_id == "party_crown"
        assert mgr2.perch_enabled is True
        assert mgr2.perch_controller.enabled is True
        assert pet2._act_perch.isChecked() is True
        assert mgr2.sounds_enabled is True
        assert mgr2.sound_engine.enabled is True
        assert pet2._act_sounds.isChecked() is True

        acc_menu = _find_submenu(pet2._menu, "Acessórios")
        assert acc_menu is not None
        crown_actions = [a for a in acc_menu.actions() if a.text() == "Coroa VIP"]
        assert len(crown_actions) == 1
        assert crown_actions[0].isChecked() is True
    finally:
        mgr2.stop()
        pet2.close()


def test_pet_window_v2_menu_mouse_shortcuts_and_overlays(
    qapp: QApplication, tmp_path: Path
) -> None:
    custom_dir = _make_custom_accessory_dir(tmp_path)
    acc_mgr = AccessoriesManager(custom_dirs=[custom_dir])
    pet = JulesPetWindow(persist_settings=False, accessories_manager=acc_mgr)
    try:
        acc_menu = _find_submenu(pet._menu, "Acessórios")
        assert acc_menu is not None, "Submenu 'Acessórios' missing"

        acc_actions = {a.text(): a for a in acc_menu.actions() if not a.isSeparator()}
        assert "Automático por Ferramenta" in acc_actions
        assert acc_actions["Automático por Ferramenta"].isCheckable()
        assert acc_actions["Automático por Ferramenta"].isChecked() is True
        assert "Nenhum" in acc_actions
        assert acc_actions["Nenhum"].isCheckable()
        assert acc_actions["Nenhum"].isChecked() is False
        assert "Coroa VIP" in acc_actions
        assert acc_actions["Coroa VIP"].isCheckable()

        top_actions = {a.text(): a for a in pet._menu.actions() if not a.isSeparator()}
        assert "Empoleirar na janela de código" in top_actions
        assert top_actions["Empoleirar na janela de código"].isCheckable()
        assert top_actions["Empoleirar na janela de código"].isChecked() is False

        assert "Sons 8-bit" in top_actions
        assert top_actions["Sons 8-bit"].isCheckable()
        assert top_actions["Sons 8-bit"].isChecked() is False

        assert "Oferecer Café" in top_actions
        assert "Estatísticas da Sessão" in top_actions

        # Verify menu signals
        acc_events: list[tuple[str, str]] = []
        perch_events: list[bool] = []
        sound_events: list[bool] = []
        coffee_events: list[bool] = []
        stats_events: list[bool] = []

        pet.accessory_selected.connect(lambda m, cid: acc_events.append((m, cid)))
        pet.perch_toggled.connect(perch_events.append)
        pet.sounds_toggled.connect(sound_events.append)
        pet.coffee_requested.connect(lambda: coffee_events.append(True))
        pet.stats_requested.connect(lambda: stats_events.append(True))

        acc_actions["Nenhum"].trigger()
        acc_actions["Coroa VIP"].trigger()
        acc_actions["Automático por Ferramenta"].trigger()
        assert acc_events == [("none", ""), ("custom", "party_crown"), ("auto", "")]

        top_actions["Empoleirar na janela de código"].trigger()
        top_actions["Sons 8-bit"].trigger()
        top_actions["Oferecer Café"].trigger()
        top_actions["Estatísticas da Sessão"].trigger()

        assert perch_events == [True]
        assert sound_events == [True]
        assert len(coffee_events) == 1
        assert len(stats_events) == 1

        # Middle-click -> coffee_requested; Right double-click -> stats_requested
        mid_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(20.0, 20.0),
            QPointF(20.0, 20.0),
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.MiddleButton,
            Qt.KeyboardModifier.NoModifier,
        )
        pet.mousePressEvent(mid_event)
        assert len(coffee_events) == 2

        rdbl_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonDblClick,
            QPointF(20.0, 20.0),
            QPointF(20.0, 20.0),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        pet.mouseDoubleClickEvent(rdbl_event)
        assert len(stats_events) == 2

        # Draw steam particle cleanly
        steam = Particle(
            x=45.0,
            y=35.0,
            vx=0.0,
            vy=0.0,
            kind="steam",
            color=OUTLINE,
            life=0.8,
            max_life=1.0,
            size=4,
        )
        canvas = QImage(pet.width(), pet.height(), QImage.Format.Format_ARGB32)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        pet._draw_particle(painter, steam)
        painter.end()
        steam_hits = sum(
            1
            for dx in range(-6, 7)
            for dy in range(-6, 7)
            if canvas.pixelColor(45 + dx, 35 + dy).alpha() > 0
        )
        assert steam_hits > 0

        # Active accessory overlay + EXHAUSTED micro-laptop render cleanly
        base_img = pet.grab().toImage()

        spec = acc_mgr.get("dev_glasses")
        assert spec is not None
        pix, ox, oy = render_accessory_pixmap(spec, scale=pet.controller.scale, flip_x=False)
        pet.set_active_accessory(pix, ox, oy)
        with_acc_img = pet.grab().toImage()
        assert with_acc_img != base_img

        pet.set_active_accessory(None, 0, 0)
        pet.controller.set_exhausted(True)
        assert pet.controller.state == PetState.EXHAUSTED
        exhausted_img = pet.grab().toImage()
        assert exhausted_img != base_img
    finally:
        pet.close()


def test_swarm_manager_accessories_sounds_and_ink_splats(qapp: QApplication) -> None:
    played: list[SoundEffect] = []

    class RecordingSoundEngine(RetroSoundEngine):
        def play(self, effect: SoundEffect) -> None:
            if self.enabled:
                played.append(effect)
            super().play(effect)

    pet = JulesPetWindow(persist_settings=False)
    bubble = BubbleWidget()
    ipc = JulesIpcServer(host="127.0.0.1", port=0, auto_start=False)
    watcher = TranscriptWatcher()
    buddy = BuddySessionModel()
    sound_engine = RecordingSoundEngine(enabled=False, player=lambda _b: None)

    manager = MascotSquadManager(
        pet_window=pet,
        bubble_widget=bubble,
        ipc_server=ipc,
        transcript_watcher=watcher,
        buddy=buddy,
        sound_engine=sound_engine,
        auto_start=False,
    )
    try:
        manager.set_sounds_enabled(True)
        assert manager.sounds_enabled is True
        assert sound_engine.enabled is True

        # Tool categories equip corresponding accessories in auto mode
        manager.on_ipc_event({"type": "tool_start", "tool": "edit_file", "category": "edit_write"})
        assert manager.active_accessory_id == "dev_glasses"

        manager.on_ipc_event({"type": "tool_start", "tool": "read_file", "category": "read_search"})
        assert manager.active_accessory_id == "detective_loupe"

        # Active swarm overrides to hard_hat
        watcher.subagent_event.emit("spawn", "sub-acc-1", "Builder", "self")
        assert manager.active_accessory_id == "hard_hat"

        # Subagent completion plays POWER_UP
        watcher.subagent_event.emit("done", "sub-acc-1", "Builder", "self")
        assert SoundEffect.POWER_UP in played

        # Clean up clones
        manager.cleanup_all_clones()

        # tool_end ok=False triggers InkSplatManager.spawn_splats + SoundEffect.SQUIRT
        manager.on_ipc_event(
            {"type": "tool_end", "tool": "run_command", "ok": False, "error": "boom"}
        )
        assert len(manager.ink_splat_manager.active_splats) >= 2
        assert SoundEffect.SQUIRT in played

        # user_interacted plays BLIP
        pet.user_interacted.emit("click")
        assert SoundEffect.BLIP in played

        # Stop fully_idle=True plays LEVEL_UP
        manager.on_ipc_event(
            {"type": "lifecycle", "event": "Stop", "fully_idle": True}
        )
        assert SoundEffect.LEVEL_UP in played
    finally:
        manager.stop()
        pet.close()


def test_swarm_manager_coffee_break_stats_and_perch(qapp: QApplication) -> None:
    target_rect = QRect(200, 180, 900, 620)
    fake_window = WindowInfo(
        hwnd=42,
        title="projeto JULE - Visual Studio Code",
        rect=target_rect,
        pid=os.getpid() + 999,
        visible=True,
        minimized=False,
    )
    perch = PerchController(window_provider=lambda: fake_window, enabled=False)

    pet = JulesPetWindow(persist_settings=False)
    buddy = BuddySessionModel()
    buddy.energy = 30.0
    buddy.mood_score = 50.0
    buddy.update_context(12_000, 3_000, 0.4)
    buddy.handle_event({"type": "tool_start", "tool": "bash", "category": "terminal"})
    buddy.handle_event({"type": "tool_end", "tool": "bash", "ok": True})
    buddy.on_pet()

    manager = MascotSquadManager(
        pet_window=pet,
        ipc_server=JulesIpcServer(port=0, auto_start=False),
        buddy=buddy,
        perch_controller=perch,
        sound_engine=RetroSoundEngine(enabled=False, player=lambda _b: None),
        auto_start=False,
    )
    try:
        # Perch routing
        manager.set_perch_enabled(True)
        assert perch.enabled is True
        perch.poll()
        assert pet.controller.state == PetState.PERCHED
        assert pet.controller._perch_rect == target_rect

        manager.set_perch_enabled(False)
        assert pet.controller.state == PetState.IDLE

        # Offer coffee -> spawns CoffeeCupWindow, steers Jules, calls take_coffee_break on arrival
        coffee = manager.offer_coffee()
        assert isinstance(coffee, CoffeeCupWindow)
        assert manager.coffee_window is coffee
        assert coffee.isVisible()
        assert pet.controller.state == PetState.COFFEE_BREAK

        screen = pet.screen_rect()
        cursor = QPointF(0.0, 0.0)
        energy_before = buddy.energy
        for _ in range(300):
            pet.controller.update(0.05, screen, cursor)
            if buddy.energy > energy_before:
                break

        assert buddy.energy == pytest.approx(min(100.0, energy_before + 30.0))
        assert "Cafezinho" in buddy.status_verb

        # Show stats -> opens & updates StatsCardWindow with current SessionStats
        stats_win = manager.show_stats()
        assert isinstance(stats_win, StatsCardWindow)
        assert manager.stats_window is stats_win
        assert stats_win.isVisible()
        assert stats_win.tokens_value_label.text() == "15K"
        assert stats_win.commands_value_label.text() == "1/1 concluídos"
        assert stats_win.pets_value_label.text() == "1"
    finally:
        manager.stop()
        pet.close()
