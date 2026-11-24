"""Transparent frameless Windows desktop pet window and system tray integration."""

from __future__ import annotations

import os
import time
from pathlib import Path
from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QCursor,
    QGuiApplication,
    QMouseEvent,
    QMoveEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from jules_pet.accessories_manager import AccessoriesManager
from jules_pet.config import (
    DEFAULT_SCALE_NAME,
    FRAME_MS,
    GRID_HEIGHT,
    GRID_WIDTH,
    PADDING_X,
    PADDING_Y,
    PIXEL_SCALES,
)
from jules_pet.physics import Particle, PetController, PetState
from jules_pet.settings import PetSettings, load_settings, save_settings
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

    approval_bridge_toggled = Signal(bool)
    auto_hide_bubble_toggled = Signal(bool)
    click_through_toggled = Signal(bool)
    accessory_selected = Signal(str, str)
    perch_toggled = Signal(bool)
    sounds_toggled = Signal(bool)
    coffee_requested = Signal()
    stats_requested = Signal()
    user_interacted = Signal(str)
    moved = Signal()

    def __init__(
        self,
        *,
        settings_path: Path | None = None,
        persist_settings: bool | None = None,
        accessories_manager: AccessoriesManager | None = None,
    ) -> None:
        super().__init__()
        self._settings_path = settings_path
        if persist_settings is None:
            self._persist_settings = not (
                "PYTEST_CURRENT_TEST" in os.environ and settings_path is None
            )
        else:
            self._persist_settings = bool(persist_settings)

        self._settings: PetSettings = (
            load_settings(self._settings_path) if self._persist_settings else PetSettings()
        )
        self._accessories_manager = accessories_manager or AccessoriesManager()
        self._active_accessory_pixmap: QPixmap | None = None
        self._active_accessory_ox: int = 0
        self._active_accessory_oy: int = 0
        self._always_on_top = self._settings.always_on_top
        self._click_through = self._settings.click_through
        self._apply_window_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if self._click_through:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setMouseTracking(True)

        scale = PIXEL_SCALES.get(self._settings.scale_name, PIXEL_SCALES[DEFAULT_SCALE_NAME])
        self.controller = PetController(
            scale=scale,
            follow_mouse=self._settings.follow_mouse,
            floor_mode=self._settings.floor_mode,
        )
        self.controller.center_on(self._screen_rect())
        if self._settings.floor_mode:
            self.controller.set_floor_mode(True, self._screen_rect())

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
        if self._click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
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
        self._act_float.setChecked(not self._settings.floor_mode)
        self._act_floor.setChecked(self._settings.floor_mode)
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
        self._scale_actions: dict[str, QAction] = {}
        for label, px_scale in PIXEL_SCALES.items():
            act = QAction(label, self, checkable=True)
            if label == self._settings.scale_name:
                act.setChecked(True)
            act.triggered.connect(
                lambda _checked=False, s=px_scale, name=label: self._on_change_scale(s, name)
            )
            size_group.addAction(act)
            size_menu.addAction(act)
            self._scale_actions[label] = act

        self._act_top = QAction("Sempre no topo", self, checkable=True)
        self._act_top.setChecked(self._always_on_top)
        self._act_top.toggled.connect(self._on_toggle_top)
        self._menu.addAction(self._act_top)

        # Accessories submenu
        self._accessories_menu = self._menu.addMenu("Acessórios")
        self._accessories_menu.setStyleSheet(MENU_STYLESHEET)
        self._accessories_group = QActionGroup(self)
        self._accessories_group.setExclusive(True)
        self._custom_accessory_actions: dict[str, QAction] = {}
        self._populate_accessories_menu()
        self._accessories_menu.aboutToShow.connect(self._populate_accessories_menu)

        self._act_perch = QAction("Empoleirar na janela de código", self, checkable=True)
        self._act_perch.setChecked(self._settings.perch_enabled)
        self._act_perch.toggled.connect(self.perch_toggled.emit)
        self._menu.addAction(self._act_perch)

        self._act_sounds = QAction("Sons 8-bit", self, checkable=True)
        self._act_sounds.setChecked(self._settings.sounds_enabled)
        self._act_sounds.toggled.connect(self.sounds_toggled.emit)
        self._menu.addAction(self._act_sounds)

        self._menu.addSeparator()

        self._act_coffee = QAction("Oferecer Café", self)
        self._act_coffee.triggered.connect(self.coffee_requested.emit)
        self._menu.addAction(self._act_coffee)

        self._act_stats = QAction("Estatísticas da Sessão", self)
        self._act_stats.triggered.connect(self.stats_requested.emit)
        self._menu.addAction(self._act_stats)

        self._menu.addSeparator()

        self._act_approval_bridge = QAction("Aprovação pelo Pet", self, checkable=True)
        self._act_approval_bridge.setChecked(self._settings.approval_bridge_enabled)
        self._act_approval_bridge.toggled.connect(self.approval_bridge_toggled.emit)
        self._menu.addAction(self._act_approval_bridge)

        self._act_auto_hide_bubble = QAction("Auto-ocultar balão", self, checkable=True)
        self._act_auto_hide_bubble.setChecked(self._settings.auto_hide_bubble)
        self._act_auto_hide_bubble.toggled.connect(self.auto_hide_bubble_toggled.emit)
        self._menu.addAction(self._act_auto_hide_bubble)

        self._act_click_through = QAction("Modo Click-Through (Ctrl+Shift+J)", self, checkable=True)
        self._act_click_through.setChecked(self._click_through)
        self._act_click_through.toggled.connect(self.click_through_toggled.emit)
        self._menu.addAction(self._act_click_through)

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

    @property
    def settings(self) -> PetSettings:
        """Return the current PetSettings instance."""
        return self._settings

    def save_preference(self, key: str, value: object) -> None:
        """Update a preference field and persist settings to disk if enabled."""
        if hasattr(self._settings, key):
            setattr(self._settings, key, value)
            if self._persist_settings:
                save_settings(self._settings, self._settings_path)

    def _on_toggle_follow(self, checked: bool) -> None:
        self.controller.follow_mouse = checked
        self.save_preference("follow_mouse", bool(checked))

    def _on_floor_mode(self, enabled: bool) -> None:
        self.controller.set_floor_mode(enabled, self._screen_rect())
        self.save_preference("floor_mode", bool(enabled))

    def _on_change_scale(self, new_scale: int, scale_name: str | None = None) -> None:
        self.controller.set_scale(new_scale, self._screen_rect())
        self.resize(self.controller.window_width, self.controller.window_height)
        self.move(int(self.controller.x), int(self.controller.y))
        self.update()
        if scale_name is None:
            for name, px_scale in PIXEL_SCALES.items():
                if px_scale == new_scale:
                    scale_name = name
                    break
        if scale_name is not None:
            self.save_preference("scale_name", scale_name)

    def _on_toggle_top(self, checked: bool) -> None:
        self._always_on_top = checked
        self._apply_window_flags()
        self.show()
        self.save_preference("always_on_top", bool(checked))

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

        if self._active_accessory_pixmap is not None and not self._active_accessory_pixmap.isNull():
            painter.drawPixmap(
                PADDING_X + self._active_accessory_ox,
                PADDING_Y + bob_y + self._active_accessory_oy,
                self._active_accessory_pixmap,
            )

        if self.controller.state == PetState.EXHAUSTED:
            self._draw_micro_laptop(painter, bob_y)

        for particle in self.controller.particles:
            self._draw_particle(painter, particle)

    def _draw_micro_laptop(self, painter: QPainter, bob_y: int) -> None:
        s = max(2, self.controller.scale)
        lx = PADDING_X + ((GRID_WIDTH - 10) // 2) * s
        ly = PADDING_Y + bob_y + (GRID_HEIGHT - 6) * s
        # Lid / bezel
        painter.fillRect(lx + s, ly, 8 * s, 4 * s, QColor("#140B29"))
        # Glowing cyan/indigo screen
        painter.fillRect(lx + 2 * s, ly + s, 6 * s, 2 * s, QColor("#38BDF8"))
        # Tiny code line highlights on screen
        painter.fillRect(lx + 3 * s, ly + s, 3 * s, max(1, s // 2), QColor("#E0F2FE"))
        # Keyboard base
        painter.fillRect(lx, ly + 4 * s, 10 * s, 2 * s, QColor("#475569"))
        painter.fillRect(lx + s, ly + 4 * s, 8 * s, s, QColor("#94A3B8"))

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
        elif p.kind == "sweat":
            # Crisp pixel teardrop
            painter.fillRect(px, py - s, s, s, color)
            painter.fillRect(px - s // 2, py, s * 2, s * 2, color)
        elif p.kind == "ink":
            # Crisp pixel ink splat with satellite droplets
            painter.fillRect(px - s, py - s, s * 2, s * 2, color)
            painter.fillRect(px - 2 * s, py, s, s, color)
            painter.fillRect(px + s, py - 2 * s, s, s, color)
            painter.fillRect(px + s, py + s, s, s, color)
        elif p.kind == "steam":
            # Rising pixel-art steam curl
            painter.fillRect(px, py - s * 2, s, s, color)
            painter.fillRect(px + s, py - s, s, s, color)
            painter.fillRect(px, py, s, s, color)
            painter.fillRect(px - s, py + s, s, s, color)

    def pet_rect(self) -> QRect:
        """Return the pet window bounds in screen coordinates."""
        return QRect(self.x(), self.y(), self.width(), self.height())

    def screen_rect(self) -> QRect:
        """Return the available screen geometry containing Jules."""
        return self._screen_rect()

    def set_click_through(self, enabled: bool) -> None:
        """Enable or disable input pass-through on the main pet window."""
        self._click_through = bool(enabled)
        was_visible = self.isVisible()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, self._click_through)
        self._apply_window_flags()
        if was_visible:
            self.show()

    def set_click_through_checked(self, enabled: bool) -> None:
        """Sync the menu check state for click-through without re-emitting toggled."""
        self._act_click_through.blockSignals(True)
        self._act_click_through.setChecked(bool(enabled))
        self._act_click_through.blockSignals(False)

    def set_approval_bridge_checked(self, enabled: bool) -> None:
        """Sync the menu check state for approval bridge without re-emitting toggled."""
        self._act_approval_bridge.blockSignals(True)
        self._act_approval_bridge.setChecked(bool(enabled))
        self._act_approval_bridge.blockSignals(False)

    def set_auto_hide_bubble_checked(self, enabled: bool) -> None:
        """Sync the menu check state for auto-hide bubble without re-emitting toggled."""
        self._act_auto_hide_bubble.blockSignals(True)
        self._act_auto_hide_bubble.setChecked(bool(enabled))
        self._act_auto_hide_bubble.blockSignals(False)

    def _populate_accessories_menu(self) -> None:
        """Rebuild the dynamic 'Acessórios' submenu from AccessoriesManager."""
        for action in list(self._accessories_group.actions()):
            self._accessories_group.removeAction(action)
        self._accessories_menu.clear()
        self._custom_accessory_actions.clear()

        self._act_acc_auto = QAction("Automático por Ferramenta", self, checkable=True)
        self._act_acc_auto.triggered.connect(lambda: self.accessory_selected.emit("auto", ""))
        self._accessories_group.addAction(self._act_acc_auto)
        self._accessories_menu.addAction(self._act_acc_auto)

        self._act_acc_none = QAction("Nenhum", self, checkable=True)
        self._act_acc_none.triggered.connect(lambda: self.accessory_selected.emit("none", ""))
        self._accessories_group.addAction(self._act_acc_none)
        self._accessories_menu.addAction(self._act_acc_none)

        custom_specs = self._accessories_manager.list_custom()
        if custom_specs:
            self._accessories_menu.addSeparator()
            for spec in custom_specs:
                act = QAction(spec.name, self, checkable=True)
                act.triggered.connect(
                    lambda _checked=False, cid=spec.id: self.accessory_selected.emit("custom", cid)
                )
                self._accessories_group.addAction(act)
                self._accessories_menu.addAction(act)
                self._custom_accessory_actions[spec.id] = act

        self.set_accessory_selection(
            self._settings.accessory_mode,
            self._settings.custom_accessory_id,
        )

    def set_accessories_manager(self, manager: AccessoriesManager) -> None:
        """Attach an AccessoriesManager instance and refresh the accessories submenu."""
        self._accessories_manager = manager
        self._populate_accessories_menu()

    def set_accessory_selection(self, mode: str, custom_id: str = "") -> None:
        """Sync the menu check state for the active accessory without re-emitting signals."""
        normalized_mode = (mode or "auto").strip().lower()
        target: QAction | None = None
        if normalized_mode in {"none", "off", ""}:
            target = self._act_acc_none
        elif normalized_mode == "custom":
            target = self._custom_accessory_actions.get((custom_id or "").strip())
        elif normalized_mode == "auto":
            target = self._act_acc_auto

        for act in self._accessories_group.actions():
            act.blockSignals(True)
            act.setChecked(act is target)
            act.blockSignals(False)

    def set_perch_checked(self, enabled: bool) -> None:
        """Sync the menu check state for perching without re-emitting toggled."""
        self._act_perch.blockSignals(True)
        self._act_perch.setChecked(bool(enabled))
        self._act_perch.blockSignals(False)

    def set_sounds_checked(self, enabled: bool) -> None:
        """Sync the menu check state for 8-bit sounds without re-emitting toggled."""
        self._act_sounds.blockSignals(True)
        self._act_sounds.setChecked(bool(enabled))
        self._act_sounds.blockSignals(False)

    def set_active_accessory(
        self,
        pixmap: QPixmap | None,
        ox: int = 0,
        oy: int = 0,
    ) -> None:
        """Set or clear the pixel-art accessory overlay rendered atop Jules."""
        if pixmap is None or pixmap.isNull():
            self._active_accessory_pixmap = None
            self._active_accessory_ox = 0
            self._active_accessory_oy = 0
        else:
            self._active_accessory_pixmap = pixmap
            self._active_accessory_ox = int(ox)
            self._active_accessory_oy = int(oy)
        self.update()

    def moveEvent(self, event: QMoveEvent) -> None:  # noqa: N802
        super().moveEvent(event)
        self.moved.emit()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.moved.emit()

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
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.coffee_requested.emit()
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
                self.user_interacted.emit("pet")
        self._last_hover_x = lx

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._pressing_left:
            self._pressing_left = False
            if self._dragging:
                self._dragging = False
                self.controller.end_drag(self._throw_vx, self._throw_vy)
            else:
                self.controller.trigger_click_reaction()
                self.user_interacted.emit("click")
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.trigger_double_click_reaction()
            self.user_interacted.emit("double_click")
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.stats_requested.emit()
            event.accept()
