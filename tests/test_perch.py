"""Headless unit tests for Win32 active-window perching controller."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from jules_pet.perch_controller import (
    PerchController,
    WindowInfo,
    get_foreground_window_win32,
    is_dev_window_title,
)


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.mark.parametrize(
    "title",
    [
        "main.py - Visual Studio Code",
        "Antigravity",
        "Cursor",
        "Windows PowerShell",
        "Windows Terminal",
        "IntelliJ IDEA",
        "PyCharm",
    ],
)
def test_is_dev_window_title_matches_dev_tools(title: str) -> None:
    assert is_dev_window_title(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "Google Chrome",
        "YouTube",
        "Spotify",
        "",
    ],
)
def test_is_dev_window_title_rejects_non_dev_windows(title: str) -> None:
    assert is_dev_window_title(title) is False


def test_perch_controller_emits_on_dev_window_and_move_resize(qapp: QApplication) -> None:
    current: list[WindowInfo | None] = [
        WindowInfo(
            hwnd=101,
            title="main.py - Visual Studio Code",
            rect=QRect(100, 80, 1200, 800),
            pid=4242,
            visible=True,
            minimized=False,
        )
    ]

    ctrl = PerchController(
        window_provider=lambda: current[0],
        own_pid=9999,
        enabled=True,
    )
    assert ctrl.POLL_INTERVAL_MS == 400
    assert ctrl.enabled is True
    assert ctrl.current_rect is None

    received: list[QRect | None] = []
    ctrl.perch_target_changed.connect(received.append)

    ctrl.poll()
    assert received == [QRect(100, 80, 1200, 800)]
    assert ctrl.current_rect == QRect(100, 80, 1200, 800)

    # Polling again with identical geometry must not re-emit.
    ctrl.poll()
    assert len(received) == 1

    # Moving/resizing the dev window emits the new QRect.
    current[0] = WindowInfo(
        hwnd=101,
        title="main.py - Visual Studio Code",
        rect=QRect(200, 120, 1000, 700),
        pid=4242,
        visible=True,
        minimized=False,
    )
    ctrl.poll()
    assert received == [
        QRect(100, 80, 1200, 800),
        QRect(200, 120, 1000, 700),
    ]
    assert ctrl.current_rect == QRect(200, 120, 1000, 700)

    ctrl.set_enabled(False)


def test_perch_controller_clears_on_non_dev_minimized_hidden_or_own_pid(
    qapp: QApplication,
) -> None:
    dev_win = WindowInfo(
        hwnd=202,
        title="Cursor",
        rect=QRect(50, 50, 900, 600),
        pid=1234,
        visible=True,
        minimized=False,
    )
    current: list[WindowInfo | None] = [dev_win]

    ctrl = PerchController(
        window_provider=lambda: current[0],
        own_pid=9999,
        enabled=True,
    )
    received: list[QRect | None] = []
    ctrl.perch_target_changed.connect(received.append)

    # Start perched on dev window
    ctrl.poll()
    assert received[-1] == QRect(50, 50, 900, 600)

    # Switch to non-dev window (Chrome) -> emits None
    current[0] = WindowInfo(
        hwnd=203,
        title="Google Chrome",
        rect=QRect(0, 0, 1280, 720),
        pid=2222,
        visible=True,
        minimized=False,
    )
    ctrl.poll()
    assert received[-1] is None
    assert ctrl.current_rect is None

    # Re-perch, then minimize -> emits None
    current[0] = dev_win
    ctrl.poll()
    assert received[-1] == QRect(50, 50, 900, 600)

    current[0] = WindowInfo(
        hwnd=202,
        title="Cursor",
        rect=QRect(50, 50, 900, 600),
        pid=1234,
        visible=True,
        minimized=True,
    )
    ctrl.poll()
    assert received[-1] is None

    # Re-perch, then hidden (visible=False) -> emits None
    current[0] = dev_win
    ctrl.poll()
    assert received[-1] == QRect(50, 50, 900, 600)

    current[0] = WindowInfo(
        hwnd=202,
        title="Cursor",
        rect=QRect(50, 50, 900, 600),
        pid=1234,
        visible=False,
        minimized=False,
    )
    ctrl.poll()
    assert received[-1] is None

    # Re-perch, then own_pid -> emits None
    current[0] = dev_win
    ctrl.poll()
    assert received[-1] == QRect(50, 50, 900, 600)

    current[0] = WindowInfo(
        hwnd=202,
        title="Antigravity",
        rect=QRect(50, 50, 900, 600),
        pid=9999,
        visible=True,
        minimized=False,
    )
    ctrl.poll()
    assert received[-1] is None

    ctrl.set_enabled(False)


def test_perch_controller_set_enabled_false_clears_when_perched(qapp: QApplication) -> None:
    current: list[WindowInfo | None] = [
        WindowInfo(
            hwnd=303,
            title="Windows Terminal",
            rect=QRect(10, 20, 800, 500),
            pid=5555,
            visible=True,
            minimized=False,
        )
    ]

    ctrl = PerchController(
        window_provider=lambda: current[0],
        own_pid=9999,
        enabled=True,
    )
    received: list[QRect | None] = []
    ctrl.perch_target_changed.connect(received.append)

    ctrl.poll()
    assert received == [QRect(10, 20, 800, 500)]
    assert ctrl.current_rect == QRect(10, 20, 800, 500)

    ctrl.set_enabled(False)
    assert ctrl.enabled is False
    assert ctrl.current_rect is None
    assert received == [QRect(10, 20, 800, 500), None]

    # Calling set_enabled(False) again while already cleared should not re-emit None
    ctrl.set_enabled(False)
    assert received == [QRect(10, 20, 800, 500), None]

    # Polling while disabled does nothing
    ctrl.poll()
    assert received == [QRect(10, 20, 800, 500), None]


def test_get_foreground_window_win32_returns_window_info_or_none(qapp: QApplication) -> None:
    result = get_foreground_window_win32()
    assert result is None or isinstance(result, WindowInfo)
