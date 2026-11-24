"""OctoSwarm coordinator wiring IPC, transcript watcher, buddy model, bubble, and clones."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget

from jules_pet.accessories_manager import AccessoriesManager, render_accessory_pixmap
from jules_pet.bubble_widget import BubbleWidget, DONE_HIDE_MS, IDLE_HIDE_MS
from jules_pet.buddy import BuddySessionModel
from jules_pet.coffee_window import CoffeeCupWindow
from jules_pet.ink_splat_window import InkSplatManager
from jules_pet.ipc_protocol import DEFAULT_IPC_HOST, DEFAULT_IPC_PORT
from jules_pet.ipc_server import JulesIpcServer
from jules_pet.perch_controller import PerchController
from jules_pet.pet_window import JulesPetWindow
from jules_pet.sound_effects import RetroSoundEngine, SoundEffect
from jules_pet.stats_window import SessionStats, StatsCardWindow
from jules_pet.subagent_window import JulesSubagentWindow
from jules_pet.transcript_watcher import TranscriptWatcher

MAX_VISIBLE_CLONES = 5

_MOOD_LABELS: dict[str, str] = {
    "idle": "De boas",
    "happy": "Feliz",
    "focused": "Focado",
    "tired": "Exausto",
    "sweating": "Suando frio",
    "shocked": "Em choque",
}

_CLONE_HUE_SHIFTS: tuple[float, ...] = (
    0.14,
    0.28,
    0.45,
    0.62,
    0.80,
    0.08,
    0.36,
    0.54,
    0.72,
    0.88,
)


def _apply_click_through(widget: QWidget, enabled: bool) -> None:
    was_visible = widget.isVisible()
    widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
    widget.setWindowFlag(Qt.WindowType.WindowTransparentForInput, enabled)
    if was_visible:
        widget.show()


class MascotSquadManager(QObject):
    """Coordinates main Jules, speech/approval bubble, IPC bridge, and subagent clones."""

    MAX_VISIBLE_CLONES = MAX_VISIBLE_CLONES

    def __init__(
        self,
        pet_window: JulesPetWindow | None = None,
        bubble_widget: BubbleWidget | None = None,
        ipc_server: JulesIpcServer | None = None,
        transcript_watcher: TranscriptWatcher | None = None,
        buddy: BuddySessionModel | None = None,
        *,
        ipc_host: str = DEFAULT_IPC_HOST,
        ipc_port: int = DEFAULT_IPC_PORT,
        auto_start: bool = False,
        accessories_manager: AccessoriesManager | None = None,
        perch_controller: PerchController | None = None,
        sound_engine: RetroSoundEngine | None = None,
        ink_splat_manager: InkSplatManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.pet_window = pet_window or JulesPetWindow()
        self.bubble_widget = bubble_widget or BubbleWidget(always_on_top=self.pet_window._always_on_top)
        self.ipc_server = ipc_server or JulesIpcServer(
            host=ipc_host,
            port=ipc_port,
            auto_start=False,
        )
        self.transcript_watcher = transcript_watcher or TranscriptWatcher(parent=self)
        self.buddy = buddy or BuddySessionModel(parent=self)

        self.approval_bridge_enabled: bool = self.pet_window.settings.approval_bridge_enabled
        self.click_through: bool = self.pet_window.settings.click_through
        self.accessory_mode: str = self.pet_window.settings.accessory_mode
        self.custom_accessory_id: str = self.pet_window.settings.custom_accessory_id
        self.perch_enabled: bool = self.pet_window.settings.perch_enabled
        self.sounds_enabled: bool = self.pet_window.settings.sounds_enabled
        self.active_accessory_id: str | None = None
        self._last_rendered_accessory_key: tuple[str, int, bool] | None = None

        self.accessories_manager = accessories_manager or self.pet_window._accessories_manager
        self.pet_window.set_accessories_manager(self.accessories_manager)
        self.pet_window.set_accessory_selection(self.accessory_mode, self.custom_accessory_id)

        self.perch_controller = perch_controller or PerchController(
            enabled=self.perch_enabled,
            parent=self,
        )
        if perch_controller is not None:
            if self.perch_enabled:
                self.perch_controller.set_enabled(True)
            elif self.perch_controller.enabled:
                self.perch_enabled = True
                self.pet_window.set_perch_checked(True)

        self.sound_engine = sound_engine or RetroSoundEngine(enabled=self.sounds_enabled)
        if sound_engine is not None:
            if self.sounds_enabled:
                self.sound_engine.set_enabled(True)
            elif self.sound_engine.enabled:
                self.sounds_enabled = True
                self.pet_window.set_sounds_checked(True)

        self.ink_splat_manager = ink_splat_manager or InkSplatManager(
            scale=self.pet_window.controller.scale,
            always_on_top=self.pet_window._always_on_top,
            parent=self,
        )
        self.coffee_window: CoffeeCupWindow | None = None
        self.stats_window: StatsCardWindow | None = None

        self.bubble_widget.set_auto_hide_enabled(self.pet_window.settings.auto_hide_bubble)
        if self.click_through:
            _apply_click_through(self.bubble_widget, True)
        self.active_clones: dict[str, JulesSubagentWindow] = {}
        self._overflow_subagents: dict[str, tuple[str, str]] = {}
        self._orbit_counter: int = 0
        self._cleaning_up: bool = False

        # Global/window shortcut to toggle Click-Through mode
        self.shortcut_click_through = QShortcut(QKeySequence("Ctrl+Shift+J"), self.pet_window)
        self.shortcut_click_through.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_click_through.activated.connect(self.toggle_click_through)

        # Wire pet window menu & geometry signals
        self.pet_window.approval_bridge_toggled.connect(self.set_approval_bridge_enabled)
        self.pet_window.auto_hide_bubble_toggled.connect(self.set_auto_hide_bubble)
        self.pet_window.click_through_toggled.connect(self.set_click_through)
        self.pet_window.accessory_selected.connect(self.set_accessory)
        self.pet_window.perch_toggled.connect(self.set_perch_enabled)
        self.pet_window.sounds_toggled.connect(self.set_sounds_enabled)
        self.pet_window.coffee_requested.connect(self.offer_coffee)
        self.pet_window.stats_requested.connect(self.show_stats)
        self.pet_window.user_interacted.connect(self._on_user_interacted)
        self.pet_window.moved.connect(self._on_pet_moved)

        # Wire perch & buddy signals
        self.perch_controller.perch_target_changed.connect(self._on_perch_target_changed)
        self.buddy.ink_shock_requested.connect(self._on_ink_shock_requested)

        # Wire bubble approval decisions back to IPC server
        self.bubble_widget.approval_decided.connect(self._on_approval_decided)

        # Wire IPC server signals
        self.ipc_server.event_received.connect(self.on_ipc_event)
        self.ipc_server.approval_requested.connect(self._on_approval_requested)

        # Wire transcript watcher signals
        self.transcript_watcher.context_updated.connect(self._on_context_updated)
        self.transcript_watcher.subagent_event.connect(self.on_subagent_event)

        # Periodic timers for transcript polling and passive buddy energy tick
        self._transcript_timer = QTimer(self)
        self._transcript_timer.setInterval(500)
        self._transcript_timer.timeout.connect(self.transcript_watcher.poll)

        self._buddy_timer = QTimer(self)
        self._buddy_timer.setInterval(250)
        self._buddy_timer.timeout.connect(self._on_buddy_tick)

        self._sync_buddy_to_ui()
        if auto_start:
            self.start()

    @property
    def overflow_count(self) -> int:
        """Number of active subagents exceeding MAX_VISIBLE_CLONES."""
        return len(self._overflow_subagents)

    def start(self) -> bool:
        """Start IPC listening, background polling timers, and show the status bubble."""
        ok = self.ipc_server.start()
        self._transcript_timer.start()
        self._buddy_timer.start()
        self._anchor_bubble()
        self.bubble_widget.show_temporary(IDLE_HIDE_MS)
        return ok

    def stop(self) -> None:
        """Stop timers, close IPC server, clean up all clones/overlays, and hide the bubble."""
        self._transcript_timer.stop()
        self._buddy_timer.stop()
        self.perch_controller._timer.stop()
        self.ink_splat_manager.clear_all()
        if self.coffee_window is not None:
            self.coffee_window.close()
            self.coffee_window.deleteLater()
            self.coffee_window = None
        if self.stats_window is not None:
            self.stats_window.close()
            self.stats_window.deleteLater()
            self.stats_window = None
        self.cleanup_all_clones()
        self.ipc_server.close()
        self.bubble_widget.close()

    def set_auto_hide_bubble(self, enabled: bool) -> None:
        """Enable or disable auto-hiding the status bubble when idle."""
        self.bubble_widget.set_auto_hide_enabled(enabled)
        self.pet_window.set_auto_hide_bubble_checked(self.bubble_widget.auto_hide_enabled)
        self.pet_window.save_preference("auto_hide_bubble", self.bubble_widget.auto_hide_enabled)
        if self.bubble_widget.isVisible():
            self._anchor_bubble()

    def set_approval_bridge_enabled(self, enabled: bool) -> None:
        """Enable or disable routing tool approvals to the mascot bubble."""
        self.approval_bridge_enabled = bool(enabled)
        self.pet_window.set_approval_bridge_checked(self.approval_bridge_enabled)
        self.pet_window.save_preference("approval_bridge_enabled", self.approval_bridge_enabled)
        if not self.approval_bridge_enabled:
            pending_id = self.bubble_widget.pending_request_id
            if pending_id:
                self.bubble_widget.hide_approval()
                self.ipc_server.resolve_approval(pending_id, "ask", "approval_bridge_disabled")

    def set_click_through(self, enabled: bool) -> None:
        """Toggle click-through across Jules, bubble, and all active clones."""
        self.click_through = bool(enabled)
        self.pet_window.set_click_through(self.click_through)
        _apply_click_through(self.bubble_widget, self.click_through)
        for clone in self.active_clones.values():
            clone.set_click_through(self.click_through)
        self.pet_window.set_click_through_checked(self.click_through)
        self.pet_window.save_preference("click_through", self.click_through)

    def toggle_click_through(self) -> None:
        """Invert the current click-through mode."""
        self.set_click_through(not self.click_through)

    def set_accessory(self, mode: str, custom_id: str = "") -> None:
        """Select the active accessory mode/custom ID and persist it."""
        self.accessory_mode = (mode or "auto").strip() or "auto"
        self.custom_accessory_id = (custom_id or "").strip()
        self.pet_window.set_accessory_selection(self.accessory_mode, self.custom_accessory_id)
        self.pet_window.save_preference("accessory_mode", self.accessory_mode)
        self.pet_window.save_preference("custom_accessory_id", self.custom_accessory_id)
        self._sync_accessory()

    def set_perch_enabled(self, enabled: bool) -> None:
        """Enable or disable perching on active IDE/terminal windows."""
        self.perch_enabled = bool(enabled)
        self.perch_controller.set_enabled(self.perch_enabled)
        self.pet_window.set_perch_checked(self.perch_enabled)
        self.pet_window.save_preference("perch_enabled", self.perch_enabled)
        if self.perch_enabled:
            self.perch_controller.poll()

    def set_sounds_enabled(self, enabled: bool) -> None:
        """Enable or disable procedural 8-bit sound effects."""
        self.sounds_enabled = bool(enabled)
        self.sound_engine.set_enabled(self.sounds_enabled)
        self.pet_window.set_sounds_checked(self.sounds_enabled)
        self.pet_window.save_preference("sounds_enabled", self.sounds_enabled)

    def offer_coffee(self) -> CoffeeCupWindow:
        """Spawn a steaming coffee cup and steer Jules over for a coffee break."""
        if self.coffee_window is not None:
            self.coffee_window.close()
            self.coffee_window.deleteLater()
            self.coffee_window = None

        cup_scale = max(2, self.pet_window.controller.scale - 1)
        cup = CoffeeCupWindow(scale=cup_scale)
        screen = self.pet_window.screen_rect()
        pet_center = self.pet_window.controller.sprite_center

        offset_x = -110 if pet_center.x() > screen.center().x() else 110
        raw_x = int(round(pet_center.x() + offset_x - cup.width() / 2.0))
        raw_y = int(round(pet_center.y() - cup.height() / 2.0 + 10.0))
        max_x = max(screen.left(), screen.left() + screen.width() - cup.width())
        max_y = max(screen.top(), screen.top() + screen.height() - cup.height())
        cup.move(
            max(screen.left(), min(raw_x, max_x)),
            max(screen.top(), min(raw_y, max_y)),
        )
        cup.show()
        self.coffee_window = cup

        def _on_drink_finished() -> None:
            if self.coffee_window is cup:
                self.coffee_window = None
            cup.close()
            cup.deleteLater()

        def _on_arrived() -> None:
            self.buddy.take_coffee_break()
            self._sync_buddy_to_ui()
            self.bubble_widget.show_temporary(DONE_HIDE_MS)
            cup.start_drinking()

        cup.drink_finished.connect(_on_drink_finished)
        self.pet_window.controller.start_coffee_break(cup.cup_center(), on_arrived=_on_arrived)
        return cup

    def current_session_stats(self) -> SessionStats:
        """Snapshot the buddy telemetry into a SessionStats dataclass."""
        return SessionStats(
            total_tokens=self.buddy.total_tokens,
            total_subagents=self.buddy.total_subagents,
            commands_succeeded=self.buddy.commands_succeeded,
            commands_total=self.buddy.commands_total,
            pet_count=self.buddy.pet_count,
            energy=self.buddy.energy,
            mood_score=self.buddy.mood_score,
            mood_label=_MOOD_LABELS.get(self.buddy.mood, "De boas"),
            session_duration_seconds=self.buddy.session_duration_seconds,
        )

    def show_stats(self) -> StatsCardWindow:
        """Open or refresh the retro RPG SessionStats HUD card."""
        stats = self.current_session_stats()
        if self.stats_window is None:
            self.stats_window = StatsCardWindow(stats=stats)
        else:
            self.stats_window.update_stats(stats)
        self.stats_window.show()
        self.stats_window.raise_()
        return self.stats_window

    def _on_perch_target_changed(self, rect: object) -> None:
        self.pet_window.controller.set_perch_rect(
            rect if hasattr(rect, "top") else None,
            self.pet_window.screen_rect(),
        )
        self.pet_window.move(
            int(round(self.pet_window.controller.x)),
            int(round(self.pet_window.controller.y)),
        )

    def _on_ink_shock_requested(self) -> None:
        self.ink_splat_manager.scale = self.pet_window.controller.scale
        self.ink_splat_manager.always_on_top = self.pet_window._always_on_top
        self.ink_splat_manager.spawn_splats(
            self.pet_window.controller.sprite_center,
            self.pet_window.screen_rect(),
            count=3,
        )
        self.sound_engine.play(SoundEffect.SQUIRT)

    def _sync_accessory(self) -> None:
        swarm_count = len(self.active_clones) + self.overflow_count
        spec = self.accessories_manager.resolve_active_accessory(
            mode=self.accessory_mode,
            custom_id=self.custom_accessory_id,
            category=self.buddy.active_category,
            swarm_count=swarm_count,
        )
        if spec is None:
            self.active_accessory_id = None
            if self._last_rendered_accessory_key is not None:
                self._last_rendered_accessory_key = None
                self.pet_window.set_active_accessory(None, 0, 0)
            return

        self.active_accessory_id = spec.id
        ctrl = self.pet_window.controller
        render_key = (spec.id, ctrl.scale, ctrl.facing_left)
        if render_key == self._last_rendered_accessory_key:
            return
        self._last_rendered_accessory_key = render_key
        pix, ox, oy = render_accessory_pixmap(
            spec,
            scale=ctrl.scale,
            flip_x=ctrl.facing_left,
        )
        self.pet_window.set_active_accessory(pix, ox, oy)

    def cleanup_all_clones(self) -> None:
        """Immediately remove all subagent clone windows and reset overflow count."""
        self._cleaning_up = True
        try:
            self._overflow_subagents.clear()
            for subagent_id in list(self.active_clones.keys()):
                clone = self.active_clones.pop(subagent_id)
                clone.blockSignals(True)
                clone.close()
                clone.deleteLater()
            self.bubble_widget.set_swarm_overflow(0)
            self._anchor_bubble()
            self._sync_accessory()
        finally:
            self._cleaning_up = False

    def on_ipc_event(self, event: dict[str, Any]) -> None:
        """Handle incoming hook IPC event, update buddy, and handle Stop cleanup."""
        if not isinstance(event, dict):
            return

        transcript_path = event.get("transcript_path") or event.get("transcriptPath")
        if transcript_path:
            self.transcript_watcher.set_transcript_path(str(transcript_path))

        self.buddy.handle_event(event)
        self._sync_buddy_to_ui()
        self._update_bubble_visibility_for_event(event)

        if (
            event.get("type") == "lifecycle"
            and event.get("event") == "Stop"
            and bool(event.get("fully_idle", False))
        ):
            self.cleanup_all_clones()
            if not str(event.get("error") or "").strip():
                self.sound_engine.play(SoundEffect.LEVEL_UP)

        if self.transcript_watcher.transcript_path is not None:
            self.transcript_watcher.poll()

    def _update_bubble_visibility_for_event(self, event: dict[str, Any]) -> None:
        msg_type = str(event.get("type") or "")
        if msg_type == "tool_start":
            self.bubble_widget.show_persistent()
        elif msg_type == "tool_end":
            if self.buddy.phase == "error":
                self.bubble_widget.show_temporary(IDLE_HIDE_MS)
            else:
                self.bubble_widget.show_temporary(DONE_HIDE_MS)
        elif msg_type == "lifecycle":
            lifecycle_event = str(event.get("event") or "")
            if lifecycle_event == "PreInvocation":
                self.bubble_widget.show_persistent()
            elif lifecycle_event == "Stop":
                if self.buddy.phase == "error":
                    self.bubble_widget.show_temporary(IDLE_HIDE_MS)
                else:
                    self.bubble_widget.show_temporary(DONE_HIDE_MS)
            elif lifecycle_event in ("SessionStart", "PostInvocation"):
                self.bubble_widget.show_temporary(IDLE_HIDE_MS)

    def _on_user_interacted(self, _kind: str) -> None:
        self.buddy.on_pet()
        self.sound_engine.play(SoundEffect.BLIP)
        self._sync_buddy_to_ui()
        self.bubble_widget.show_temporary(IDLE_HIDE_MS)

    def _on_approval_requested(self, request_id: str, tool: str, command: str) -> None:
        if not self.approval_bridge_enabled:
            self.ipc_server.resolve_approval(request_id, "ask", "approval_bridge_disabled")
            self.buddy.handle_event({"type": "approval_response", "decision": "ask"})
            self._sync_buddy_to_ui()
            return

        self.bubble_widget.show_approval(request_id, tool, command)
        self._anchor_bubble()
        self.bubble_widget.show()

    def _on_approval_decided(self, request_id: str, decision: str) -> None:
        self.ipc_server.resolve_approval(request_id, decision)
        self.buddy.handle_event({"type": "approval_response", "decision": decision})
        self._sync_buddy_to_ui()

    def _on_context_updated(
        self,
        input_tokens: int,
        cache_read_tokens: int,
        pressure_ratio: float,
    ) -> None:
        self.buddy.update_context(input_tokens, cache_read_tokens, pressure_ratio)
        self._sync_buddy_to_ui()

    def on_subagent_event(
        self,
        kind: str,
        subagent_id: str,
        role: str = "",
        type_name: str = "",
    ) -> None:
        """Handle TranscriptWatcher subagent spawn/done notifications."""
        if not subagent_id:
            return

        if kind == "spawn":
            if subagent_id in self.active_clones or subagent_id in self._overflow_subagents:
                return
            self.buddy.record_subagent_spawn()
            self.pet_window.controller.set_annoyed()
            if len(self.active_clones) < self.MAX_VISIBLE_CLONES:
                self._spawn_visible_clone(subagent_id, role, type_name)
            else:
                self._overflow_subagents[subagent_id] = (role, type_name)
            self.bubble_widget.set_swarm_overflow(self.overflow_count)
            self._anchor_bubble()
            self._sync_accessory()
            return

        if kind == "done":
            self.pet_window.controller.trigger_high_five()
            self.sound_engine.play(SoundEffect.POWER_UP)
            if subagent_id in self._overflow_subagents:
                self._overflow_subagents.pop(subagent_id, None)
                self.bubble_widget.set_swarm_overflow(self.overflow_count)
                self._anchor_bubble()
                self._sync_accessory()
                return

            clone = self.active_clones.get(subagent_id)
            if clone is not None:
                clone.begin_return(self.pet_window.controller.sprite_center)

    def _allocate_hue_shift(self) -> float:
        used = {round(clone.hue_shift % 1.0, 3) for clone in self.active_clones.values()}
        for candidate in _CLONE_HUE_SHIFTS:
            if round(candidate % 1.0, 3) not in used:
                return candidate
        idx = len(self.active_clones) + 1
        return round(((idx * 0.61803398875) % 0.86) + 0.07, 3)

    def _spawn_visible_clone(self, subagent_id: str, role: str, type_name: str) -> None:
        hue_shift = self._allocate_hue_shift()
        clone_scale = max(2, self.pet_window.controller.scale - 1)
        clone = JulesSubagentWindow(
            subagent_id=subagent_id,
            role=role,
            type_name=type_name,
            hue_shift=hue_shift,
            scale=clone_scale,
            orbit_index=self._orbit_counter,
            anchor_center=self.pet_window.controller.sprite_center,
            screen_rect=self.pet_window.screen_rect(),
            always_on_top=self.pet_window._always_on_top,
        )
        self._orbit_counter += 1
        clone.finished.connect(self._on_clone_finished)
        if self.click_through:
            clone.set_click_through(True)
        self.active_clones[subagent_id] = clone
        clone.show()

    def _on_clone_finished(self, subagent_id: str) -> None:
        clone = self.active_clones.pop(subagent_id, None)
        if clone is not None:
            clone.close()
            clone.deleteLater()

        if (
            not self._cleaning_up
            and self._overflow_subagents
            and len(self.active_clones) < self.MAX_VISIBLE_CLONES
        ):
            next_id, (next_role, next_type) = next(iter(self._overflow_subagents.items()))
            self._overflow_subagents.pop(next_id, None)
            self._spawn_visible_clone(next_id, next_role, next_type)

        self.bubble_widget.set_swarm_overflow(self.overflow_count)
        self._anchor_bubble()
        self._sync_accessory()

    def _on_pet_moved(self) -> None:
        self._anchor_bubble()
        center = self.pet_window.controller.sprite_center
        for clone in self.active_clones.values():
            clone.set_anchor_center(center)

    def _on_buddy_tick(self) -> None:
        self.buddy.tick(0.25)
        self._sync_buddy_to_ui()

    def _sync_buddy_to_ui(self) -> None:
        ctrl = self.pet_window.controller
        if self.buddy._pending_ink_shock or not ctrl._ai_timed:
            self.buddy.apply_to_controller(ctrl)
        else:
            ctrl.set_context_pressure(self.buddy.context_pressure)
        self.bubble_widget.set_status(self.buddy.status_verb)
        self._anchor_bubble()
        self._sync_accessory()
        if self.stats_window is not None and self.stats_window.isVisible():
            self.stats_window.update_stats(self.current_session_stats())

    def _anchor_bubble(self) -> None:
        self.bubble_widget.anchor_near(
            self.pet_window.pet_rect(),
            self.pet_window.screen_rect(),
        )
