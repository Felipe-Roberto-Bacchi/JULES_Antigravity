"""Physical desktop ink splat windows and manager for Jules ink-burst reactions."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import random
import time

from PySide6.QtCore import QObject, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QEnterEvent, QImage, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QWidget

from jules_pet.config import EYE, FRAME_MS

INK_COLOR = EYE  # "#140B29" deep dark indigo/black ink
AUTO_FADE_MS = 3500
WIPE_FADE_MS = 200
SPLAT_VARIANTS: tuple[int, ...] = (0, 1, 2)

_GRID_WIDTH = 16
_GRID_HEIGHT = 22


@dataclass(frozen=True)
class _SplatSpec:
    """Procedural geometry parameters for an ink splat + drip variant."""

    lobes: tuple[tuple[float, float, float, float], ...]
    drips: tuple[tuple[int, int, int], ...]
    droplets: tuple[tuple[int, int, int], ...]


_VARIANT_SPECS: dict[int, _SplatSpec] = {
    0: _SplatSpec(
        lobes=((7.5, 6.0, 4.6, 3.8), (5.0, 5.2, 2.5, 2.4), (10.5, 6.8, 2.4, 2.2)),
        drips=((4, 7, 7), (8, 8, 10), (11, 7, 5)),
        droplets=((2, 3, 1), (13, 4, 1), (8, 19, 1)),
    ),
    1: _SplatSpec(
        lobes=((7.5, 5.5, 5.5, 3.2), (3.8, 6.2, 2.3, 2.0), (11.6, 5.2, 2.3, 2.3)),
        drips=((3, 7, 6), (6, 8, 9), (10, 7, 8), (12, 6, 4)),
        droplets=((2, 10, 1), (13, 12, 1), (6, 18, 1)),
    ),
    2: _SplatSpec(
        lobes=((8.0, 6.5, 4.0, 4.3), (6.0, 4.2, 2.8, 2.4), (10.2, 8.2, 2.4, 2.2)),
        drips=((5, 8, 6), (8, 9, 9), (11, 9, 4)),
        droplets=((3, 3, 1), (13, 5, 1), (8, 19, 2), (4, 16, 1)),
    ),
}


@lru_cache(maxsize=24)
def generate_ink_splat_pixmap(variant: int = 0, scale: int = 4) -> QPixmap:
    """Procedurally generate a crisp pixel-art #140B29 ink drip QPixmap."""
    norm_variant = int(variant) % len(SPLAT_VARIANTS)
    px_scale = max(1, int(scale))
    spec = _VARIANT_SPECS[norm_variant]

    grid = QImage(_GRID_WIDTH, _GRID_HEIGHT, QImage.Format.Format_ARGB32)
    grid.fill(Qt.GlobalColor.transparent)
    ink = QColor(INK_COLOR)

    # Fill organic splat lobes inside a 1-px transparent safety margin
    for y in range(1, _GRID_HEIGHT - 1):
        for x in range(1, _GRID_WIDTH - 1):
            for cx, cy, rx, ry in spec.lobes:
                nx = (x - cx) / rx
                ny = (y - cy) / ry
                if nx * nx + ny * ny <= 1.0:
                    grid.setPixelColor(x, y, ink)
                    break

    # Add vertical gravity drips
    for dx, start_y, length in spec.drips:
        if not (1 <= dx < _GRID_WIDTH - 1):
            continue
        end_y = min(_GRID_HEIGHT - 1, start_y + length)
        for y in range(max(1, start_y), end_y):
            grid.setPixelColor(dx, y, ink)

    # Add detached satellite ink droplets
    for dx, dy, size in spec.droplets:
        for oy in range(size):
            for ox in range(size):
                px, py = dx + ox, dy + oy
                if 1 <= px < _GRID_WIDTH - 1 and 1 <= py < _GRID_HEIGHT - 1:
                    grid.setPixelColor(px, py, ink)

    scaled = grid.scaled(
        _GRID_WIDTH * px_scale,
        _GRID_HEIGHT * px_scale,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
    return QPixmap.fromImage(scaled)


class InkSplatWindow(QWidget):
    """Frameless translucent desktop window showing an ink splat that fades or wipes on hover."""

    finished = Signal()

    def __init__(
        self,
        variant: int = 0,
        *,
        scale: int = 4,
        always_on_top: bool = True,
        auto_fade_ms: int = AUTO_FADE_MS,
        wipe_fade_ms: int = WIPE_FADE_MS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.variant = int(variant) % len(SPLAT_VARIANTS)
        self.scale = max(2, int(scale))
        self.auto_fade_ms = max(1, int(auto_fade_ms))
        self.wipe_fade_ms = max(1, int(wipe_fade_ms))

        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        if always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._pixmap = generate_ink_splat_pixmap(self.variant, scale=self.scale)
        self.resize(self._pixmap.size())

        self._opacity = 1.0
        self._start_opacity = 1.0
        self._fade_duration_ms = 300
        self._fade_start_time = 0.0
        self._wiping = False
        self._finished_emitted = False

        self._auto_fade_timer = QTimer(self)
        self._auto_fade_timer.setSingleShot(True)
        self._auto_fade_timer.setInterval(self.auto_fade_ms)
        self._auto_fade_timer.timeout.connect(self._on_auto_fade_timeout)
        self._auto_fade_timer.start()

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(FRAME_MS)
        self._fade_timer.timeout.connect(self._on_fade_tick)

    @property
    def auto_fade_timer(self) -> QTimer:
        """Timer controlling automatic fade-out after AUTO_FADE_MS."""
        return self._auto_fade_timer

    @property
    def opacity(self) -> float:
        """Current rendered opacity in [0.0, 1.0]."""
        return self._opacity

    @property
    def is_wiping(self) -> bool:
        """Whether the user triggered a fast hover wipe ('limpar o vidro')."""
        return self._wiping

    def trigger_wipe(self) -> None:
        """Start immediate 200ms wipe fade-out when hovered."""
        if self._finished_emitted or self._wiping:
            return
        self._wiping = True
        self._auto_fade_timer.stop()
        self._begin_fade_out(self.wipe_fade_ms)

    def close_immediately(self) -> None:
        """Stop timers, close window immediately, and emit finished once."""
        self._finish()

    def enterEvent(self, event: QEnterEvent) -> None:
        self.trigger_wipe()
        super().enterEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        if self._opacity <= 0.0:
            return
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.end()

    def closeEvent(self, event) -> None:
        self._auto_fade_timer.stop()
        self._fade_timer.stop()
        super().closeEvent(event)

    def _on_auto_fade_timeout(self) -> None:
        if self._finished_emitted or self._wiping:
            return
        fade_ms = min(300, max(40, self.auto_fade_ms)) if self.auto_fade_ms < 300 else 300
        self._begin_fade_out(fade_ms)

    def _begin_fade_out(self, duration_ms: int) -> None:
        if self._finished_emitted:
            return
        self._start_opacity = self._opacity
        self._fade_duration_ms = max(1, int(duration_ms))
        self._fade_start_time = time.monotonic()
        if not self._fade_timer.isActive():
            self._fade_timer.start()

    def _on_fade_tick(self) -> None:
        elapsed_ms = (time.monotonic() - self._fade_start_time) * 1000.0
        progress = min(1.0, elapsed_ms / self._fade_duration_ms)
        self._opacity = max(0.0, self._start_opacity * (1.0 - progress))
        self.update()
        if progress >= 1.0:
            self._finish()

    def _finish(self) -> None:
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self._auto_fade_timer.stop()
        self._fade_timer.stop()
        self._opacity = 0.0
        self.hide()
        self.close()
        self.finished.emit()


class InkSplatManager(QObject):
    """Spawns, clamps, tracks, and cleans up desktop InkSplatWindow bursts."""

    def __init__(
        self,
        *,
        scale: int = 4,
        always_on_top: bool = True,
        auto_fade_ms: int = AUTO_FADE_MS,
        wipe_fade_ms: int = WIPE_FADE_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.scale = max(2, int(scale))
        self.always_on_top = bool(always_on_top)
        self.auto_fade_ms = max(1, int(auto_fade_ms))
        self.wipe_fade_ms = max(1, int(wipe_fade_ms))
        self.active_splats: list[InkSplatWindow] = []

    def spawn_splats(
        self,
        origin: QPointF,
        screen_rect: QRect,
        count: int = 3,
    ) -> list[InkSplatWindow]:
        """Spawn 2-3 ink splats scattered near origin and clamped strictly inside screen_rect."""
        target_count = max(0, min(int(count), 6))
        if target_count == 0:
            return []

        variants = list(SPLAT_VARIANTS)
        random.shuffle(variants)
        base_angle = random.uniform(0.0, math.tau)
        spawned: list[InkSplatWindow] = []

        for idx in range(target_count):
            variant = variants[idx % len(variants)]
            splat = InkSplatWindow(
                variant=variant,
                scale=self.scale,
                always_on_top=self.always_on_top,
                auto_fade_ms=self.auto_fade_ms,
                wipe_fade_ms=self.wipe_fade_ms,
            )
            angle = base_angle + idx * (math.tau / max(1, target_count)) + random.uniform(-0.35, 0.35)
            radius = random.uniform(24.0, 72.0)
            cx = origin.x() + math.cos(angle) * radius
            cy = origin.y() + math.sin(angle) * radius

            raw_x = int(round(cx - splat.width() / 2.0))
            raw_y = int(round(cy - splat.height() / 2.0))
            max_x = max(screen_rect.left(), screen_rect.left() + screen_rect.width() - splat.width())
            max_y = max(screen_rect.top(), screen_rect.top() + screen_rect.height() - splat.height())
            clamped_x = max(screen_rect.left(), min(raw_x, max_x))
            clamped_y = max(screen_rect.top(), min(raw_y, max_y))

            splat.move(clamped_x, clamped_y)
            splat.finished.connect(lambda w=splat: self._on_splat_finished(w))
            self.active_splats.append(splat)
            splat.show()
            spawned.append(splat)

        return spawned

    def clear_all(self) -> None:
        """Immediately close and clean up all active ink splat windows."""
        for splat in list(self.active_splats):
            splat.close_immediately()
        self.active_splats.clear()

    def _on_splat_finished(self, splat: InkSplatWindow) -> None:
        if splat in self.active_splats:
            self.active_splats.remove(splat)
        splat.deleteLater()
