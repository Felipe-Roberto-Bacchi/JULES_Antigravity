"""Headless TDD tests for BuddySessionModel, BubbleWidget, and AI physics reactions."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtWidgets import QApplication

from jules_pet.bubble_widget import BubbleWidget
from jules_pet.buddy import BuddySessionModel
from jules_pet.physics import PetController, PetState


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_buddy_tool_start_categories_map_to_portuguese_verbs_and_eyes(qapp: QApplication) -> None:
    buddy = BuddySessionModel()

    cases = [
        ("read_file", "read_search", "scanning", None),
        ("edit_file", "edit_write", "coding", "coding"),
        ("run_command", "terminal", "coding", "coding"),
        ("browser_navigate", "browser", "scanning", None),
        ("invoke_subagent", "subagent", "thinking", None),
    ]

    seen_verbs: set[str] = set()
    for tool_name, category, expected_eye, expected_frame in cases:
        buddy.handle_event(
            {
                "type": "tool_start",
                "call_id": f"call-{tool_name}",
                "tool": tool_name,
                "category": category,
                "summary": tool_name,
            }
        )
        assert buddy.active_category == category
        assert buddy.eye_mode == expected_eye
        assert buddy.frame_prefix == expected_frame
        assert isinstance(buddy.status_verb, str) and len(buddy.status_verb.strip()) > 3
        seen_verbs.add(buddy.status_verb)

    # Different categories should produce distinct expressive Portuguese verbs
    assert len(seen_verbs) >= 4


def test_buddy_tool_end_error_and_stop_lifecycle(qapp: QApplication) -> None:
    buddy = BuddySessionModel()
    initial_energy = buddy.energy
    initial_mood = buddy.mood_score

    buddy.handle_event(
        {
            "type": "tool_start",
            "call_id": "c-1",
            "tool": "run_command",
            "category": "terminal",
        }
    )
    buddy.handle_event(
        {
            "type": "tool_end",
            "call_id": "c-1",
            "tool": "run_command",
            "ok": False,
            "error": "exit code 1",
        }
    )

    assert buddy.eye_mode == "shocked_ink"
    assert buddy.mood == "shocked"
    assert buddy.mood_score < initial_mood
    assert buddy.energy < initial_energy
    assert buddy.phase == "error"

    buddy.handle_event(
        {
            "type": "lifecycle",
            "event": "Stop",
            "fully_idle": True,
            "termination_reason": "completed",
        }
    )
    assert buddy.phase == "done"
    assert buddy.eye_mode == "normal"
    assert buddy.frame_prefix is None


def test_buddy_energy_mood_petting_and_context_pressure(qapp: QApplication) -> None:
    buddy = BuddySessionModel()

    # Drop mood & energy first via repeated errors so petting boost is observable
    for i in range(2):
        buddy.handle_event(
            {"type": "tool_end", "call_id": f"err-{i}", "tool": "run_command", "ok": False}
        )
    low_energy = buddy.energy
    low_mood = buddy.mood_score
    assert 0.0 <= low_energy <= 100.0

    buddy.on_pet()
    assert buddy.energy > low_energy
    assert buddy.mood_score > low_mood
    assert buddy.mood == "happy"

    # Clamp upper bounds at 100
    for _ in range(20):
        buddy.on_pet()
    assert buddy.energy <= 100.0
    assert buddy.mood_score <= 100.0

    # Context pressure threshold at 0.75
    buddy.update_context(100_000, 100_000, 0.50)
    assert buddy.context_pressure == pytest.approx(0.50)
    assert buddy.is_sweating is False

    buddy.update_context(500_000, 250_000, 0.75)
    assert buddy.context_pressure == pytest.approx(0.75)
    assert buddy.is_sweating is True

    buddy.update_context(900_000, 300_000, 1.4)
    assert buddy.context_pressure == pytest.approx(1.0)
    assert buddy.is_sweating is True


def test_bubble_widget_styling_status_overflow_and_approval_signals(qapp: QApplication) -> None:
    bubble = BubbleWidget()
    bubble.show()

    # Frameless, translucent, dark-indigo flat QSS (no generic gradients)
    assert bool(bubble.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert bubble.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    qss = bubble.styleSheet()
    assert "#1A1033" in qss
    assert "#705BD6" in qss
    assert "Segoe UI" in qss
    assert "gradient" not in qss.lower()

    # Status text & swarm +N badge
    bubble.set_status("Codando com 8 tentáculos...")
    assert bubble.status_text == "Codando com 8 tentáculos..."
    assert bubble.overflow_badge.isHidden()

    bubble.set_swarm_overflow(3)
    assert not bubble.overflow_badge.isHidden()
    assert bubble.overflow_badge.text() == "+3"

    bubble.set_swarm_overflow(0)
    assert bubble.overflow_badge.isHidden()

    # Approval bar & decision signals
    assert bubble.approval_bar.isHidden()
    decisions: list[tuple[str, str]] = []
    bubble.approval_decided.connect(lambda rid, dec: decisions.append((rid, dec)))

    bubble.show_approval("req-allow-1", "run_command", "uv run pytest -v")
    assert not bubble.approval_bar.isHidden()
    assert bubble.allow_button.text() == "Permitir"
    assert bubble.deny_button.text() == "Bloquear"

    bubble.allow_button.click()
    assert decisions == [("req-allow-1", "allow")]
    assert bubble.approval_bar.isHidden()

    bubble.show_approval("req-deny-2", "run_command", "rm -rf /tmp/x")
    assert not bubble.approval_bar.isHidden()
    bubble.deny_button.click()
    assert decisions == [("req-allow-1", "allow"), ("req-deny-2", "deny")]
    assert bubble.approval_bar.isHidden()

    bubble.close()


def test_physics_controller_ai_expressions_and_sweat_ink_particles(qapp: QApplication) -> None:
    screen = QRect(0, 0, 1920, 1080)
    ctrl = PetController(scale=4)

    # Persistent AI activity
    ctrl.set_ai_activity("coding", "coding")
    assert ctrl.current_eye_mode() == "coding"
    assert ctrl.current_frame_name().startswith("coding_")

    # Clearing AI activity restores normal idle
    ctrl.set_ai_activity(None)
    assert ctrl.current_eye_mode() in ("normal", "blink")
    assert ctrl.current_frame_name().startswith("idle_")

    # Timed high_five
    ctrl.trigger_high_five(duration=0.4)
    assert ctrl.current_eye_mode() == "high_five"
    assert ctrl.current_frame_name().startswith("high_five_")
    for _ in range(12):
        ctrl.update(0.05, screen, QPointF(0, 0))
    assert ctrl.current_eye_mode() in ("normal", "blink")

    # Timed annoyed_side_eye
    ctrl.set_annoyed(duration=0.3)
    assert ctrl.current_eye_mode() == "annoyed_side_eye"
    for _ in range(10):
        ctrl.update(0.05, screen, QPointF(0, 0))
    assert ctrl.current_eye_mode() in ("normal", "blink")

    # Ink shock emits "ink" particles and shows shocked_ink
    ctrl.particles.clear()
    ctrl.trigger_ink_shock(duration=0.35)
    assert ctrl.current_eye_mode() == "shocked_ink"
    assert any(p.kind == "ink" for p in ctrl.particles)
    for _ in range(10):
        ctrl.update(0.05, screen, QPointF(0, 0))
    assert ctrl.current_eye_mode() in ("normal", "blink")

    # Context pressure >= 0.75 emits "sweat" particles (and does not emit when < 0.75)
    ctrl.particles.clear()
    ctrl.set_context_pressure(0.4)
    for _ in range(15):
        ctrl.update(0.05, screen, QPointF(0, 0))
    assert not any(p.kind == "sweat" for p in ctrl.particles)

    ctrl.particles.clear()
    ctrl.set_context_pressure(0.85)
    for _ in range(15):
        ctrl.update(0.05, screen, QPointF(0, 0))
    assert any(p.kind == "sweat" for p in ctrl.particles)

    # Sleep still overrides AI eye mode safely
    ctrl.set_ai_activity("scanning")
    ctrl.toggle_sleep()
    assert ctrl.state == PetState.SLEEP
    assert ctrl.current_eye_mode() == "sleep"


def test_buddy_apply_to_controller_and_bubble_anchor_near(qapp: QApplication) -> None:
    screen = QRect(0, 0, 1920, 1080)
    ctrl = PetController(scale=4)
    buddy = BuddySessionModel()

    buddy.handle_event({"type": "tool_start", "tool": "edit_file", "category": "edit_write"})
    buddy.update_context(700_000, 100_000, 0.8)
    buddy.apply_to_controller(ctrl)

    assert ctrl.current_eye_mode() == "coding"
    assert ctrl.current_frame_name().startswith("coding_")
    assert ctrl.context_pressure == pytest.approx(0.8)

    ctrl.update(0.05, screen, QPointF(0, 0))
    assert any(p.kind == "sweat" for p in ctrl.particles)

    buddy.handle_event({"type": "tool_end", "tool": "edit_file", "ok": False, "error": "boom"})
    buddy.apply_to_controller(ctrl)
    assert ctrl.current_eye_mode() == "shocked_ink"
    assert any(p.kind == "ink" for p in ctrl.particles)

    bubble = BubbleWidget()
    bubble.set_status(buddy.status_verb)
    bubble.anchor_near(QRect(400, 300, 152, 152), screen)
    assert screen.contains(bubble.geometry())
    bubble.close()
