"""Headless TDD tests for Tamagotchi coffee break, exhaustion, perching, and session counters."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
import pytest
from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtWidgets import QApplication

from jules_pet.buddy import BuddySessionModel
from jules_pet.coffee_window import CoffeeCupWindow
from jules_pet.config import PADDING_Y
from jules_pet.physics import PetController, PetState


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_coffee_cup_window_geometry_and_drink_signal(qapp: QApplication) -> None:
    cup = CoffeeCupWindow()
    try:
        assert bool(cup.windowFlags() & Qt.WindowType.FramelessWindowHint)
        assert cup.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        cup.move(300, 400)
        cup.show()
        qapp.processEvents()

        center = cup.cup_center()
        assert isinstance(center, QPointF)
        assert center.x() == pytest.approx(cup.x() + cup.width() / 2.0)
        assert center.y() == pytest.approx(cup.y() + cup.height() / 2.0)

        finished: list[bool] = []
        cup.drink_finished.connect(lambda: finished.append(True))

        cup.start_drinking(duration_ms=40)
        deadline = time.monotonic() + 1.0
        while not finished and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.01)

        assert finished == [True]
    finally:
        cup.close()


def test_physics_coffee_break_steers_sips_emits_particles_and_returns_idle(
    qapp: QApplication,
) -> None:
    screen = QRect(0, 0, 1920, 1080)
    ctrl = PetController(scale=4, x=120.0, y=120.0)
    cup_center = QPointF(420.0, 280.0)

    arrived_calls: list[bool] = []
    ctrl.start_coffee_break(cup_center, on_arrived=lambda: arrived_calls.append(True))
    assert ctrl.state == PetState.COFFEE_BREAK

    saw_steam = False
    saw_heart = False
    for _ in range(240):
        ctrl.update(1 / 60, screen, QPointF(0, 0))
        if any(p.kind == "steam" for p in ctrl.particles):
            saw_steam = True
        if any(p.kind == "heart" for p in ctrl.particles):
            saw_heart = True
        if ctrl.state == PetState.IDLE and arrived_calls:
            break

    assert arrived_calls == [True]
    assert saw_steam is True
    assert saw_heart is True
    assert ctrl.state == PetState.IDLE


def test_physics_perched_state_places_jules_on_top_and_clamps(qapp: QApplication) -> None:
    screen = QRect(0, 0, 1280, 720)
    ctrl = PetController(scale=4)
    ctrl.center_on(screen)

    target_rect = QRect(300, 260, 600, 400)
    ctrl.set_perch_rect(target_rect)
    assert ctrl.state == PetState.PERCHED

    ctrl.update(1 / 60, screen, QPointF(0, 0))
    sprite_bottom = ctrl.y + PADDING_Y + ctrl.sprite_height
    assert sprite_bottom == pytest.approx(float(target_rect.top()), abs=2.0)
    assert ctrl.x >= ctrl._min_x(screen)
    assert ctrl.x <= ctrl._max_x(screen)

    # Off-screen top rect must still clamp inside screen_rect
    ctrl.set_perch_rect(QRect(20, -200, 300, 400))
    ctrl.update(1 / 60, screen, QPointF(0, 0))
    assert ctrl.y >= ctrl._min_y(screen)
    assert ctrl.x >= ctrl._min_x(screen)

    ctrl.set_perch_rect(None)
    assert ctrl.state == PetState.IDLE


def test_physics_exhausted_state_sleep_eyes_and_slow_zzz(qapp: QApplication) -> None:
    screen = QRect(0, 0, 1920, 1080)
    ctrl = PetController(scale=4)
    ctrl.set_ai_activity("coding", "coding")

    ctrl.set_exhausted(True)
    assert ctrl.state == PetState.EXHAUSTED
    assert ctrl.current_eye_mode() == "sleep"

    ctrl.particles.clear()
    for _ in range(15):
        ctrl.update(0.05, screen, QPointF(0, 0))
        assert ctrl.current_eye_mode() == "sleep"

    zzz_particles = [p for p in ctrl.particles if p.kind == "zzz"]
    assert len(zzz_particles) >= 1

    ctrl.set_exhausted(False)
    assert ctrl.state == PetState.IDLE


def test_buddy_session_counters_coffee_break_and_burnout(qapp: QApplication) -> None:
    buddy = BuddySessionModel()

    assert buddy.session_duration_seconds == pytest.approx(0.0)
    assert buddy.total_tokens == 0
    assert buddy.total_subagents == 0
    assert buddy.commands_succeeded == 0
    assert buddy.commands_total == 0
    assert buddy.pet_count == 0
    assert buddy.is_exhausted is False

    # Counters track tokens, subagents, commands, pets, and duration
    buddy.update_context(120_000, 80_000, 0.2)
    assert buddy.total_tokens == 200_000

    buddy.record_subagent_spawn()
    buddy.record_subagent_spawn()
    assert buddy.total_subagents == 2

    buddy.handle_event({"type": "tool_end", "tool": "run_command", "ok": True})
    buddy.handle_event({"type": "tool_end", "tool": "run_command", "ok": False, "error": "boom"})
    assert buddy.commands_total == 2
    assert buddy.commands_succeeded == 1

    buddy.on_pet()
    assert buddy.pet_count == 1

    # Low energy (< 20.0) triggers exhaustion
    buddy.energy = 15.0
    buddy.tick(1.0)
    assert buddy.session_duration_seconds == pytest.approx(1.0)
    assert buddy.is_exhausted is True
    assert buddy.status_verb == "Turno da madrugada... só mais 5 minutinhos..."

    # Coffee break boosts energy (+30 capped at 100) and mood_score (+20 capped at 100), clears exhaustion
    buddy.energy = 80.0
    buddy.mood_score = 90.0
    buddy.take_coffee_break()
    assert buddy.energy == pytest.approx(100.0)
    assert buddy.mood_score == pytest.approx(100.0)
    assert buddy.is_exhausted is False
    assert buddy.status_verb != "Turno da madrugada... só mais 5 minutinhos..."

    # Long session (>= 10800s / 3 hours) triggers exhaustion even with full energy
    buddy_long = BuddySessionModel()
    buddy_long.tick(10800.0)
    assert buddy_long.session_duration_seconds >= 10800.0
    assert buddy_long.is_exhausted is True
    assert buddy_long.status_verb == "Turno da madrugada... só mais 5 minutinhos..."

    # Coffee break clears 3-hour exhaustion too
    buddy_long.take_coffee_break()
    assert buddy_long.is_exhausted is False
    assert buddy_long.status_verb != "Turno da madrugada... só mais 5 minutinhos..."
