"""State machine, movement, mouse following, and particle physics for Jules."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto

from PySide6.QtCore import QPointF, QRect

from jules_pet.config import (
    FOLLOW_SPEED,
    FOLLOW_STOP_RADIUS,
    GRID_HEIGHT,
    GRID_WIDTH,
    HEART_PINK,
    PADDING_X,
    PADDING_Y,
    ROAM_SPEED,
    SPARKLE_CYAN,
    SPARKLE_YELLOW,
    WALK_FLOOR_SPEED,
    ZZZ_LAVENDER,
)


class PetState(Enum):
    """High-level behavior states of the Jules pet."""

    IDLE = auto()
    ROAM = auto()
    WALK_FLOOR = auto()
    FOLLOW_MOUSE = auto()
    DRAGGED = auto()
    HAPPY = auto()
    SLEEP = auto()


@dataclass
class Particle:
    """Pixel-art particle emitted on clicks, pets, or sleep."""

    x: float
    y: float
    vx: float
    vy: float
    kind: str  # "sparkle" | "heart" | "zzz"
    color: str
    life: float
    max_life: float
    size: int = 4


@dataclass
class PetController:
    """Pure state & physics controller for the Jules desktop pet."""

    scale: int = 4
    x: float = 300.0
    y: float = 300.0
    vx: float = 0.0
    vy: float = 0.0
    state: PetState = PetState.IDLE
    facing_left: bool = False
    follow_mouse: bool = False
    floor_mode: bool = False

    state_timer: float = 2.0
    anim_time: float = 0.0
    bob_phase: float = 0.0
    blink_timer: float = 3.2
    blink_duration: float = 0.0
    happy_timer: float = 0.0
    sleep_zzz_timer: float = 0.0
    pet_cooldown: float = 0.0

    eye_dx: int = 0
    eye_dy: int = 0

    _roam_target_x: float | None = None
    _roam_target_y: float | None = None
    particles: list[Particle] = field(default_factory=list)

    @property
    def sprite_width(self) -> int:
        return GRID_WIDTH * self.scale

    @property
    def sprite_height(self) -> int:
        return GRID_HEIGHT * self.scale

    @property
    def window_width(self) -> int:
        return self.sprite_width + PADDING_X * 2

    @property
    def window_height(self) -> int:
        return self.sprite_height + PADDING_Y * 2

    @property
    def sprite_center(self) -> QPointF:
        return QPointF(
            self.x + PADDING_X + self.sprite_width / 2.0,
            self.y + PADDING_Y + self.sprite_height / 2.0,
        )

    def set_scale(self, new_scale: int, screen_rect: QRect) -> None:
        """Update pixel scale while keeping the sprite center stable."""
        center = self.sprite_center
        self.scale = new_scale
        self.x = center.x() - PADDING_X - self.sprite_width / 2.0
        self.y = center.y() - PADDING_Y - self.sprite_height / 2.0
        self._clamp_to_screen(screen_rect)

    def center_on(self, screen_rect: QRect) -> None:
        """Center Jules in the given screen rectangle."""
        self.x = screen_rect.center().x() - self.window_width / 2.0
        self.y = screen_rect.center().y() - self.window_height / 2.0
        self.vx = 0.0
        self.vy = 0.0
        self._clamp_to_screen(screen_rect)

    def toggle_sleep(self) -> None:
        """Toggle between sleeping and idle states."""
        if self.state == PetState.SLEEP:
            self.state = PetState.IDLE
            self.state_timer = 2.0
            self.trigger_click_reaction()
        else:
            self.state = PetState.SLEEP
            self.vx = 0.0
            self.vy = 0.0
            self.sleep_zzz_timer = 0.4

    def set_floor_mode(self, enabled: bool, screen_rect: QRect) -> None:
        """Switch between free-floating mode and taskbar floor-walking mode."""
        self.floor_mode = enabled
        if self.state in (PetState.ROAM, PetState.WALK_FLOOR, PetState.IDLE):
            self.state = PetState.WALK_FLOOR if enabled else PetState.IDLE
            self.state_timer = 2.0
            if enabled:
                self.y = float(self._max_y(screen_rect))

    def start_drag(self) -> None:
        """Enter dragged state."""
        self.state = PetState.DRAGGED
        self.vx = 0.0
        self.vy = 0.0
        self._roam_target_x = None
        self._roam_target_y = None

    def update_drag(self, dx: float, dy: float, screen_rect: QRect) -> None:
        """Move pet during active mouse drag."""
        self.x += dx
        self.y += dy
        self._clamp_to_screen(screen_rect)

    def end_drag(self, throw_vx: float, throw_vy: float) -> None:
        """Release pet from drag with capped momentum."""
        max_throw = 16.0
        self.vx = max(-max_throw, min(max_throw, throw_vx))
        self.vy = max(-max_throw, min(max_throw, throw_vy))
        self.state = PetState.WALK_FLOOR if self.floor_mode else PetState.IDLE
        self.state_timer = 1.6

    def trigger_click_reaction(self) -> None:
        """Happy hop + blush + pixel sparkles on left click."""
        if self.state == PetState.SLEEP:
            self.state = PetState.IDLE
        self.happy_timer = 0.9
        self.vy = min(self.vy, -3.5)
        cx = self.window_width / 2.0
        cy = PADDING_Y + self.sprite_height * 0.25
        for i in range(4):
            angle = -math.pi * (0.2 + 0.2 * i) + random.uniform(-0.2, 0.2)
            speed = random.uniform(25.0, 55.0)
            color = SPARKLE_CYAN if i % 2 == 0 else SPARKLE_YELLOW
            self.particles.append(
                Particle(
                    x=cx + random.uniform(-12, 12),
                    y=cy,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed - 15.0,
                    kind="sparkle",
                    color=color,
                    life=0.65,
                    max_life=0.65,
                    size=max(3, self.scale),
                )
            )

    def trigger_double_click_reaction(self) -> None:
        """Excited jump + heart and star burst on double click."""
        if self.state == PetState.SLEEP:
            self.state = PetState.IDLE
        self.happy_timer = 1.3
        self.vy = -5.5
        cx = self.window_width / 2.0
        cy = PADDING_Y + self.sprite_height * 0.2
        colors = (HEART_PINK, SPARKLE_YELLOW, SPARKLE_CYAN, HEART_PINK, SPARKLE_YELLOW)
        for i, color in enumerate(colors):
            angle = -math.pi * (0.1 + 0.2 * i)
            speed = random.uniform(35.0, 70.0)
            kind = "heart" if color == HEART_PINK else "sparkle"
            self.particles.append(
                Particle(
                    x=cx + random.uniform(-8, 8),
                    y=cy,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed - 20.0,
                    kind=kind,
                    color=color,
                    life=0.85,
                    max_life=0.85,
                    size=max(3, self.scale),
                )
            )

    def trigger_pet_reaction(self) -> None:
        """Gentle floating heart when the user pets Jules by rubbing the cursor."""
        if self.pet_cooldown > 0.0 or self.state == PetState.DRAGGED:
            return
        self.pet_cooldown = 0.75
        self.happy_timer = max(self.happy_timer, 0.65)
        self.particles.append(
            Particle(
                x=self.window_width / 2.0 + random.uniform(-10, 10),
                y=PADDING_Y + 6.0,
                vx=random.uniform(-12.0, 12.0),
                vy=-32.0,
                kind="heart",
                color=HEART_PINK,
                life=0.9,
                max_life=0.9,
                size=max(3, self.scale),
            )
        )

    def update(self, dt: float, screen_rect: QRect, cursor_pos: QPointF) -> None:
        """Advance animation, movement, eye tracking, and particles by dt seconds."""
        dt = max(0.001, min(dt, 0.05))
        self.anim_time += dt
        self.bob_phase += dt * 3.2
        if self.pet_cooldown > 0.0:
            self.pet_cooldown = max(0.0, self.pet_cooldown - dt)
        if self.happy_timer > 0.0:
            self.happy_timer = max(0.0, self.happy_timer - dt)

        # Natural blinking
        if self.blink_duration > 0.0:
            self.blink_duration = max(0.0, self.blink_duration - dt)
        else:
            self.blink_timer -= dt
            if self.blink_timer <= 0.0:
                self.blink_duration = 0.14
                self.blink_timer = random.uniform(2.6, 5.2)

        # Eye tracking toward cursor
        center = self.sprite_center
        dx_cursor = cursor_pos.x() - center.x()
        dy_cursor = cursor_pos.y() - center.y()
        dist_cursor = math.hypot(dx_cursor, dy_cursor)
        if dist_cursor > 24.0:
            self.eye_dx = 1 if dx_cursor > 36 else (-1 if dx_cursor < -36 else 0)
            self.eye_dy = 1 if dy_cursor > 48 else (-1 if dy_cursor < -48 else 0)
        else:
            self.eye_dx = 0
            self.eye_dy = 0

        # State machine & movement
        if self.state == PetState.DRAGGED:
            pass
        elif self.state == PetState.SLEEP:
            self.sleep_zzz_timer -= dt
            if self.sleep_zzz_timer <= 0.0:
                self.sleep_zzz_timer = 1.15
                self.particles.append(
                    Particle(
                        x=self.window_width * 0.65,
                        y=PADDING_Y + 8.0,
                        vx=10.0,
                        vy=-22.0,
                        kind="zzz",
                        color=ZZZ_LAVENDER,
                        life=1.2,
                        max_life=1.2,
                        size=max(3, self.scale),
                    )
                )
        elif self.follow_mouse:
            self.state = PetState.FOLLOW_MOUSE
            self._steer_toward(cursor_pos.x(), cursor_pos.y(), FOLLOW_SPEED, FOLLOW_STOP_RADIUS)
            self._apply_velocity(dt, screen_rect, damping=0.88)
        else:
            self._update_autonomous(dt, screen_rect)

        self._update_particles(dt)

    def _update_autonomous(self, dt: float, screen_rect: QRect) -> None:
        self.state_timer -= dt
        if self.floor_mode:
            # Gentle gravity toward the bottom of the screen (taskbar edge)
            floor_y = float(self._max_y(screen_rect))
            if self.y < floor_y - 1.0:
                self.vy += 18.0 * dt
            if self.state not in (PetState.IDLE, PetState.WALK_FLOOR):
                self.state = PetState.WALK_FLOOR
                self.state_timer = random.uniform(2.5, 5.0)

            if self.state_timer <= 0.0:
                if self.state == PetState.IDLE:
                    self.state = PetState.WALK_FLOOR
                    self.state_timer = random.uniform(2.5, 5.5)
                    self._roam_target_x = float(
                        random.randint(self._min_x(screen_rect), self._max_x(screen_rect))
                    )
                else:
                    self.state = PetState.IDLE
                    self.state_timer = random.uniform(1.8, 4.0)
                    self._roam_target_x = None

            if self.state == PetState.WALK_FLOOR and self._roam_target_x is not None:
                diff_x = self._roam_target_x - self.x
                if abs(diff_x) < 10.0:
                    self.vx *= 0.8
                    self.state = PetState.IDLE
                    self.state_timer = random.uniform(1.5, 3.5)
                else:
                    dir_x = 1.0 if diff_x > 0 else -1.0
                    self.vx = dir_x * WALK_FLOOR_SPEED
                    self.facing_left = dir_x < 0
            else:
                self.vx *= 0.85

            self._apply_velocity(dt, screen_rect, damping=0.94)
            if self.y > floor_y:
                self.y = floor_y
                self.vy = 0.0
        else:
            if self.state == PetState.FOLLOW_MOUSE:
                self.state = PetState.IDLE
                self.state_timer = 1.5

            if self.state_timer <= 0.0:
                if self.state == PetState.IDLE:
                    self.state = PetState.ROAM
                    self.state_timer = random.uniform(2.5, 5.0)
                    self._roam_target_x = float(
                        random.randint(self._min_x(screen_rect), self._max_x(screen_rect))
                    )
                    self._roam_target_y = float(
                        random.randint(self._min_y(screen_rect), self._max_y(screen_rect))
                    )
                else:
                    self.state = PetState.IDLE
                    self.state_timer = random.uniform(2.0, 4.5)
                    self._roam_target_x = None
                    self._roam_target_y = None

            if (
                self.state == PetState.ROAM
                and self._roam_target_x is not None
                and self._roam_target_y is not None
            ):
                target_cx = self._roam_target_x + self.window_width / 2.0
                target_cy = self._roam_target_y + self.window_height / 2.0
                arrived = self._steer_toward(target_cx, target_cy, ROAM_SPEED, 14.0)
                if arrived:
                    self.state = PetState.IDLE
                    self.state_timer = random.uniform(2.0, 4.0)
            self._apply_velocity(dt, screen_rect, damping=0.92)

    def _steer_toward(
        self, target_cx: float, target_cy: float, max_speed: float, stop_radius: float
    ) -> bool:
        center = self.sprite_center
        dx = target_cx - center.x()
        dy = target_cy - center.y()
        dist = math.hypot(dx, dy)
        if dist <= stop_radius:
            self.vx *= 0.82
            self.vy *= 0.82
            return True

        # Smooth deceleration near stop_radius
        factor = min(1.0, (dist - stop_radius) / 80.0)
        speed = max(0.6, max_speed * factor)
        desired_vx = (dx / dist) * speed
        desired_vy = (dy / dist) * speed
        self.vx += (desired_vx - self.vx) * 0.16
        self.vy += (desired_vy - self.vy) * 0.16
        if abs(self.vx) > 0.25:
            self.facing_left = self.vx < 0
        return False

    def _apply_velocity(self, dt: float, screen_rect: QRect, damping: float) -> None:
        step = dt * 60.0
        self.x += self.vx * step
        self.y += self.vy * step

        # Gentle decay when idle
        if self.state == PetState.IDLE:
            self.vx *= damping
            self.vy *= damping

        min_x = self._min_x(screen_rect)
        max_x = self._max_x(screen_rect)
        min_y = self._min_y(screen_rect)
        max_y = self._max_y(screen_rect)

        if self.x < min_x:
            self.x = float(min_x)
            self.vx = abs(self.vx) * 0.55
        elif self.x > max_x:
            self.x = float(max_x)
            self.vx = -abs(self.vx) * 0.55

        if self.y < min_y:
            self.y = float(min_y)
            self.vy = abs(self.vy) * 0.55
        elif self.y > max_y:
            self.y = float(max_y)
            self.vy = -abs(self.vy) * 0.55

    def _min_x(self, screen_rect: QRect) -> int:
        return screen_rect.left() - PADDING_X

    def _max_x(self, screen_rect: QRect) -> int:
        return max(self._min_x(screen_rect), screen_rect.right() - self.window_width + PADDING_X)

    def _min_y(self, screen_rect: QRect) -> int:
        return screen_rect.top() - PADDING_Y

    def _max_y(self, screen_rect: QRect) -> int:
        return max(self._min_y(screen_rect), screen_rect.bottom() - self.window_height + PADDING_Y)

    def _clamp_to_screen(self, screen_rect: QRect) -> None:
        self.x = max(float(self._min_x(screen_rect)), min(float(self._max_x(screen_rect)), self.x))
        self.y = max(float(self._min_y(screen_rect)), min(float(self._max_y(screen_rect)), self.y))

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

    def current_frame_name(self) -> str:
        """Select the tentacle animation frame matching the current state."""
        if self.state == PetState.SLEEP:
            return "sleep_0"
        if self.state == PetState.DRAGGED:
            idx = int(self.anim_time * 6.0) % 2
            return f"drag_{idx}"
        if self.state == PetState.WALK_FLOOR and abs(self.vx) > 0.2:
            idx = int(self.anim_time * 6.0) % 2
            return f"walk_{idx}"
        idx = int(self.anim_time * 4.5) % 4
        return f"idle_{idx}"

    def current_eye_mode(self) -> str:
        """Select the eye expression matching the current state."""
        if self.state == PetState.SLEEP:
            return "sleep"
        if self.state == PetState.DRAGGED:
            return "surprised"
        if self.happy_timer > 0.0:
            return "happy"
        if self.blink_duration > 0.0:
            return "blink"
        return "normal"

    def bob_offset_y(self) -> int:
        """Subtle vertical floating offset in screen pixels."""
        if self.state in (PetState.DRAGGED, PetState.SLEEP):
            return 0
        if self.state == PetState.WALK_FLOOR:
            return -abs(int(round(math.sin(self.bob_phase * 2.0) * 2.0)))
        return int(round(math.sin(self.bob_phase) * 3.0))
