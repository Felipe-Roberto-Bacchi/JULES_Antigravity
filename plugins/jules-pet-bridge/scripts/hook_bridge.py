"""Stdlib-only Antigravity hook bridge for Jules Desktop Pet.

Reads an Antigravity lifecycle/tool hook payload from stdin, forwards a
normalized JSON-Lines event over loopback TCP to Jules Desktop Pet, and writes
a valid Antigravity hook response JSON object to stdout. Fails open quickly
when the pet is offline or unreachable.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import uuid

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18765
CONNECT_TIMEOUT_S = 0.08
DEFAULT_APPROVAL_TIMEOUT_S = 20.0
VALID_DECISIONS = frozenset({"allow", "deny", "ask", "force_ask"})

_TERMINAL_TOOLS = frozenset(
    {"run_command", "command_status", "send_command_input", "read_terminal"}
)
_READ_SEARCH_TOOLS = frozenset(
    {
        "read_file",
        "view_file",
        "list_dir",
        "find_by_name",
        "grep_search",
        "search_web",
        "read_url_content",
        "view_file_outline",
        "view_code_item",
    }
)
_EDIT_WRITE_TOOLS = frozenset(
    {
        "write_file",
        "write_to_file",
        "edit_file",
        "replace_file_content",
        "multi_replace_file_content",
    }
)


def categorize_tool(tool_name: str) -> str:
    """Map an Antigravity tool name to a compact Jules Pet category."""
    if tool_name in _TERMINAL_TOOLS:
        return "terminal"
    if tool_name in _READ_SEARCH_TOOLS:
        return "read_search"
    if tool_name in _EDIT_WRITE_TOOLS:
        return "edit_write"
    if tool_name.startswith("browser_") or tool_name in {"open_browser_url", "read_browser_page"}:
        return "browser"
    return "other"


def _summarize_tool_call(tool_name: str, args: dict) -> str:
    """Extract a short human-readable summary from tool arguments."""
    for key in ("CommandLine", "command", "Path", "TargetFile", "AbsolutePath", "query", "Url"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:160]
    return tool_name


def _get_host_port() -> tuple[str, int]:
    host = os.environ.get("JULES_PET_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    raw_port = os.environ.get("JULES_PET_PORT", str(DEFAULT_PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError:
        port = DEFAULT_PORT
    return host, port


def _get_approval_timeout() -> float:
    raw = os.environ.get("JULES_APPROVAL_TIMEOUT", str(DEFAULT_APPROVAL_TIMEOUT_S)).strip()
    try:
        timeout = float(raw)
        return timeout if timeout > 0.0 else DEFAULT_APPROVAL_TIMEOUT_S
    except ValueError:
        return DEFAULT_APPROVAL_TIMEOUT_S


def _approval_bridge_enabled() -> bool:
    return os.environ.get("JULES_PET_APPROVAL_BRIDGE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _send_fire_and_forget(host: str, port: int, message: dict) -> None:
    """Send a single JSON-Line message with an 80ms connect timeout."""
    data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(CONNECT_TIMEOUT_S)
        sock.connect((host, port))
        sock.sendall(data)


def _request_approval(
    host: str,
    port: int,
    message: dict,
    request_id: str,
    timeout_s: float,
) -> dict:
    """Send an approval_request and wait for a matching approval_response."""
    data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(CONNECT_TIMEOUT_S)
        sock.connect((host, port))
        sock.sendall(data)
        sock.settimeout(timeout_s)

        buf = b""
        while len(buf) < 65536:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    reply = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(reply, dict):
                    continue
                if reply.get("type") != "approval_response":
                    continue
                if reply.get("request_id") and reply.get("request_id") != request_id:
                    continue
                decision = reply.get("decision")
                if decision not in VALID_DECISIONS:
                    return {"decision": "ask"}
                out: dict[str, str] = {"decision": decision}
                reason = reply.get("reason")
                if isinstance(reason, str) and reason:
                    out["reason"] = reason
                return out
    return {"decision": "ask"}


def _handle_payload(payload: dict) -> dict:
    """Dispatch an Antigravity hook payload and return the stdout JSON object."""
    event = payload.get("hookEventName", "")
    host, port = _get_host_port()
    conversation_id = payload.get("conversationId", "")
    transcript_path = payload.get("transcriptPath", "")

    if event == "PreToolUse":
        tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
        tool_name = str(tool_call.get("name", ""))
        call_id = str(tool_call.get("id", ""))
        args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
        summary = _summarize_tool_call(tool_name, args)

        if _approval_bridge_enabled() and tool_name == "run_command":
            timeout_s = _get_approval_timeout()
            request_id = str(uuid.uuid4())
            req_msg = {
                "type": "approval_request",
                "request_id": request_id,
                "tool": tool_name,
                "call_id": call_id,
                "command": summary,
                "transcript_path": transcript_path,
                "conversation_id": conversation_id,
                "timeout_ms": int(timeout_s * 1000),
            }
            try:
                return _request_approval(host, port, req_msg, request_id, timeout_s)
            except OSError:
                return {"decision": "ask"}

        msg = {
            "type": "tool_start",
            "call_id": call_id,
            "tool": tool_name,
            "category": categorize_tool(tool_name),
            "summary": summary,
            "transcript_path": transcript_path,
            "conversation_id": conversation_id,
        }
        try:
            _send_fire_and_forget(host, port, msg)
        except OSError:
            pass
        return {"decision": "ask"}

    if event == "PostToolUse":
        tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
        tool_name = str(tool_call.get("name", ""))
        call_id = str(tool_call.get("id", ""))
        error = payload.get("error") or ""
        msg = {
            "type": "tool_end",
            "call_id": call_id,
            "tool": tool_name,
            "ok": not bool(error),
            "error": str(error),
            "transcript_path": transcript_path,
            "conversation_id": conversation_id,
        }
        try:
            _send_fire_and_forget(host, port, msg)
        except OSError:
            pass
        return {}

    if event in {"SessionStart", "PreInvocation", "PostInvocation", "Stop"}:
        msg = {
            "type": "lifecycle",
            "event": event,
            "conversation_id": conversation_id,
            "transcript_path": transcript_path,
            "workspace_paths": payload.get("workspacePaths", []),
            "termination_reason": payload.get("terminationReason", ""),
            "fully_idle": bool(payload.get("fullyIdle", False)),
            "error": str(payload.get("error") or ""),
        }
        try:
            _send_fire_and_forget(host, port, msg)
        except OSError:
            pass
        return {}

    return {}


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except json.JSONDecodeError:
        payload = {}

    try:
        response = _handle_payload(payload)
    except Exception:
        response = {"decision": "ask"} if payload.get("hookEventName") == "PreToolUse" else {}

    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
