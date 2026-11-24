"""Retro RPG / Game Boy dark-indigo session statistics HUD card."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jules_pet.sprites import get_sprite_pixmap

STATS_CARD_STYLESHEET = """
QWidget#statsCardWindow {
    background-color: #1A1033;
    font-family: "Consolas", "Courier New", monospace;
}
QFrame#statsCardFrame {
    background-color: #1A1033;
    border: 2px solid #705BD6;
    border-radius: 6px;
    font-family: "Consolas", "Courier New", monospace;
}
QFrame#statsSection {
    background-color: #140B29;
    border: 1px solid #3B2870;
    border-radius: 4px;
}
QLabel#cardTitle {
    color: #FACC15;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11pt;
    font-weight: 700;
    background: transparent;
}
QLabel#cardSubtitle {
    color: #C4B5FD;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 8pt;
    background: transparent;
}
QLabel#durationBadge {
    background-color: #2A194D;
    color: #38BDF8;
    border: 1px solid #705BD6;
    border-radius: 4px;
    padding: 2px 7px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 8.5pt;
    font-weight: 700;
}
QLabel#statKey {
    color: #9B87F5;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 8.5pt;
    font-weight: 700;
    background: transparent;
}
QLabel#statValue {
    color: #E6DCFF;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 9.5pt;
    font-weight: 700;
    background: transparent;
}
QLabel#barLabel {
    color: #E6DCFF;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 8.5pt;
    font-weight: 700;
    background: transparent;
}
QLabel#moodBadge {
    color: #F472B6;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 8.5pt;
    font-weight: 700;
    background: transparent;
}
QProgressBar#energyBar {
    background-color: #0E0720;
    border: 2px solid #705BD6;
    border-radius: 3px;
    text-align: center;
    color: #E6DCFF;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 8pt;
    font-weight: 700;
    min-height: 16px;
    max-height: 16px;
}
QProgressBar#energyBar::chunk {
    background-color: #38BDF8;
    width: 8px;
    margin: 1px;
}
QProgressBar#moodBar {
    background-color: #0E0720;
    border: 2px solid #705BD6;
    border-radius: 3px;
    text-align: center;
    color: #E6DCFF;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 8pt;
    font-weight: 700;
    min-height: 16px;
    max-height: 16px;
}
QProgressBar#moodBar::chunk {
    background-color: #F472B6;
    width: 8px;
    margin: 1px;
}
QPushButton#exportButton {
    background-color: #705BD6;
    color: #FFFFFF;
    border: 2px solid #9B87F5;
    border-radius: 4px;
    padding: 6px 12px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 9pt;
    font-weight: 700;
}
QPushButton#exportButton:hover {
    background-color: #8470E8;
}
QPushButton#exportButton:pressed {
    background-color: #4E39A8;
}
"""


@dataclass
class SessionStats:
    """Snapshot of session telemetry and Tamagotchi state for the HUD card."""

    total_tokens: int = 0
    total_subagents: int = 0
    commands_succeeded: int = 0
    commands_total: int = 0
    pet_count: int = 0
    energy: float = 85.0
    mood_score: float = 80.0
    mood_label: str = "De boas"
    session_duration_seconds: float = 0.0


def _clamp_percent(value: float) -> int:
    return max(0, min(100, int(round(float(value)))))


def format_tokens(tokens: int) -> str:
    """Format token counts cleanly (e.g., 420, 18.5K, 1.25M)."""
    count = max(0, int(tokens))
    if count < 1_000:
        return str(count)
    if count < 1_000_000:
        formatted = f"{count / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"{formatted}K"
    formatted = f"{count / 1_000_000:.2f}".rstrip("0").rstrip(".")
    return f"{formatted}M"


def format_duration(seconds: float) -> str:
    """Format elapsed seconds as MM:SS or HH:MM:SS."""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class StatsCardWindow(QWidget):
    """Retro RPG / Game Boy dark-indigo HUD card showing Jules session stats."""

    def __init__(
        self,
        stats: SessionStats | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("statsCardWindow")
        self.setWindowTitle("Jules // RPG Stats")
        self.setStyleSheet(STATS_CARD_STYLESHEET)
        self.setMinimumWidth(360)

        self._stats: SessionStats = stats or SessionStats()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)

        self._frame = QFrame(self)
        self._frame.setObjectName("statsCardFrame")
        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(12, 12, 12, 12)
        frame_layout.setSpacing(10)

        # Header with mini Jules sprite, retro title, and duration badge
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        self._avatar_label = QLabel(self._frame)
        self._avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar_pix = get_sprite_pixmap("idle_0", eye_mode="happy", scale=2)
        self._avatar_label.setPixmap(avatar_pix)
        self._avatar_label.setFixedSize(avatar_pix.size())
        header_layout.addWidget(self._avatar_label)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self._title_label = QLabel("JULES // RPG STATS", self._frame)
        self._title_label.setObjectName("cardTitle")
        self._subtitle_label = QLabel("TAMAGOTCHI DEV HUD", self._frame)
        self._subtitle_label.setObjectName("cardSubtitle")
        title_col.addWidget(self._title_label)
        title_col.addWidget(self._subtitle_label)
        header_layout.addLayout(title_col, 1)

        self.duration_label = QLabel("00:00", self._frame)
        self.duration_label.setObjectName("durationBadge")
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.duration_label)

        frame_layout.addLayout(header_layout)

        # Telemetry metrics grid
        metrics_box = QFrame(self._frame)
        metrics_box.setObjectName("statsSection")
        metrics_grid = QGridLayout(metrics_box)
        metrics_grid.setContentsMargins(10, 8, 10, 8)
        metrics_grid.setHorizontalSpacing(14)
        metrics_grid.setVerticalSpacing(6)

        self.tokens_value_label = self._add_stat_row(metrics_grid, 0, "TOKENS")
        self.subagents_value_label = self._add_stat_row(metrics_grid, 1, "SUBAGENTES")
        self.commands_value_label = self._add_stat_row(metrics_grid, 2, "COMANDOS")
        self.pets_value_label = self._add_stat_row(metrics_grid, 3, "CARINHOS")
        metrics_grid.setColumnStretch(1, 1)

        frame_layout.addWidget(metrics_box)

        # Pixel-art Energy & Humor bars
        bars_box = QFrame(self._frame)
        bars_box.setObjectName("statsSection")
        bars_layout = QVBoxLayout(bars_box)
        bars_layout.setContentsMargins(10, 8, 10, 8)
        bars_layout.setSpacing(6)

        energy_header = QHBoxLayout()
        energy_title = QLabel("ENERGIA", bars_box)
        energy_title.setObjectName("barLabel")
        self.energy_value_label = QLabel("85%", bars_box)
        self.energy_value_label.setObjectName("statValue")
        energy_header.addWidget(energy_title)
        energy_header.addStretch(1)
        energy_header.addWidget(self.energy_value_label)
        bars_layout.addLayout(energy_header)

        self.energy_bar = QProgressBar(bars_box)
        self.energy_bar.setObjectName("energyBar")
        self.energy_bar.setRange(0, 100)
        self.energy_bar.setFormat("%p%")
        bars_layout.addWidget(self.energy_bar)

        mood_header = QHBoxLayout()
        mood_title = QLabel("HUMOR", bars_box)
        mood_title.setObjectName("barLabel")
        self.mood_label_widget = QLabel("De boas", bars_box)
        self.mood_label_widget.setObjectName("moodBadge")
        mood_header.addWidget(mood_title)
        mood_header.addStretch(1)
        mood_header.addWidget(self.mood_label_widget)
        bars_layout.addLayout(mood_header)

        self.mood_bar = QProgressBar(bars_box)
        self.mood_bar.setObjectName("moodBar")
        self.mood_bar.setRange(0, 100)
        self.mood_bar.setFormat("%p%")
        bars_layout.addWidget(self.mood_bar)

        frame_layout.addWidget(bars_box)

        # Export button
        self.export_button = QPushButton("Exportar Card (PNG)", self._frame)
        self.export_button.setObjectName("exportButton")
        self.export_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_button.clicked.connect(self._on_export_clicked)
        frame_layout.addWidget(self.export_button)

        root_layout.addWidget(self._frame)

        self.update_stats(self._stats)
        self.adjustSize()

    @staticmethod
    def _add_stat_row(grid: QGridLayout, row: int, label_text: str) -> QLabel:
        key_label = QLabel(label_text)
        key_label.setObjectName("statKey")
        val_label = QLabel("0")
        val_label.setObjectName("statValue")
        val_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(key_label, row, 0)
        grid.addWidget(val_label, row, 1)
        return val_label

    def update_stats(self, stats: SessionStats) -> None:
        """Refresh all displayed counters, mood label, duration, and RPG bars."""
        self._stats = stats

        self.tokens_value_label.setText(format_tokens(stats.total_tokens))
        self.subagents_value_label.setText(str(max(0, int(stats.total_subagents))))
        self.commands_value_label.setText(
            f"{max(0, int(stats.commands_succeeded))}/{max(0, int(stats.commands_total))} concluídos"
        )
        self.pets_value_label.setText(str(max(0, int(stats.pet_count))))
        self.duration_label.setText(format_duration(stats.session_duration_seconds))

        energy_pct = _clamp_percent(stats.energy)
        mood_pct = _clamp_percent(stats.mood_score)

        self.energy_bar.setValue(energy_pct)
        self.energy_value_label.setText(f"{energy_pct}%")
        self.mood_bar.setValue(mood_pct)
        self.mood_label_widget.setText(stats.mood_label or "De boas")

    def export_png(self, path: Path | str) -> bool:
        """Render the current stats card into a PNG file at ``path``."""
        target = Path(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False

        self.ensurePolished()
        if self.layout() is not None:
            self.layout().activate()
        target_size = self.size().expandedTo(self.sizeHint())
        if target_size.width() <= 0 or target_size.height() <= 0:
            return False
        if self.size() != target_size:
            self.resize(target_size)

        pixmap = QPixmap(target_size)
        pixmap.fill(QColor("#1A1033"))
        self.render(pixmap)
        if pixmap.isNull():
            return False
        return bool(pixmap.save(str(target), "PNG"))

    def _on_export_clicked(self) -> None:
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Card (PNG)",
            "jules_stats_card.png",
            "PNG Images (*.png)",
        )
        if chosen:
            self.export_png(Path(chosen))
