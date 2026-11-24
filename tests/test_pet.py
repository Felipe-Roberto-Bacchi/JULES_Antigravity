"""Headless unit tests for Jules Desktop Pet sprites, physics, and window."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math
import pytest
from PySide6.QtCore import QPointF, QRect
from PySide6.QtWidgets import QApplication

from jules_pet.config import FOLLOW_STOP_RADIUS, GRID_HEIGHT, GRID_WIDTH, PIXEL_SCALES
from jules_pet.physics import PetController, PetState
from jules_pet.sprites import TENTACLE_FRAMES, create_tray_icon, get_sprite_pixmap


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_sprite_dimensions_and_transparency(qapp: QApplication) -> None:
    for scale in PIXEL_SCALES.values():
        for frame in TENTACLE_FRAMES:
            for eye_mode in ("normal", "blink", "happy", "surprised", "sleep"):
                pix = get_sprite_pixmap(frame, eye_mode=eye_mode, scale=scale)
                assert not pix.isNull()
                assert pix.width() == GRID_WIDTH * scale
                assert pix.height() == GRID_HEIGHT * scale
                img = pix.toImage()
                # Corners must be transparent
                assert img.pixelColor(0, 0).alpha() == 0
                assert img.pixelColor(pix.width() - 1, 0).alpha() == 0

    icon = create_tray_icon()
    assert not icon.isNull()


def test_controller_clamps_within_screen_after_roam_and_throw(qapp: QApplication) -> None:
    screen = QRect(0, 0, 1280, 720)
    ctrl = PetController(scale=4)
    ctrl.center_on(screen)

    # High-velocity drag release toward top-left
    ctrl.start_drag()
    ctrl.update_drag(-5000.0, -5000.0, screen)
    ctrl.end_drag(-50.0, -50.0)
    for _ in range(120):
        ctrl.update(1 / 60, screen, QPointF(640, 360))

    assert ctrl.x >= ctrl._min_x(screen)
    assert ctrl.x <= ctrl._max_x(screen)
    assert ctrl.y >= ctrl._min_y(screen)
    assert ctrl.y <= ctrl._max_y(screen)


def test_follow_mouse_stops_at_radius(qapp: QApplication) -> None:
    screen = QRect(0, 0, 1920, 1080)
    ctrl = PetController(scale=4, x=100.0, y=100.0, follow_mouse=True)
    target = QPointF(900.0, 500.0)

    for _ in range(360):
        ctrl.update(1 / 60, screen, target)

    dist = math.hypot(ctrl.sprite_center.x() - target.x(), ctrl.sprite_center.y() - target.y())
    assert dist <= FOLLOW_STOP_RADIUS + 20.0
    assert dist >= FOLLOW_STOP_RADIUS * 0.5


def test_click_double_click_and_sleep_transitions(qapp: QApplication) -> None:
    screen = QRect(0, 0, 1920, 1080)
    ctrl = PetController(scale=4)

    ctrl.trigger_click_reaction()
    assert ctrl.happy_timer > 0.0
    assert len(ctrl.particles) >= 4
    assert ctrl.current_eye_mode() == "happy"

    ctrl.trigger_double_click_reaction()
    assert ctrl.vy < 0.0
    assert any(p.kind == "heart" for p in ctrl.particles)

    ctrl.toggle_sleep()
    assert ctrl.state == PetState.SLEEP
    assert ctrl.current_eye_mode() == "sleep"
    for _ in range(10):
        ctrl.update(0.05, screen, QPointF(0, 0))
    assert any(p.kind == "zzz" for p in ctrl.particles)

    # Clicking wakes Jules up
    ctrl.trigger_click_reaction()
    assert ctrl.state != PetState.SLEEP
