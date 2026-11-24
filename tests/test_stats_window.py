"""Headless unit tests for Retro RPG StatsCardWindow and SessionStats."""

from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QPushButton, QWidget

from jules_pet.stats_window import SessionStats, StatsCardWindow


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_session_stats_dataclass_fields_and_defaults() -> None:
    expected_fields = {
        "total_tokens",
        "total_subagents",
        "commands_succeeded",
        "commands_total",
        "pet_count",
        "energy",
        "mood_score",
        "mood_label",
        "session_duration_seconds",
    }
    actual_fields = {f.name for f in fields(SessionStats)}
    assert expected_fields.issubset(actual_fields)

    default_stats = SessionStats()
    assert default_stats.total_tokens == 0
    assert default_stats.total_subagents == 0
    assert default_stats.commands_succeeded == 0
    assert default_stats.commands_total == 0
    assert default_stats.pet_count == 0
    assert 0 <= default_stats.energy <= 100
    assert 0 <= default_stats.mood_score <= 100
    assert isinstance(default_stats.mood_label, str)
    assert default_stats.session_duration_seconds == 0

    custom = SessionStats(
        total_tokens=15400,
        total_subagents=4,
        commands_succeeded=18,
        commands_total=20,
        pet_count=7,
        energy=82.5,
        mood_score=91.0,
        mood_label="Radiante",
        session_duration_seconds=3665,
    )
    assert custom.total_tokens == 15400
    assert custom.commands_succeeded == 18
    assert custom.commands_total == 20
    assert custom.mood_label == "Radiante"


def test_stats_card_window_retro_qss_and_widgets(qapp: QApplication) -> None:
    window = StatsCardWindow()
    assert isinstance(window, QWidget)

    stylesheet = window.styleSheet()
    assert "#1A1033" in stylesheet
    assert "#705BD6" in stylesheet
    assert any(
        token in stylesheet.lower()
        for token in ("monospace", "consolas", "courier")
    )

    buttons = window.findChildren(QPushButton)
    assert any("Exportar Card (PNG)" in btn.text() for btn in buttons)

    bars = window.findChildren(QProgressBar)
    assert len(bars) >= 2
    for bar in bars:
        assert bar.minimum() == 0
        assert bar.maximum() == 100


def test_update_stats_updates_labels_and_bars(qapp: QApplication) -> None:
    window = StatsCardWindow()

    stats = SessionStats(
        total_tokens=18500,
        total_subagents=3,
        commands_succeeded=18,
        commands_total=20,
        pet_count=9,
        energy=64.0,
        mood_score=88.0,
        mood_label="Em chamas",
        session_duration_seconds=125,
    )
    window.update_stats(stats)

    label_texts = [lbl.text() for lbl in window.findChildren(QLabel)]
    joined = "\n".join(label_texts)

    assert "18.5K" in joined
    assert "3" in joined
    assert "18/20 concluídos" in joined
    assert "9" in joined
    assert "Em chamas" in joined
    assert "02:05" in joined

    assert window.energy_bar.value() == 64
    assert window.mood_bar.value() == 88

    # Update again with edge values to confirm dynamic refresh and clamping
    updated = SessionStats(
        total_tokens=1_250_000,
        total_subagents=12,
        commands_succeeded=5,
        commands_total=5,
        pet_count=42,
        energy=130.0,
        mood_score=-15.0,
        mood_label="Sonolento",
        session_duration_seconds=3661,
    )
    window.update_stats(updated)

    label_texts_2 = [lbl.text() for lbl in window.findChildren(QLabel)]
    joined_2 = "\n".join(label_texts_2)

    assert "1.25M" in joined_2
    assert "12" in joined_2
    assert "5/5 concluídos" in joined_2
    assert "42" in joined_2
    assert "Sonolento" in joined_2
    assert "01:01:01" in joined_2

    assert window.energy_bar.value() == 100
    assert window.mood_bar.value() == 0


def test_export_png_creates_valid_image(qapp: QApplication, tmp_path: Path) -> None:
    window = StatsCardWindow(
        stats=SessionStats(
            total_tokens=420,
            total_subagents=2,
            commands_succeeded=10,
            commands_total=12,
            pet_count=5,
            energy=90.0,
            mood_score=95.0,
            mood_label="Felizão",
            session_duration_seconds=75,
        )
    )

    out_path = tmp_path / "exports" / "jules_stats.png"
    ok = window.export_png(out_path)

    assert ok is True
    assert out_path.exists()
    data = out_path.read_bytes()
    assert len(data) > 0
    assert data.startswith(b"\x89PNG\r\n\x1a\n")

    pixmap = QPixmap(str(out_path))
    assert pixmap.isNull() is False
    assert pixmap.width() > 100
    assert pixmap.height() > 100
