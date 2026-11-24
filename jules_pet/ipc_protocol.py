"""IPC JSON-Lines protocol helpers and tool categorization."""

from __future__ import annotations

import json
from typing import Any

DEFAULT_IPC_HOST = "127.0.0.1"
DEFAULT_IPC_PORT = 18765
DEFAULT_APPROVAL_TIMEOUT_MS = 20_000

_READ_SEARCH_TOOLS = frozenset(
    {
        "read_file",
        "grep_search",
        "find_by_name",
        "list_dir",
        "view_file",
        "view_file_outline",
        "view_code_item",
    }
)

_EDIT_WRITE_TOOLS = frozenset(
    {
        "edit_file",
        "write_file",
        "replace_file_content",
        "multi_replace_file_content",
        "write_to_file",
    }
)

_TERMINAL_TOOLS = frozenset(
    {
        "run_command",
        "command_status",
        "send_command_input",
    }
)


def parse_ipc_message(raw_line: str | bytes) -> dict[str, Any] | None:
    """Parse a single JSON-Lines message safely, returning None on invalid input."""
    if isinstance(raw_line, (bytes, bytearray)):
        raw_line = raw_line.decode("utf-8", errors="replace")
    if not isinstance(raw_line, str):
        return None

    text = raw_line.strip()
    if not text:
        return None

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def encode_ipc_message(payload: dict[str, Any]) -> bytes:
    """Serialize a dictionary as a newline-terminated UTF-8 JSON line."""
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


def categorize_tool(tool_name: str) -> str:
    """Map an Antigravity tool name into a mascot animation/status category."""
    if not isinstance(tool_name, str):
        return "other"

    normalized = tool_name.strip().lower()
    if not normalized:
        return "other"

    if normalized in _READ_SEARCH_TOOLS:
        return "read_search"
    if normalized in _EDIT_WRITE_TOOLS:
        return "edit_write"
    if normalized in _TERMINAL_TOOLS:
        return "terminal"
    if normalized.startswith("browser_"):
        return "browser"
    if normalized == "invoke_subagent":
        return "subagent"
    return "other"
