"""Win32 active-window detector and perching target controller."""

from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRect, QTimer, Signal

_DEV_TITLE_KEYWORDS: tuple[str, ...] = (
    "visual studio code",
    "code - insiders",
    "vs code",
    "antigravity",
    "cursor",
    "windsurf",
    "windows powershell",
    "powershell",
    "windows terminal",
    "intellij idea",
    "pycharm",
    "webstorm",
    "clion",
    "goland",
    "android studio",
    "sublime text",
    "neovim",
    "zed",
)


@dataclass(frozen=True)
class WindowInfo:
    """Snapshot of a foreground top-level window."""

    hwnd: int
    title: str
    rect: QRect
    pid: int
    visible: bool = True
    minimized: bool = False


def is_dev_window_title(title: str) -> bool:
    """Return True if the window title looks like an IDE, editor, or terminal."""
    if not title or not title.strip():
        return False
    lowered = title.casefold()
    return any(keyword in lowered for keyword in _DEV_TITLE_KEYWORDS)


def get_foreground_window_win32() -> WindowInfo | None:
    """Inspect the active foreground Win32 window, or return None on error/non-Windows."""
    if sys.platform != "win32" or not hasattr(ctypes, "windll"):
        return None

    try:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
        else:
            title = ""

        win_rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(win_rect)):
            return None

        width = max(0, int(win_rect.right - win_rect.left))
        height = max(0, int(win_rect.bottom - win_rect.top))
        rect = QRect(int(win_rect.left), int(win_rect.top), width, height)

        visible = bool(user32.IsWindowVisible(hwnd))
        minimized = bool(user32.IsIconic(hwnd))

        pid_dword = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_dword))

        return WindowInfo(
            hwnd=int(hwnd),
            title=title,
            rect=rect,
            pid=int(pid_dword.value),
            visible=visible,
            minimized=minimized,
        )
    except (OSError, AttributeError, ValueError, ctypes.ArgumentError):
        return None


class PerchController(QObject):
    """Polls the active foreground window and emits QRect targets for dev windows."""

    POLL_INTERVAL_MS = 400

    perch_target_changed = Signal(object)

    def __init__(
        self,
        window_provider: Callable[[], WindowInfo | None] | None = None,
        own_pid: int | None = None,
        enabled: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._window_provider: Callable[[], WindowInfo | None] = (
            window_provider if window_provider is not None else get_foreground_window_win32
        )
        self._own_pid = os.getpid() if own_pid is None else int(own_pid)
        self._enabled = bool(enabled)
        self._current_rect: QRect | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self.poll)
        if self._enabled:
            self._timer.start()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def current_rect(self) -> QRect | None:
        return QRect(self._current_rect) if self._current_rect is not None else None

    def set_enabled(self, enabled: bool) -> None:
        new_state = bool(enabled)
        self._enabled = new_state
        if new_state:
            if not self._timer.isActive():
                self._timer.start()
            return

        self._timer.stop()
        if self._current_rect is not None:
            self._current_rect = None
            self.perch_target_changed.emit(None)

    def poll(self) -> None:
        if not self._enabled:
            return

        info = self._window_provider()
        target = self._resolve_target_rect(info)
        if target == self._current_rect:
            return

        self._current_rect = QRect(target) if target is not None else None
        self.perch_target_changed.emit(
            QRect(self._current_rect) if self._current_rect is not None else None
        )

    def _resolve_target_rect(self, info: WindowInfo | None) -> QRect | None:
        if info is None:
            return None
        if not info.visible or info.minimized:
            return None
        if info.pid == self._own_pid:
            return None
        if not info.rect.isValid() or info.rect.width() <= 0 or info.rect.height() <= 0:
            return None
        if not is_dev_window_title(info.title):
            return None
        return info.rect
