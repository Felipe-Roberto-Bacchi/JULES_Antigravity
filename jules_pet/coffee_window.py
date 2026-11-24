"""Frameless pixel-art steaming coffee cup widget for Jules coffee breaks."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

_CUP_COLORS: dict[str, QColor] = {
    "W": QColor("#F8FAFC"),  # Porcelain mug highlight
    "C": QColor("#CBD5E1"),  # Mug shading
    "O": QColor("#1E1B4B"),  # Crisp dark outline
    "F": QColor("#451A03"),  # Dark roast coffee
    "B": QColor("#78350F"),  # Coffee crema
    "S": QColor("#E2E8F0"),  # Steam pixel
    "T": QColor("#94A3B8"),  # Saucer shadow
}

_STEAM_FRAMES: tuple[tuple[str, ...], ...] = (
    (
        ".....S....S.....",
        "......S....S....",
        ".....S....S.....",
        "................",
    ),
    (
        "......S....S....",
        ".....S....S.....",
        "......S....S....",
        "................",
    ),
)

_CUP_ROWS: tuple[str, ...] = (
    "...OOOOOOOOOO...",
    "..OWFFFFFFFFWO..",
    "..OWWBBBBBBWWO..",
    "..OWWWWWWWWWWO..",
    "..OWWWWWWWWWCOOO",
    "..OWWWWCWWWWCO.O",
    "..OWWWWCWWWWCO.O",
    "..OWWWWCWWWWCOOO",
    "..OWWWCCCCCCCO..",
    "...OOOOOOOOOO...",
    ".OOTTTTTTTTTTOO.",
    "..OOOOOOOOOOOO..",
)


class CoffeeCupWindow(QWidget):
    """Frameless, translucent pixel-art steaming coffee cup widget."""

    drink_finished = Signal()

    def __init__(self, scale: int = 3, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scale = max(2, int(scale))
        self._steam_frame = 0
        self._drinking = False
        self._sip_step = 0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        grid_w = 16
        grid_h = len(_STEAM_FRAMES[0]) + len(_CUP_ROWS)
        self.setFixedSize(grid_w * self._scale, grid_h * self._scale)

        self._steam_timer = QTimer(self)
        self._steam_timer.setInterval(220)
        self._steam_timer.timeout.connect(self._on_steam_tick)
        self._steam_timer.start()

        self._drink_timer = QTimer(self)
        self._drink_timer.setSingleShot(True)
        self._drink_timer.timeout.connect(self._on_drink_timeout)

    def cup_center(self) -> QPointF:
        """Return the center point of the coffee cup in screen coordinates."""
        return QPointF(
            self.x() + self.width() / 2.0,
            self.y() + self.height() / 2.0,
        )

    def start_drinking(self, duration_ms: int = 900) -> None:
        """Start the coffee drinking sequence and emit `drink_finished` when done."""
        self._drinking = True
        self._sip_step += 1
        self.update()
        self._drink_timer.stop()
        self._drink_timer.start(max(10, int(duration_ms)))

    def _on_steam_tick(self) -> None:
        self._steam_frame = (self._steam_frame + 1) % len(_STEAM_FRAMES)
        self.update()

    def _on_drink_timeout(self) -> None:
        self._drinking = False
        self.update()
        self.drink_finished.emit()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        steam_rows = _STEAM_FRAMES[self._steam_frame]
        rows = steam_rows + _CUP_ROWS
        s = self._scale

        for row_idx, row in enumerate(rows):
            for col_idx, token in enumerate(row):
                if token == ".":
                    continue
                if self._drinking and token in ("F", "B"):
                    # Show lower coffee level while sipping
                    color = _CUP_COLORS["C"] if row_idx <= 5 else _CUP_COLORS[token]
                else:
                    color = _CUP_COLORS[token]
                painter.fillRect(col_idx * s, row_idx * s, s, s, color)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._steam_timer.stop()
        self._drink_timer.stop()
        super().closeEvent(event)
