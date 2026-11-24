"""Floating dark-indigo QSS status and approval micro-bubble widget."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

BUBBLE_STYLESHEET = """
QFrame#bubbleFrame {
    background-color: #1A1033;
    border: 2px solid #705BD6;
    border-radius: 10px;
    font-family: "Segoe UI", sans-serif;
}
QLabel#statusLabel {
    color: #E6DCFF;
    font-family: "Segoe UI", sans-serif;
    font-size: 9.5pt;
    font-weight: 500;
    background: transparent;
}
QLabel#overflowBadge {
    background-color: #705BD6;
    color: #FFFFFF;
    border-radius: 8px;
    padding: 1px 7px;
    font-family: "Segoe UI", sans-serif;
    font-size: 8.5pt;
    font-weight: 700;
}
QLabel#commandLabel {
    color: #C4B5FD;
    background-color: #140B29;
    border: 1px solid #3B2870;
    border-radius: 5px;
    padding: 4px 6px;
    font-family: "Segoe UI", sans-serif;
    font-size: 8.5pt;
}
QPushButton#allowButton {
    background-color: #705BD6;
    color: #FFFFFF;
    border: 1px solid #9B87F5;
    border-radius: 5px;
    padding: 4px 10px;
    font-family: "Segoe UI", sans-serif;
    font-size: 8.5pt;
    font-weight: 600;
}
QPushButton#allowButton:hover {
    background-color: #8470E8;
}
QPushButton#allowButton:pressed {
    background-color: #5B46B8;
}
QPushButton#denyButton {
    background-color: #2A194D;
    color: #FB7185;
    border: 1px solid #FB7185;
    border-radius: 5px;
    padding: 4px 10px;
    font-family: "Segoe UI", sans-serif;
    font-size: 8.5pt;
    font-weight: 600;
}
QPushButton#denyButton:hover {
    background-color: #3D2166;
}
QPushButton#denyButton:pressed {
    background-color: #1E1038;
}
"""


class BubbleWidget(QWidget):
    """Frameless translucent micro-bubble showing status, swarm +N badge, and approvals."""

    approval_decided = Signal(str, str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        always_on_top: bool = True,
    ) -> None:
        super().__init__(parent)
        self._always_on_top = always_on_top
        self._overflow_count: int = 0
        self._pending_request_id: str | None = None

        self._apply_window_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(BUBBLE_STYLESHEET)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self._frame = QFrame(self)
        self._frame.setObjectName("bubbleFrame")
        root_layout.addWidget(self._frame)

        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(10, 7, 10, 7)
        frame_layout.setSpacing(6)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.status_label = QLabel("De boas no aquário...", self._frame)
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setMaximumWidth(230)
        header_layout.addWidget(self.status_label, 1)

        self.overflow_badge = QLabel("", self._frame)
        self.overflow_badge.setObjectName("overflowBadge")
        self.overflow_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overflow_badge.hide()
        header_layout.addWidget(self.overflow_badge, 0, Qt.AlignmentFlag.AlignTop)

        frame_layout.addLayout(header_layout)

        self.approval_bar = QWidget(self._frame)
        approval_layout = QVBoxLayout(self.approval_bar)
        approval_layout.setContentsMargins(0, 2, 0, 0)
        approval_layout.setSpacing(5)

        self.command_label = QLabel("", self.approval_bar)
        self.command_label.setObjectName("commandLabel")
        self.command_label.setWordWrap(True)
        self.command_label.setMaximumWidth(240)
        approval_layout.addWidget(self.command_label)

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(6)

        self.allow_button = QPushButton("Permitir", self.approval_bar)
        self.allow_button.setObjectName("allowButton")
        self.allow_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.allow_button.clicked.connect(lambda: self._decide("allow"))

        self.deny_button = QPushButton("Bloquear", self.approval_bar)
        self.deny_button.setObjectName("denyButton")
        self.deny_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.deny_button.clicked.connect(lambda: self._decide("deny"))

        buttons_layout.addWidget(self.allow_button)
        buttons_layout.addWidget(self.deny_button)
        approval_layout.addLayout(buttons_layout)

        self.approval_bar.hide()
        frame_layout.addWidget(self.approval_bar)

        self.adjustSize()

    def _apply_window_flags(self) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        if self._always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    @property
    def status_text(self) -> str:
        return self.status_label.text()

    @property
    def overflow_count(self) -> int:
        return self._overflow_count

    @property
    def pending_request_id(self) -> str | None:
        return self._pending_request_id

    def set_status(self, text: str) -> None:
        """Update the bubble status text and refit the bubble bounds."""
        self.status_label.setText(text)
        self.adjustSize()

    def set_swarm_overflow(self, count: int) -> None:
        """Show or hide the `+N` swarm overflow badge when clones exceed the cap."""
        self._overflow_count = max(0, int(count))
        if self._overflow_count > 0:
            self.overflow_badge.setText(f"+{self._overflow_count}")
            self.overflow_badge.show()
        else:
            self.overflow_badge.clear()
            self.overflow_badge.hide()
        self.adjustSize()

    def show_approval(self, request_id: str, tool: str, command: str) -> None:
        """Display the interactive `[Permitir]` / `[Bloquear]` approval prompt."""
        self._pending_request_id = request_id
        preview = command.strip() or tool.strip()
        if len(preview) > 120:
            preview = preview[:117] + "..."
        label_text = f"{tool}: {preview}" if tool and preview != tool else preview
        self.command_label.setText(label_text)
        self.approval_bar.show()
        self.adjustSize()

    def hide_approval(self) -> None:
        """Hide the approval bar and clear any pending request ID."""
        self._pending_request_id = None
        self.command_label.clear()
        self.approval_bar.hide()
        self.adjustSize()

    def _decide(self, decision: str) -> None:
        request_id = self._pending_request_id
        self.hide_approval()
        if request_id:
            self.approval_decided.emit(request_id, decision)

    def anchor_near(self, pet_rect: QRect, screen_rect: QRect) -> None:
        """Position the bubble neatly above the pet while staying inside screen_rect."""
        self.adjustSize()
        bw = self.width()
        bh = self.height()

        target_x = pet_rect.center().x() - bw // 2
        target_y = pet_rect.top() - bh - 6
        if target_y < screen_rect.top():
            target_y = pet_rect.bottom() + 6

        clamped_x = max(screen_rect.left(), min(screen_rect.right() - bw, target_x))
        clamped_y = max(screen_rect.top(), min(screen_rect.bottom() - bh, target_y))
        self.move(clamped_x, clamped_y)
