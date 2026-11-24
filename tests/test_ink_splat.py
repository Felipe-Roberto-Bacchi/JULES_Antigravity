"""Headless TDD tests for Fase 2E — physical desktop ink splats."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QEnterEvent, QImage
from PySide6.QtWidgets import QApplication, QWidget

from jules_pet.ink_splat_window import (
    AUTO_FADE_MS,
    INK_COLOR,
    SPLAT_VARIANTS,
    WIPE_FADE_MS,
    InkSplatManager,
    InkSplatWindow,
    generate_ink_splat_pixmap,
)


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _pump_until(predicate, timeout_ms: int = 1200) -> bool:
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


def _opaque_signature(image: QImage) -> tuple[tuple[int, int], ...]:
    coords: list[tuple[int, int]] = []
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 0:
                coords.append((x, y))
    return tuple(coords)


def test_ink_splat_window_flags_and_translucent_attributes(qapp: QApplication) -> None:
    win = InkSplatWindow(variant=0)
    try:
        assert isinstance(win, QWidget)
        assert win.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        assert not win.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        flags = win.windowFlags()
        assert bool(flags & Qt.WindowType.FramelessWindowHint)
        assert bool(flags & Qt.WindowType.WindowStaysOnTopHint)
        assert bool(flags & Qt.WindowType.Tool)
    finally:
        win.close()


def test_procedural_ink_drip_variants_are_140b29_and_distinct(qapp: QApplication) -> None:
    assert INK_COLOR.upper() == "#140B29"
    assert SPLAT_VARIANTS == (0, 1, 2)

    expected_color = QColor("#140B29")
    signatures: set[tuple[tuple[int, int], ...]] = set()

    for variant in SPLAT_VARIANTS:
        pix = generate_ink_splat_pixmap(variant=variant, scale=4)
        assert not pix.isNull()
        assert pix.width() > 0 and pix.height() > 0

        img = pix.toImage()
        # Corners remain transparent
        assert img.pixelColor(0, 0).alpha() == 0
        assert img.pixelColor(img.width() - 1, 0).alpha() == 0

        opaque_colors = {
            img.pixelColor(x, y).name().upper()
            for y in range(img.height())
            for x in range(img.width())
            if img.pixelColor(x, y).alpha() > 0
        }
        assert opaque_colors == {expected_color.name().upper()}

        sig = _opaque_signature(img)
        assert len(sig) > 20
        signatures.add(sig)

        # Verify InkSplatWindow paints the procedural ink sprite
        win = InkSplatWindow(variant=variant, scale=4)
        try:
            canvas = QImage(win.size(), QImage.Format.Format_ARGB32_Premultiplied)
            canvas.fill(Qt.GlobalColor.transparent)
            win.render(canvas)

            has_ink_pixel = any(
                canvas.pixelColor(x, y).alpha() > 0
                and canvas.pixelColor(x, y).red() == expected_color.red()
                and canvas.pixelColor(x, y).green() == expected_color.green()
                and canvas.pixelColor(x, y).blue() == expected_color.blue()
                for y in range(canvas.height())
                for x in range(canvas.width())
            )
            assert has_ink_pixel
        finally:
            win.close()

    assert len(signatures) == 3


def test_auto_fade_timer_defaults_and_emits_finished(qapp: QApplication) -> None:
    assert AUTO_FADE_MS == 3500

    default_win = InkSplatWindow(variant=1)
    try:
        assert default_win.auto_fade_timer.interval() == 3500
        assert default_win.auto_fade_timer.isActive()
    finally:
        default_win.close()

    fast_win = InkSplatWindow(variant=2, auto_fade_ms=40)
    finished_events: list[bool] = []
    fast_win.finished.connect(lambda: finished_events.append(True))
    fast_win.show()

    assert _pump_until(lambda: len(finished_events) == 1, timeout_ms=1000)
    assert fast_win.opacity == 0.0
    assert not fast_win.isVisible()


def test_enter_event_wipes_glass_with_200ms_fade_and_emits_finished(qapp: QApplication) -> None:
    assert WIPE_FADE_MS == 200

    win = InkSplatWindow(variant=0, auto_fade_ms=3500)
    finished_events: list[bool] = []
    win.finished.connect(lambda: finished_events.append(True))
    win.show()
    assert win.auto_fade_timer.isActive()
    assert win.opacity == 1.0

    enter = QEnterEvent(QPointF(10.0, 10.0), QPointF(10.0, 10.0), QPointF(10.0, 10.0))
    QApplication.sendEvent(win, enter)

    assert not win.auto_fade_timer.isActive()
    assert win.is_wiping

    assert _pump_until(lambda: len(finished_events) == 1, timeout_ms=800)
    assert len(finished_events) == 1
    assert win.opacity == 0.0
    assert not win.isVisible()


def test_manager_spawns_clamped_splats_cleans_up_on_finish_and_clears_all(qapp: QApplication) -> None:
    manager = InkSplatManager()
    screen_rect = QRect(100, 50, 800, 600)

    try:
        # Spawn near bottom-right corner and outside top-left boundary to verify strict clamping
        splats_br = manager.spawn_splats(QPointF(920.0, 660.0), screen_rect, count=3)
        assert len(splats_br) == 3
        assert len(manager.active_splats) == 3

        for splat in splats_br:
            assert isinstance(splat, InkSplatWindow)
            assert screen_rect.contains(splat.geometry())

        splats_tl = manager.spawn_splats(QPointF(-50.0, -50.0), screen_rect, count=2)
        assert len(splats_tl) == 2
        assert len(manager.active_splats) == 5

        for splat in splats_tl:
            assert screen_rect.contains(splat.geometry())

        # Wiping one splat removes only that splat from active_splats when finished
        target = splats_br[0]
        QApplication.sendEvent(
            target,
            QEnterEvent(QPointF(8.0, 8.0), QPointF(8.0, 8.0), QPointF(8.0, 8.0)),
        )
        assert _pump_until(lambda: target not in manager.active_splats, timeout_ms=800)
        assert len(manager.active_splats) == 4

        # clear_all() closes all remaining splats immediately
        remaining = list(manager.active_splats)
        manager.clear_all()
        qapp.processEvents()
        assert manager.active_splats == []
        for splat in remaining:
            assert not splat.isVisible()
    finally:
        manager.clear_all()
