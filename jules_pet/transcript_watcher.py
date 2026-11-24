"""Incremental JSONL watcher for Antigravity transcript.jsonl metrics and subagents."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from jules_pet.ipc_protocol import parse_ipc_message

DEFAULT_CONTEXT_WINDOW = 1_000_000

_SYSTEM_SENDER_RE = re.compile(r"\bsender=([^\s\]>]+)")
_CONVERSATION_ID_RE = re.compile(
    r'(?:conversationId|conversation_id)["\s:=]+([0-9a-fA-F-]{6,}|[A-Za-z0-9_-]{3,})'
)


def _clean_arg_str(value: Any) -> str:
    """Normalize an arg value that may be double-encoded as a JSON string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        return str(value)
    text = value.strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        try:
            decoded = json.loads(text)
            if isinstance(decoded, str):
                return decoded
        except (json.JSONDecodeError, ValueError):
            pass
    return text


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


class TranscriptWatcher(QObject):
    """Tails an Antigravity transcript.jsonl file for token usage and subagent lifecycle."""

    context_updated = Signal(int, int, float)
    subagent_event = Signal(str, str, str, str)

    def __init__(
        self,
        context_window: int = DEFAULT_CONTEXT_WINDOW,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._context_window = max(1, int(context_window))
        self._path: Path | None = None
        self._offset: int = 0
        self._active_subagents: dict[str, tuple[str, str]] = {}
        self._pending_spawns: list[tuple[str, str]] = []

    @property
    def transcript_path(self) -> Path | None:
        return self._path

    def set_transcript_path(self, path: str | Path | None) -> None:
        """Point the watcher at a new transcript file and reset incremental cursor."""
        new_path = Path(path) if path else None
        if new_path == self._path:
            return
        self._path = new_path
        self._offset = 0
        self._active_subagents.clear()
        self._pending_spawns.clear()

    def poll(self) -> None:
        """Read newly appended JSONL lines and emit context/subagent signals."""
        if self._path is None or not self._path.is_file():
            return

        try:
            with self._path.open("rb") as fh:
                fh.seek(0, os.SEEK_END)
                file_size = fh.tell()
                if file_size < self._offset:
                    self._offset = 0
                if file_size == self._offset:
                    return
                fh.seek(self._offset)
                chunk = fh.read()
                self._offset = fh.tell()
        except OSError:
            return

        text = chunk.decode("utf-8", errors="replace")
        for line in text.splitlines():
            entry = parse_ipc_message(line)
            if entry is None:
                continue
            self._process_entry(entry)

    def _process_entry(self, entry: dict[str, Any]) -> None:
        entry_type = entry.get("type")

        if entry_type == "PLANNER_RESPONSE":
            self._handle_planner_response(entry)
        elif entry_type == "GENERIC" and self._pending_spawns:
            self._handle_generic_result(entry)
        elif entry_type == "SYSTEM_MESSAGE":
            self._handle_system_message(entry)

    def _handle_planner_response(self, entry: dict[str, Any]) -> None:
        if "input_tokens" in entry or "cache_read_tokens" in entry:
            input_tokens = _safe_int(entry.get("input_tokens"))
            cache_read_tokens = _safe_int(entry.get("cache_read_tokens"))
            total_tokens = input_tokens + cache_read_tokens
            pressure_ratio = min(1.0, max(0.0, total_tokens / self._context_window))
            self.context_updated.emit(input_tokens, cache_read_tokens, pressure_ratio)

        tool_calls = entry.get("tool_calls")
        if not isinstance(tool_calls, list):
            return

        for call in tool_calls:
            if not isinstance(call, dict) or call.get("name") != "invoke_subagent":
                continue

            args = call.get("args")
            if not isinstance(args, dict):
                args = {}

            role = _clean_arg_str(args.get("Role") or args.get("role"))
            type_name = _clean_arg_str(args.get("TypeName") or args.get("type_name"))
            subagent_id = _clean_arg_str(
                args.get("conversationId")
                or args.get("conversation_id")
                or args.get("subagent_id")
                or call.get("conversationId")
                or call.get("conversation_id")
                or call.get("subagent_id")
                or call.get("id")
                or call.get("call_id")
            )

            if subagent_id:
                self._active_subagents[subagent_id] = (role, type_name)
                self.subagent_event.emit("spawn", subagent_id, role, type_name)
            else:
                self._pending_spawns.append((role, type_name))

    def _handle_generic_result(self, entry: dict[str, Any]) -> None:
        content = entry.get("content")
        if not isinstance(content, str):
            return
        match = _CONVERSATION_ID_RE.search(content)
        if not match:
            return
        subagent_id = match.group(1)
        if subagent_id in self._active_subagents or "/" in subagent_id:
            return
        role, type_name = self._pending_spawns.pop(0)
        self._active_subagents[subagent_id] = (role, type_name)
        self.subagent_event.emit("spawn", subagent_id, role, type_name)

    def _handle_system_message(self, entry: dict[str, Any]) -> None:
        sender = _clean_arg_str(entry.get("sender"))
        if not sender:
            content = entry.get("content")
            if isinstance(content, str):
                match = _SYSTEM_SENDER_RE.search(content)
                if match:
                    sender = match.group(1)

        if not sender:
            return

        info = self._active_subagents.pop(sender, None)
        if info is None:
            return

        role, type_name = info
        self.subagent_event.emit("done", sender, role, type_name)
