"""Headless TDD tests for OctoSwarm multi-instance clones, click-through, and manager."""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtNetwork import QTcpSocket
from PySide6.QtWidgets import QApplication

from jules_pet.bubble_widget import BubbleWidget
from jules_pet.buddy import BuddySessionModel
from jules_pet.config import EYE, SPARKLE_CYAN
from jules_pet.ipc_server import JulesIpcServer
from jules_pet.pet_window import JulesPetWindow
from jules_pet.physics import Particle
from jules_pet.subagent_window import JulesSubagentWindow
from jules_pet.swarm_manager import MAX_VISIBLE_CLONES, MascotSquadManager
from jules_pet.transcript_watcher import TranscriptWatcher


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _pump_events_until(predicate, timeout_ms: int = 1500) -> bool:
    if predicate():
        return True
    loop = QEventLoop()
    timed_out = False

    def _on_timeout() -> None:
        nonlocal timed_out
        timed_out = True
        loop.quit()

    timeout_timer = QTimer()
    timeout_timer.setSingleShot(True)
    timeout_timer.timeout.connect(_on_timeout)
    timeout_timer.start(timeout_ms)

    poll_timer = QTimer()
    poll_timer.setInterval(10)

    def _check() -> None:
        if predicate():
            loop.quit()

    poll_timer.timeout.connect(_check)
    poll_timer.start()
    loop.exec()
    poll_timer.stop()
    timeout_timer.stop()
    return not timed_out and predicate()


def _make_manager() -> tuple[MascotSquadManager, JulesPetWindow, BubbleWidget, JulesIpcServer, TranscriptWatcher]:
    pet = JulesPetWindow()
    bubble = BubbleWidget()
    ipc = JulesIpcServer(host="127.0.0.1", port=0, auto_start=False)
    watcher = TranscriptWatcher()
    buddy = BuddySessionModel()
    manager = MascotSquadManager(
        pet_window=pet,
        bubble_widget=bubble,
        ipc_server=ipc,
        transcript_watcher=watcher,
        buddy=buddy,
        auto_start=False,
    )
    return manager, pet, bubble, ipc, watcher


def test_swarm_caps_visible_clones_at_five_and_updates_overflow_badge(qapp: QApplication) -> None:
    assert MAX_VISIBLE_CLONES == 5
    manager, pet, bubble, ipc, watcher = _make_manager()
    try:
        assert manager.MAX_VISIBLE_CLONES == 5
        for i in range(7):
            watcher.subagent_event.emit("spawn", f"sub-{i}", f"Worker {i}", "research")

        assert len(manager.active_clones) == 5
        assert manager.overflow_count == 2
        assert not bubble.overflow_badge.isHidden()
        assert bubble.overflow_badge.text() == "+2"
        assert all(isinstance(clone, JulesSubagentWindow) for clone in manager.active_clones.values())
    finally:
        manager.stop()
        pet.close()


def test_swarm_clone_distinct_non_zero_hue_and_main_annoyed_side_eye(qapp: QApplication) -> None:
    manager, pet, bubble, ipc, watcher = _make_manager()
    try:
        for i in range(5):
            watcher.subagent_event.emit("spawn", f"sub-{i}", f"Role {i}", "self")

        assert pet.controller.current_eye_mode() == "annoyed_side_eye"

        hues = [clone.hue_shift for clone in manager.active_clones.values()]
        assert len(hues) == 5
        assert all(0.0 < (h % 1.0) < 1.0 for h in hues)
        assert len({round(h % 1.0, 3) for h in hues}) == 5
    finally:
        manager.stop()
        pet.close()


def test_subagent_completion_triggers_high_five_and_cleans_up_clone(qapp: QApplication) -> None:
    manager, pet, bubble, ipc, watcher = _make_manager()
    try:
        watcher.subagent_event.emit("spawn", "sub-done-1", "Tester", "research")
        watcher.subagent_event.emit("spawn", "sub-done-2", "Builder", "self")
        assert len(manager.active_clones) == 2

        clone_1 = manager.active_clones["sub-done-1"]
        watcher.subagent_event.emit("done", "sub-done-1", "Tester", "research")

        assert clone_1.phase in ("returning", "high_five")
        assert pet.controller.current_eye_mode() == "high_five"
        assert pet.controller.current_frame_name().startswith("high_five_")
        assert any(p.kind in ("sparkle", "heart") for p in pet.controller.particles)

        # Complete immediately removes clone cleanly
        clone_1.complete_immediately()
        qapp.processEvents()
        assert "sub-done-1" not in manager.active_clones
        assert len(manager.active_clones) == 1

        # Second clone finishes via deterministic simulation ticks (return -> high_five -> fade-out)
        clone_2 = manager.active_clones["sub-done-2"]
        watcher.subagent_event.emit("done", "sub-done-2", "Builder", "self")
        assert clone_2.phase in ("returning", "high_five")

        screen = QRect(0, 0, 1920, 1080)
        anchor = QPointF(pet.controller.sprite_center)
        for _ in range(120):
            if "sub-done-2" not in manager.active_clones:
                break
            clone_2.step(0.05, anchor_center=anchor, screen_rect=screen)
            qapp.processEvents()

        assert "sub-done-2" not in manager.active_clones
        assert len(manager.active_clones) == 0
    finally:
        manager.stop()
        pet.close()


def test_stop_fully_idle_cleans_orphaned_clones_and_resets_overflow(qapp: QApplication) -> None:
    manager, pet, bubble, ipc, watcher = _make_manager()
    try:
        for i in range(7):
            watcher.subagent_event.emit("spawn", f"orphan-{i}", f"Worker {i}", "research")

        assert len(manager.active_clones) == 5
        assert manager.overflow_count == 2
        assert bubble.overflow_badge.text() == "+2"

        ipc.event_received.emit(
            {
                "type": "lifecycle",
                "event": "Stop",
                "fully_idle": True,
                "termination_reason": "NO_TOOL_CALL",
            }
        )
        qapp.processEvents()

        assert len(manager.active_clones) == 0
        assert manager.overflow_count == 0
        assert bubble.overflow_badge.isHidden()
    finally:
        manager.stop()
        pet.close()


def test_click_through_toggles_transparent_for_input_on_all_windows(qapp: QApplication) -> None:
    manager, pet, bubble, ipc, watcher = _make_manager()
    try:
        pet.show()
        bubble.show()
        watcher.subagent_event.emit("spawn", "ct-sub-1", "Scout", "research")
        clone = manager.active_clones["ct-sub-1"]

        def _is_click_through(widget) -> bool:
            return bool(widget.windowFlags() & Qt.WindowType.WindowTransparentForInput) and widget.testAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )

        assert not _is_click_through(pet)
        assert not _is_click_through(bubble)
        assert not _is_click_through(clone)

        manager.set_click_through(True)
        assert manager.click_through is True
        assert _is_click_through(pet)
        assert _is_click_through(bubble)
        assert _is_click_through(clone)
        assert pet.isVisible()
        assert bubble.isVisible()

        # Newly spawned clones while click-through is active must inherit the attribute
        watcher.subagent_event.emit("spawn", "ct-sub-2", "Scout 2", "research")
        clone_2 = manager.active_clones["ct-sub-2"]
        assert _is_click_through(clone_2)

        manager.set_click_through(False)
        assert manager.click_through is False
        assert not _is_click_through(pet)
        assert not _is_click_through(bubble)
        assert not _is_click_through(clone)
        assert not _is_click_through(clone_2)

        # Shortcut exists and toggles via Ctrl+Shift+J
        assert manager.shortcut_click_through.key().toString() == "Ctrl+Shift+J"
    finally:
        manager.stop()
        pet.close()


def test_pet_window_menu_actions_and_sweat_ink_paint_event(qapp: QApplication) -> None:
    pet = JulesPetWindow()
    try:
        action_texts = [act.text() for act in pet._menu.actions() if not act.isSeparator()]

        approval_actions = [act for act in pet._menu.actions() if "Aprovação pelo Pet" in act.text()]
        click_actions = [act for act in pet._menu.actions() if "Modo Click-Through" in act.text()]

        assert len(approval_actions) == 1, f"Missing approval action in {action_texts}"
        assert approval_actions[0].isCheckable()
        assert approval_actions[0].isChecked() is False

        assert len(click_actions) == 1, f"Missing click-through action in {action_texts}"
        assert click_actions[0].isCheckable()
        assert click_actions[0].isChecked() is False

        # Verify signals fire on toggle
        approval_toggles: list[bool] = []
        click_toggles: list[bool] = []
        pet.approval_bridge_toggled.connect(approval_toggles.append)
        pet.click_through_toggled.connect(click_toggles.append)

        approval_actions[0].trigger()
        click_actions[0].trigger()
        assert approval_toggles == [True]
        assert click_toggles == [True]

        # Verify paintEvent renders sweat & ink particles cleanly onto an image
        pet.controller.particles = [
            Particle(x=40.0, y=30.0, vx=0.0, vy=0.0, kind="sweat", color=SPARKLE_CYAN, life=0.7, max_life=0.8, size=4),
            Particle(x=60.0, y=50.0, vx=0.0, vy=0.0, kind="ink", color=EYE, life=0.7, max_life=0.8, size=4),
        ]
        canvas = QImage(pet.width(), pet.height(), QImage.Format.Format_ARGB32)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        for particle in pet.controller.particles:
            pet._draw_particle(painter, particle)
        painter.end()

        # Sweat particle should have painted cyan pixels near (40, 30)
        sweat_hits = sum(
            1
            for dx in range(-4, 6)
            for dy in range(-4, 6)
            if canvas.pixelColor(40 + dx, 30 + dy).alpha() > 0
        )
        # Ink particle should have painted dark indigo pixels near (60, 50)
        ink_hits = sum(
            1
            for dx in range(-6, 7)
            for dy in range(-6, 7)
            if canvas.pixelColor(60 + dx, 50 + dy).alpha() > 0
        )
        assert sweat_hits > 0
        assert ink_hits > 0

        # Also exercise full paintEvent via grab()
        pixmap = pet.grab()
        assert not pixmap.isNull()
    finally:
        pet.close()


def test_approval_bridge_default_asks_and_enabled_forwards_bubble_decision(qapp: QApplication) -> None:
    manager, pet, bubble, ipc, watcher = _make_manager()
    manager.start()
    try:
        assert manager.approval_bridge_enabled is False

        client = QTcpSocket()
        client.connectToHost("127.0.0.1", ipc.port)
        assert client.waitForConnected(1000)

        # Disabled -> auto-resolves "ask" without showing approval bar
        req_1 = {
            "type": "approval_request",
            "request_id": "req-disabled-1",
            "tool": "run_command",
            "command": "echo hi",
            "timeout_ms": 2000,
        }
        client.write((json.dumps(req_1) + "\n").encode("utf-8"))
        client.flush()

        assert _pump_events_until(lambda: client.bytesAvailable() > 0)
        reply_1 = json.loads(bytes(client.readAll()).decode("utf-8").strip())
        assert reply_1["request_id"] == "req-disabled-1"
        assert reply_1["decision"] == "ask"
        assert bubble.approval_bar.isHidden()

        # Enabled -> shows approval bar and resolves via user click
        pet._act_approval_bridge.setChecked(True)
        assert manager.approval_bridge_enabled is True

        req_2 = {
            "type": "approval_request",
            "request_id": "req-enabled-2",
            "tool": "run_command",
            "command": "uv run pytest",
            "timeout_ms": 2000,
        }
        client.write((json.dumps(req_2) + "\n").encode("utf-8"))
        client.flush()

        assert _pump_events_until(lambda: not bubble.approval_bar.isHidden())
        assert bubble.pending_request_id == "req-enabled-2"

        bubble.allow_button.click()
        assert _pump_events_until(lambda: client.bytesAvailable() > 0)
        reply_2 = json.loads(bytes(client.readAll()).decode("utf-8").strip())
        assert reply_2["request_id"] == "req-enabled-2"
        assert reply_2["decision"] == "allow"
        assert bubble.approval_bar.isHidden()

        client.disconnectFromHost()
    finally:
        manager.stop()
        pet.close()
