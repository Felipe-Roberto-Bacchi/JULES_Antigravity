"""Recolored mini-Jules subagent clone window with elastic pop, orbit, and high-five."""

from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from jules_pet.config import (
    FRAME_MS,
    GRID_HEIGHT,
    GRID_WIDTH,
    HEART_PINK,
    PADDING_X,
    PADDING_Y,
    SPARKLE_CYAN,
    SPARKLE_YELLOW,
)
from jules_pet.physics import Particle
from jules_pet.sprites import get_sprite_pixmap

_SPAWN_DURATION = 0.35
_HIGH_FIVE_DURATION = 0.25
_FADE_DURATION = 0.25
_RETURN_MAX_DURATION = 0.85


class JulesSubagentWindow(QWidget):
    """Frameless translucent mini-Jules clone orbiting the main pet during subagent runs."""

    finished = Signal(str)

    def __init__(
        self,
        subagent_id: str,
        *,
        role: str = "",
        type_name: str = "",
        hue_shift: float = 0.2,
        scale: int = 3,
        orbit_index: int = 0,
        anchor_center: QPointF | None = None,
        screen_rect: QRect | None = None,
        always_on_top: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.subagent_id = subagent_id
        self.role = role
        self.type_name = type_name
        self.hue_shift = float(hue_shift)
        self.scale = max(2, int(scale))

        self._always_on_top = always_on_top
        self._apply_window_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        tooltip = role.strip() or type_name.strip() or subagent_id
        self.setToolTip(f"Subagente: {tooltip}")

        self._screen_rect = screen_rect or self._default_screen_rect()
        self._anchor_center = (
            QPointF(anchor_center)
            if anchor_center is not None
            else QPointF(self._screen_rect.center())
        )

        self.sprite_width = GRID_WIDTH * self.scale
        self.sprite_height = GRID_HEIGHT * self.scale
        self.window_width = self.sprite_width + PADDING_X * 2
        self.window_height = self.sprite_height + PADDING_Y * 2
        self.resize(self.window_width, self.window_height)

        # Orbit & motion parameters
        angle_seed = (orbit_index * 1.2566) + random.uniform(-0.25, 0.25)
        self._orbit_angle = angle_seed
        self._orbit_radius = 88.0 + (orbit_index % 3) * 22.0
        self._orbit_speed = 1.45 if orbit_index % 2 == 0 else -1.35
        self._bob_phase = random.uniform(0.0, math.tau)
        self._anim_time = 0.0

        # Start slightly offset from main Jules for an elastic pop-out feel
        self.x = self._anchor_center.x() - self.window_width / 2.0 + math.cos(angle_seed) * 18.0
        self.y = self._anchor_center.y() - self.window_height / 2.0 + math.sin(angle_seed) * 12.0
        self._clamp_position()
        self.vx = 0.0
        self.vy = 0.0
        self.facing_left = math.cos(angle_seed) < 0.0

        self.phase = "spawning"
        self._spawn_timer = 0.0
        self._return_timer = 0.0
        self._high_five_timer = 0.0
        self._pop_scale = 0.35
        self._opacity = 1.0
        self._finished_emitted = False
        self.particles: list[Particle] = []

        self.move(int(round(self.x)), int(round(self.y)))

        self._last_tick = time.monotonic()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(FRAME_MS)

    def _apply_window_flags(self) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        if self._always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def _default_screen_rect(self) -> QRect:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return QRect(0, 0, 1920, 1080)
        return screen.availableGeometry()

    @property
    def pop_scale(self) -> float:
        return self._pop_scale

    @property
    def opacity(self) -> float:
        return self._opacity

    @property
    def sprite_center(self) -> QPointF:
        return QPointF(
            self.x + PADDING_X + self.sprite_width / 2.0,
            self.y + PADDING_Y + self.sprite_height / 2.0,
        )

    def set_anchor_center(self, center: QPointF) -> None:
        """Update the target main-Jules center this clone orbits or returns to."""
        self._anchor_center = QPointF(center)

    def set_click_through(self, enabled: bool) -> None:
        """Enable or disable mouse input pass-through on this clone window."""
        flag = bool(enabled)
        was_visible = self.isVisible()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, flag)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, flag)
        if was_visible:
            self.show()

    def begin_return(self, target_center: QPointF | None = None) -> None:
        """Transition this clone to fly back to main Jules for a high-five."""
        if target_center is not None:
            self._anchor_center = QPointF(target_center)
        if self.phase in ("returning", "high_five", "fading", "done"):
            return
        self.phase = "returning"
        self._return_timer = 0.0
        self._pop_scale = 1.0

    def complete_immediately(self) -> None:
        """Immediately trigger visual high-five burst and emit finished cleanup."""
        if self._finished_emitted:
            return
        self._spawn_high_five_particles()
        self.phase = "done"
        self._opacity = 0.0
        self._emit_finished()

    def _emit_finished(self) -> None:
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self._timer.stop()
        self.hide()
        self.finished.emit(self.subagent_id)

    def _spawn_high_five_particles(self) -> None:
        cx = self.window_width / 2.0
        cy = PADDING_Y + self.sprite_height * 0.25
        for i in range(5):
            angle = -math.pi * (0.15 + 0.175 * i)
            speed = random.uniform(28.0, 58.0)
            is_heart = i % 2 == 1
            self.particles.append(
                Particle(
                    x=cx + random.uniform(-6.0, 6.0),
                    y=cy,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed - 12.0,
                    kind="heart" if is_heart else "sparkle",
                    color=HEART_PINK if is_heart else SPARKLE_CYAN,
                    life=0.5,
                    max_life=0.5,
                    size=max(2, self.scale),
                )
            )

    def _on_tick(self) -> None:
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        self.step(dt)

    def step(
        self,
        dt: float,
        anchor_center: QPointF | None = None,
        screen_rect: QRect | None = None,
    ) -> None:
        """Advance clone animation, orbital movement, return flight, and fade-out."""
        if self.phase == "done":
            return

        dt = max(0.001, min(float(dt), 0.05))
        if anchor_center is not None:
            self._anchor_center = QPointF(anchor_center)
        if screen_rect is not None:
            self._screen_rect = screen_rect

        self._anim_time += dt
        self._bob_phase += dt * 4.2

        if self.phase == "spawning":
            self._spawn_timer += dt
            progress = min(1.0, self._spawn_timer / _SPAWN_DURATION)
            # Elastic overshoot from 0.35 -> ~1.16 -> 1.0
            self._pop_scale = 1.0 - 0.65 * math.exp(-7.5 * progress) * math.cos(progress * math.pi * 2.2)
            self._orbit_angle += self._orbit_speed * dt * 0.6
            self._steer_to_orbit(dt, responsiveness=7.0)
            if progress >= 1.0:
                self._pop_scale = 1.0
                self.phase = "roaming"
        elif self.phase == "roaming":
            self._orbit_angle += self._orbit_speed * dt
            self._steer_to_orbit(dt, responsiveness=5.5)
        elif self.phase == "returning":
            self._return_timer += dt
            target_x = self._anchor_center.x() + (26.0 if self.sprite_center.x() >= self._anchor_center.x() else -26.0)
            target_y = self._anchor_center.y() - 6.0
            dx = target_x - self.sprite_center.x()
            dy = target_y - self.sprite_center.y()
            dist = math.hypot(dx, dy)
            if dist <= 18.0 or self._return_timer >= _RETURN_MAX_DURATION:
                self.phase = "high_five"
                self._high_five_timer = _HIGH_FIVE_DURATION
                self._spawn_high_five_particles()
            else:
                speed = max(240.0, dist * 7.0)
                self.vx = (dx / dist) * speed
                self.vy = (dy / dist) * speed
                self.x += self.vx * dt
                self.y += self.vy * dt
                if abs(self.vx) > 5.0:
                    self.facing_left = self.vx < 0.0
                self._clamp_position()
        elif self.phase == "high_five":
            self._high_five_timer -= dt
            if self._high_five_timer <= 0.0:
                self.phase = "fading"
        elif self.phase == "fading":
            self._opacity = max(0.0, self._opacity - dt / _FADE_DURATION)
            if self._opacity <= 0.0:
                self.phase = "done"
                self._emit_finished()
                return

        self._update_particles(dt)
        self.move(int(round(self.x)), int(round(self.y)))
        self.update()

    def _steer_to_orbit(self, dt: float, *, responsiveness: float) -> None:
        target_cx = self._anchor_center.x() + math.cos(self._orbit_angle) * self._orbit_radius
        target_cy = self._anchor_center.y() + math.sin(self._orbit_angle) * (self._orbit_radius * 0.65)
        center = self.sprite_center
        dx = target_cx - center.x()
        dy = target_cy - center.y()
        self.vx = dx * responsiveness
        self.vy = dy * responsiveness
        self.x += self.vx * dt
        self.y += self.vy * dt
        if abs(self.vx) > 6.0:
            self.facing_left = self.vx < 0.0
        self._clamp_position()

    def _clamp_position(self) -> None:
        min_x = float(self._screen_rect.left() - PADDING_X)
        max_x = float(max(int(min_x), self._screen_rect.right() - self.window_width + PADDING_X))
        min_y = float(self._screen_rect.top() - PADDING_Y)
        max_y = float(max(int(min_y), self._screen_rect.bottom() - self.window_height + PADDING_Y))
        self.x = max(min_x, min(max_x, self.x))
        self.y = max(min_y, min(max_y, self.y))

    def _update_particles(self, dt: float) -> None:
        alive: list[Particle] = []
        for p in self.particles:
            p.life -= dt
            if p.life > 0.0:
                p.x += p.vx * dt
                p.y += p.vy * dt
                if p.kind == "sparkle":
                    p.vy += 45.0 * dt
                alive.append(p)
        self.particles = alive

    def _current_frame_and_eyes(self) -> tuple[str, str]:
        if self.phase in ("high_five", "fading"):
            idx = int(self._anim_time * 8.0) % 2
            return f"high_five_{idx}", "high_five"
        if self.phase == "returning":
            idx = int(self._anim_time * 8.0) % 2
            return f"walk_{idx}", "happy"
        idx = int(self._anim_time * 5.0) % 2
        return f"coding_{idx}", "coding"

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.setOpacity(self._opacity)

        frame_name, eye_mode = self._current_frame_and_eyes()
        pixmap = get_sprite_pixmap(
            frame_name=frame_name,
            eye_mode=eye_mode,
            scale=self.scale,
            flip_x=self.facing_left,
            hue_shift=self.hue_shift,
        )

        bob_y = int(round(math.sin(self._bob_phase) * 2.0)) if self.phase != "fading" else 0
        if abs(self._pop_scale - 1.0) > 0.01:
            draw_w = max(4, int(round(pixmap.width() * self._pop_scale)))
            draw_h = max(4, int(round(pixmap.height() * self._pop_scale)))
            draw_x = PADDING_X + (self.sprite_width - draw_w) // 2
            draw_y = PADDING_Y + bob_y + (self.sprite_height - draw_h) // 2
            painter.drawPixmap(QRect(draw_x, draw_y, draw_w, draw_h), pixmap)
        else:
            painter.drawPixmap(PADDING_X, PADDING_Y + bob_y, pixmap)

        for particle in self.particles:
            alpha = max(0.0, min(1.0, particle.life / particle.max_life))
            color = QColor(particle.color)
            color.setAlphaF(alpha)
            px = int(round(particle.x))
            py = int(round(particle.y))
            s = max(2, particle.size // 2)
            if particle.kind == "sparkle":
                painter.fillRect(px - s, py, s * 3, s, color)
                painter.fillRect(px, py - s, s, s * 3, color)
            elif particle.kind == "heart":
                painter.fillRect(px - 2 * s, py - s, s, s, color)
                painter.fillRect(px, py - s, s, s, color)
                painter.fillRect(px - 2 * s, py, s * 3, s, color)
                painter.fillRect(px - s, py + s, s, s, color)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().closeEvent(event)
