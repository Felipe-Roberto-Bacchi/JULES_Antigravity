"""Claude Code /buddy parity session state model for Jules Desktop Pet."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Signal

from jules_pet.ipc_protocol import categorize_tool
from jules_pet.physics import PetController

SWEAT_PRESSURE_THRESHOLD = 0.75


@dataclass(frozen=True)
class _CategoryBehavior:
    eye_mode: str
    frame_prefix: str | None
    verbs: tuple[str, ...]


_CATEGORY_BEHAVIORS: dict[str, _CategoryBehavior] = {
    "read_search": _CategoryBehavior(
        eye_mode="scanning",
        frame_prefix=None,
        verbs=(
            "Fuçando os arquivos...",
            "Farejando pistas no código...",
            "Lendo com lupa de polvo...",
        ),
    ),
    "edit_write": _CategoryBehavior(
        eye_mode="coding",
        frame_prefix="coding",
        verbs=(
            "Codando com 8 tentáculos...",
            "Escrevendo código fresquinho...",
            "Refatorando na tinta...",
        ),
    ),
    "terminal": _CategoryBehavior(
        eye_mode="coding",
        frame_prefix="coding",
        verbs=(
            "Mandando ver no terminal...",
            "Rodando feitiços no shell...",
            "Testando na coragem...",
        ),
    ),
    "browser": _CategoryBehavior(
        eye_mode="scanning",
        frame_prefix=None,
        verbs=(
            "Navegando nos mares da web...",
            "Espiando o navegador...",
        ),
    ),
    "subagent": _CategoryBehavior(
        eye_mode="thinking",
        frame_prefix=None,
        verbs=(
            "Chamando reforços do enxame...",
            "Organizando o time de polvos...",
        ),
    ),
    "other": _CategoryBehavior(
        eye_mode="thinking",
        frame_prefix=None,
        verbs=(
            "Fazendo malabarismo...",
            "Quebrando a cuca...",
        ),
    ),
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


class BuddySessionModel(QObject):
    """Tracks mascot mood, energy, context pressure, and Portuguese status verbs."""

    state_changed = Signal()
    ink_shock_requested = Signal()
    high_five_requested = Signal()
    context_pressure_changed = Signal(float, bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.energy: float = 85.0
        self.mood_score: float = 80.0
        self.mood: str = "idle"
        self.context_pressure: float = 0.0

        self.phase: str = "idle"
        self.eye_mode: str = "normal"
        self.frame_prefix: str | None = None
        self.status_verb: str = "De boas no aquário..."

        self.active_tool: str = ""
        self.active_category: str = ""
        self.input_tokens: int = 0
        self.cache_read_tokens: int = 0
        self.total_tokens: int = 0
        self.last_error: str = ""

        self.session_duration_seconds: float = 0.0
        self.total_subagents: int = 0
        self.commands_succeeded: int = 0
        self.commands_total: int = 0
        self.pet_count: int = 0
        self.is_exhausted: bool = False

        self._verb_cursor: int = 0
        self._pending_ink_shock: bool = False
        self._coffee_reset_duration: float = 0.0

    @property
    def is_sweating(self) -> bool:
        """Return True when context window pressure reaches the sweat threshold."""
        return self.context_pressure >= SWEAT_PRESSURE_THRESHOLD

    def _next_verb(self, verbs: tuple[str, ...]) -> str:
        verb = verbs[self._verb_cursor % len(verbs)]
        self._verb_cursor += 1
        return verb

    def _refresh_mood_label(self) -> None:
        if self.phase == "error":
            self.mood = "shocked"
        elif self.is_sweating:
            self.mood = "sweating"
        elif self.is_exhausted or self.energy <= 25.0:
            self.mood = "tired"
        elif self.mood_score >= 85.0:
            self.mood = "happy"
        elif self.phase in ("working", "thinking"):
            self.mood = "focused"
        else:
            self.mood = "idle"

    def _update_exhaustion(self) -> None:
        since_coffee = self.session_duration_seconds - self._coffee_reset_duration
        if self.energy < 20.0 or since_coffee >= 10800.0:
            self.is_exhausted = True
            self.status_verb = "Turno da madrugada... só mais 5 minutinhos..."
            self.mood = "tired"

    def handle_event(self, event: dict[str, Any]) -> None:
        """Process an IPC event dict (`tool_start`, `tool_end`, `lifecycle`, `approval_*`)."""
        if not isinstance(event, dict):
            return

        msg_type = str(event.get("type") or "")
        if msg_type == "tool_start":
            self._handle_tool_start(event)
        elif msg_type == "tool_end":
            self._handle_tool_end(event)
        elif msg_type == "lifecycle":
            self._handle_lifecycle(event)
        elif msg_type == "approval_request":
            self._handle_approval_request(event)
        elif msg_type == "approval_response":
            self._handle_approval_response(event)

    def _handle_tool_start(self, event: dict[str, Any]) -> None:
        tool_name = str(event.get("tool") or "")
        raw_category = str(event.get("category") or "").strip().lower()
        category = (
            raw_category
            if raw_category in _CATEGORY_BEHAVIORS
            else categorize_tool(tool_name)
        )
        behavior = _CATEGORY_BEHAVIORS.get(category, _CATEGORY_BEHAVIORS["other"])

        self.phase = "working"
        self.active_tool = tool_name
        self.active_category = category
        self.last_error = ""
        self.eye_mode = behavior.eye_mode
        self.frame_prefix = behavior.frame_prefix
        self.status_verb = self._next_verb(behavior.verbs)
        self.energy = _clamp(self.energy - 0.5, 0.0, 100.0)
        self._refresh_mood_label()
        self.state_changed.emit()

    def _handle_tool_end(self, event: dict[str, Any]) -> None:
        error_text = str(event.get("error") or "").strip()
        ok = bool(event.get("ok", not bool(error_text)))
        self.commands_total += 1
        if ok:
            self.commands_succeeded += 1

        if not ok:
            self.phase = "error"
            self.last_error = error_text or "erro desconhecido"
            self.eye_mode = "shocked_ink"
            self.frame_prefix = None
            self.mood_score = _clamp(self.mood_score - 15.0, 0.0, 100.0)
            self.energy = _clamp(self.energy - 10.0, 0.0, 100.0)
            self.mood = "shocked"
            self.status_verb = "Eita! Deu ruim na ferramenta!"
            self._pending_ink_shock = True
            self.ink_shock_requested.emit()
        else:
            self.phase = "thinking"
            self.last_error = ""
            self.eye_mode = "normal"
            self.frame_prefix = None
            self.mood_score = _clamp(self.mood_score + 3.0, 0.0, 100.0)
            self.status_verb = "Feito! Pensando no próximo passo..."
            self._refresh_mood_label()

        self.state_changed.emit()

    def _handle_lifecycle(self, event: dict[str, Any]) -> None:
        lifecycle_event = str(event.get("event") or "")
        error_text = str(event.get("error") or "").strip()

        if lifecycle_event == "SessionStart":
            self.phase = "idle"
            self.eye_mode = "happy"
            self.frame_prefix = None
            self.last_error = ""
            self.status_verb = "Pronto pra mergulhar no código!"
            self._refresh_mood_label()
        elif lifecycle_event == "PreInvocation":
            self.phase = "thinking"
            self.eye_mode = "thinking"
            self.frame_prefix = None
            self.last_error = ""
            self.status_verb = "Quebrando a cuca..."
            self._refresh_mood_label()
        elif lifecycle_event == "PostInvocation":
            self.phase = "idle"
            self.eye_mode = "normal"
            self.frame_prefix = None
            self.status_verb = "Respirando entre turnos..."
            self._refresh_mood_label()
        elif lifecycle_event == "Stop":
            self.active_tool = ""
            self.active_category = ""
            self.frame_prefix = None
            if error_text:
                self.phase = "error"
                self.last_error = error_text
                self.eye_mode = "shocked_ink"
                self.mood = "shocked"
                self.status_verb = "Travou no meio do mergulho!"
                self._pending_ink_shock = True
                self.ink_shock_requested.emit()
            else:
                self.phase = "done"
                self.eye_mode = "normal"
                self.status_verb = "Missão cumprida! De boas."
                self._refresh_mood_label()

        self.state_changed.emit()

    def _handle_approval_request(self, event: dict[str, Any]) -> None:
        tool_name = str(event.get("tool") or "comando")
        self.phase = "approval_waiting"
        self.active_tool = tool_name
        self.eye_mode = "approval_waiting"
        self.frame_prefix = None
        self.status_verb = f"Posso rodar {tool_name}?"
        self.state_changed.emit()

    def _handle_approval_response(self, event: dict[str, Any]) -> None:
        decision = str(event.get("decision") or "ask")
        if decision == "allow":
            self.phase = "working"
            self.eye_mode = "coding"
            self.frame_prefix = "coding"
            self.status_verb = "Mandando ver autorizado!"
        elif decision == "deny":
            self.phase = "idle"
            self.eye_mode = "annoyed_side_eye"
            self.frame_prefix = None
            self.status_verb = "Beleza, segurando os tentáculos."
        else:
            self.phase = "idle"
            self.eye_mode = "normal"
            self.frame_prefix = None
        self._refresh_mood_label()
        self.state_changed.emit()

    def update_context(
        self,
        input_tokens: int,
        cache_read_tokens: int,
        pressure_ratio: float,
    ) -> None:
        """Update token metrics and context pressure ratio (0.0..1.0)."""
        self.input_tokens = max(0, int(input_tokens))
        self.cache_read_tokens = max(0, int(cache_read_tokens))
        self.total_tokens = self.input_tokens + self.cache_read_tokens
        self.context_pressure = _clamp(pressure_ratio, 0.0, 1.0)
        self._refresh_mood_label()
        self.context_pressure_changed.emit(self.context_pressure, self.is_sweating)
        self.state_changed.emit()

    def record_subagent_spawn(self) -> None:
        """Increment total spawned subagents counter for the session."""
        self.total_subagents += 1
        self.state_changed.emit()

    def on_pet(self) -> None:
        """Boost mood and energy when the user pets Jules."""
        self.pet_count += 1
        self.mood_score = _clamp(self.mood_score + 10.0, 0.0, 100.0)
        self.energy = _clamp(self.energy + 8.0, 0.0, 100.0)
        if self.phase == "error":
            self.phase = "idle"
            self.last_error = ""
            self.eye_mode = "normal"
        self.mood = "happy"
        if self.phase in ("idle", "done"):
            self.status_verb = "Hehe, faz cócegas nos tentáculos!"
        self.state_changed.emit()

    def take_coffee_break(self) -> None:
        """Boost energy & mood, clear exhaustion, and set a happy status verb."""
        self.energy = _clamp(self.energy + 30.0, 0.0, 100.0)
        self.mood_score = _clamp(self.mood_score + 20.0, 0.0, 100.0)
        self.is_exhausted = False
        self._coffee_reset_duration = self.session_duration_seconds
        if self.phase == "error":
            self.phase = "idle"
            self.last_error = ""
        self.eye_mode = "happy"
        self.mood = "happy"
        self.status_verb = "Cafezinho reforçado! Energia lá em cima!"
        self.state_changed.emit()

    def tick(self, dt: float) -> None:
        """Advance session timer, passive energy drain/recovery, and exhaustion state."""
        dt = max(0.0, float(dt))
        if dt == 0.0:
            return
        self.session_duration_seconds += dt
        if self.phase in ("working", "thinking"):
            self.energy = _clamp(self.energy - 0.5 * dt, 0.0, 100.0)
        elif self.phase in ("idle", "done"):
            self.energy = _clamp(self.energy + 1.2 * dt, 0.0, 100.0)
        self._refresh_mood_label()
        self._update_exhaustion()

    def apply_to_controller(self, controller: PetController) -> None:
        """Synchronize buddy expressions, ink shocks, and context sweat onto PetController."""
        controller.set_context_pressure(self.context_pressure)
        if self._pending_ink_shock:
            self._pending_ink_shock = False
            controller.trigger_ink_shock()
            return
        if self.is_exhausted:
            controller.set_exhausted(True)
            return
        if controller.state.name == "EXHAUSTED":
            controller.set_exhausted(False)
        if self.phase in ("idle", "done") and self.eye_mode == "normal":
            controller.set_ai_activity(None)
        else:
            controller.set_ai_activity(self.eye_mode, self.frame_prefix)
