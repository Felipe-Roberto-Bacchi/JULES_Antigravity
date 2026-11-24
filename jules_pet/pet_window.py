"""Transparent frameless Windows desktop pet window and system tray integration."""

from __future__ import annotations

import time
from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QCursor,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from jules_pet.config import (
    DEFAULT_SCALE_NAME,
    FRAME_MS,
    PADDING_X,
    PADDING_Y,
    PIXEL_SCALES,
)
from jules_pet.physics import Particle, PetController, PetState
from jules_pet.sprites import create_tray_icon, get_sprite_pixmap

MENU_STYLESHEET = """
QMenu {
    background-color: #1A1033;
    color: #E6DCFF;
    border: 2px solid #705BD6;
    border-radius: 6px;
    padding: 4px;
    font-family: "Segoe UI", sans-serif;
    font-size: 9.5pt;
}
QMenu::item {
    padding: 6px 22px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #705BD6;
    color: #FFFFFF;
}
QMenu::separator {
    height: 1px;
    background: #3B2870;
    margin: 4px 8px;
}
"""


class JulesPetWindow(QWidget):
    """Frameless, always-on-top, transparent pixel-art Jules octopus pet."""

    def __init__(self) -> None:
        super().__init__()
        self._always_on_top = True
        self._apply_window_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        scale = PIXEL_SCALES[DEFAULT_SCALE_NAME]
        self.controller = PetController(scale=scale)
        self.controller.center_on(self._screen_rect())

        self.resize(self.controller.window_width, self.controller.window_height)
        self.move(int(self.controller.x), int(self.controller.y))

        # Drag & pet interaction tracking
        self._pressing_left = False
        self._dragging = False
        self._press_global = QPoint()
        self._last_global = QPoint()
        self._throw_vx = 0.0
        self._throw_vy = 0.0
        self._pet_rub_accum = 0.0
        self._last_hover_x: float | None = None

        self._last_tick = time.monotonic()

        self._build_menu()
        self._build_tray()

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

    def _screen_rect(self) -> QRect:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return QRect(0, 0, 1920, 1080)
        return screen.availableGeometry()

    def _build_menu(self) -> None:
        self._menu = QMenu(self)
        self._menu.setStyleSheet(MENU_STYLESHEET)

        self._act_follow = QAction("Seguir o mouse", self, checkable=True)
        self._act_follow.setChecked(self.controller.follow_mouse)
        self._act_follow.toggled.connect(self._on_toggle_follow)
        self._menu.addAction(self._act_follow)

        # Movement mode submenu
        move_menu = self._menu.addMenu("Modo de movimento")
        move_menu.setStyleSheet(MENU_STYLESHEET)
        move_group = QActionGroup(self)
        move_group.setExclusive(True)

        self._act_float = QAction("Flutuar livremente", self, checkable=True)
        self._act_floor = QAction("Andar na barra de tarefas", self, checkable=True)
        self._act_float.setChecked(True)
        move_group.addAction(self._act_float)
        move_group.addAction(self._act_floor)
        move_menu.addAction(self._act_float)
        move_menu.addAction(self._act_floor)
        self._act_float.triggered.connect(lambda: self._on_floor_mode(False))
        self._act_floor.triggered.connect(lambda: self._on_floor_mode(True))

        # Scale submenu
        size_menu = self._menu.addMenu("Tamanho")
        size_menu.setStyleSheet(MENU_STYLESHEET)
        size_group = QActionGroup(self)
        size_group.setExclusive(True)
        for label, px_scale in PIXEL_SCALES.items():
            act = QAction(label, self, checkable=True)
            if label == DEFAULT_SCALE_NAME:
                act.setChecked(True)
            act.triggered.connect(lambda _checked=False, s=px_scale: self._on_change_scale(s))
            size_group.addAction(act)
            size_menu.addAction(act)

        self._act_top = QAction("Sempre no topo", self, checkable=True)
        self._act_top.setChecked(self._always_on_top)
        self._act_top.toggled.connect(self._on_toggle_top)
        self._menu.addAction(self._act_top)

        self._menu.addSeparator()

        self._act_sleep = QAction("Dormir / Acordar", self)
        self._act_sleep.triggered.connect(self._on_toggle_sleep)
        self._menu.addAction(self._act_sleep)

        act_center = QAction("Centralizar na tela", self)
        act_center.triggered.connect(self._on_center)
        self._menu.addAction(act_center)

        self._menu.addSeparator()

        act_quit = QAction("Sair", self)
        act_quit.triggered.connect(self._on_quit)
        self._menu.addAction(act_quit)

    def _build_tray(self) -> None:
        self._tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            tray = QSystemTrayIcon(create_tray_icon(), self)
            tray.setToolTip("Jules Desktop Pet")
            tray.setContextMenu(self._menu)
            tray.activated.connect(self._on_tray_activated)
            tray.show()
            self._tray = tray

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show()
            self.raise_()
            self.controller.trigger_click_reaction()

    def _on_toggle_follow(self, checked: bool) -> None:
        self.controller.follow_mouse = checked

    def _on_floor_mode(self, enabled: bool) -> None:
        self.controller.set_floor_mode(enabled, self._screen_rect())

    def _on_change_scale(self, new_scale: int) -> None:
        self.controller.set_scale(new_scale, self._screen_rect())
        self.resize(self.controller.window_width, self.controller.window_height)
        self.move(int(self.controller.x), int(self.controller.y))
        self.update()

    def _on_toggle_top(self, checked: bool) -> None:
        self._always_on_top = checked
        self._apply_window_flags()
        self.show()

    def _on_toggle_sleep(self) -> None:
        self.controller.toggle_sleep()

    def _on_center(self) -> None:
        self.controller.center_on(self._screen_rect())
        self.move(int(self.controller.x), int(self.controller.y))
        self.show()
        self.raise_()

    def _on_quit(self) -> None:
        self._timer.stop()
        if self._tray is not None:
            self._tray.hide()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _on_tick(self) -> None:
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now

        cursor = QPointF(QCursor.pos())
        self.controller.update(dt, self._screen_rect(), cursor)
        self.move(int(round(self.controller.x)), int(round(self.controller.y)))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        pixmap = get_sprite_pixmap(
            frame_name=self.controller.current_frame_name(),
            eye_mode=self.controller.current_eye_mode(),
            eye_dx=self.controller.eye_dx,
            eye_dy=self.controller.eye_dy,
            scale=self.controller.scale,
            flip_x=self.controller.facing_left,
        )

        bob_y = self.controller.bob_offset_y()
        painter.drawPixmap(PADDING_X, PADDING_Y + bob_y, pixmap)

        for particle in self.controller.particles:
            self._draw_particle(painter, particle)

    def _draw_particle(self, painter: QPainter, p: Particle) -> None:
        alpha = max(0.0, min(1.0, p.life / p.max_life))
        color = QColor(p.color)
        color.setAlphaF(alpha)
        px = int(round(p.x))
        py = int(round(p.y))
        s = max(2, p.size // 2)

        if p.kind == "sparkle":
            # Crisp 4-point pixel star
            painter.fillRect(px - s, py, s * 3, s, color)
            painter.fillRect(px, py - s, s, s * 3, color)
        elif p.kind == "heart":
            # Tiny 5x4 pixel heart
            painter.fillRect(px - 2 * s, py - s, s, s, color)
            painter.fillRect(px + 0, py - s, s, s, color)
            painter.fillRect(px - 2 * s, py, s * 3, s, color)
            painter.fillRect(px - s, py + s, s, s, color)
        elif p.kind == "zzz":
            # Tiny pixel 'Z'
            painter.fillRect(px, py, s * 3, s, color)
            painter.fillRect(px + s, py + s, s, s, color)
            painter.fillRect(px, py + s * 2, s * 3, s, color)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressing_left = True
            self._dragging = False
            gpos = event.globalPosition().toPoint()
            self._press_global = gpos
            self._last_global = gpos
            self._throw_vx = 0.0
            self._throw_vy = 0.0
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._menu.popup(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        gpos = event.globalPosition().toPoint()
        if self._pressing_left:
            if not self._dragging:
                if (gpos - self._press_global).manhattanLength() >= QApplication.startDragDistance():
                    self._dragging = True
                    self.controller.start_drag()
            if self._dragging:
                dx = float(gpos.x() - self._last_global.x())
                dy = float(gpos.y() - self._last_global.y())
                self._throw_vx = self._throw_vx * 0.6 + dx * 0.4
                self._throw_vy = self._throw_vy * 0.6 + dy * 0.4
                self.controller.update_drag(dx, dy, self._screen_rect())
                self.move(int(round(self.controller.x)), int(round(self.controller.y)))
                self._last_global = gpos
            event.accept()
            return

        # Hover rubbing detection (petting Jules)
        lx = event.position().x()
        if self._last_hover_x is not None:
            self._pet_rub_accum += abs(lx - self._last_hover_x)
            if self._pet_rub_accum >= 70.0:
                self._pet_rub_accum = 0.0
                self.controller.trigger_pet_reaction()
        self._last_hover_x = lx

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._pressing_left:
            self._pressing_left = False
            if self._dragging:
                self._dragging = False
                self.controller.end_drag(self._throw_vx, self._throw_vy)
            else:
                self.controller.trigger_click_reaction()
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.trigger_double_click_reaction()
            event.accept()
