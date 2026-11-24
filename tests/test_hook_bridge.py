"""Tests for the Antigravity jules-pet-bridge plugin and hook_bridge.py."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO_ROOT / "plugins" / "jules-pet-bridge"
HOOK_SCRIPT = PLUGIN_DIR / "scripts" / "hook_bridge.py"


def _get_unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _run_hook(
    payload: dict,
    *,
    port: int,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], float]:
    env = os.environ.copy()
    env["JULES_PET_HOST"] = "127.0.0.1"
    env["JULES_PET_PORT"] = str(port)
    env.pop("JULES_PET_APPROVAL_BRIDGE", None)
    env.pop("JULES_APPROVAL_TIMEOUT", None)
    if extra_env:
        env.update(extra_env)

    start = time.monotonic()
    proc = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        timeout=5.0,
    )
    elapsed = time.monotonic() - start
    return proc, elapsed


class _MockPetServer:
    """Minimal loopback TCP JSON-Lines server simulating JulesPet IPC."""

    def __init__(self, responder=None) -> None:
        self.responder = responder
        self.messages: list[dict] = []
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self._sock.settimeout(0.2)
        self.port = int(self._sock.getsockname()[1])
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self) -> _MockPetServer:
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop_event.set()
        self._thread.join(timeout=2.0)
        self._sock.close()

    def _serve(self) -> None:
        while not self._stop_event.is_set():
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break

            with conn:
                conn.settimeout(1.0)
                buf = b""
                while not self._stop_event.is_set():
                    try:
                        chunk = conn.recv(4096)
                    except TimeoutError:
                        break
                    except OSError:
                        break
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        text = line.decode("utf-8").strip()
                        if not text:
                            continue
                        msg = json.loads(text)
                        self.messages.append(msg)
                        if self.responder is not None:
                            reply = self.responder(msg)
                            if reply is not None:
                                conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))
                            return


def test_plugin_manifests_valid() -> None:
    plugin_json = PLUGIN_DIR / "plugin.json"
    hooks_json = PLUGIN_DIR / "hooks.json"
    readme = PLUGIN_DIR / "README.md"

    assert plugin_json.is_file()
    assert hooks_json.is_file()
    assert HOOK_SCRIPT.is_file()
    assert readme.is_file()

    manifest = json.loads(plugin_json.read_text(encoding="utf-8"))
    assert manifest["name"] == "jules-pet-bridge"
    assert manifest["version"] == "0.1.0"
    assert manifest["displayName"]
    assert manifest["description"]

    hooks = json.loads(hooks_json.read_text(encoding="utf-8"))
    assert "jules-pet-bridge" in hooks
    spec = hooks["jules-pet-bridge"]
    for event in ("SessionStart", "PreInvocation", "PreToolUse", "PostToolUse", "PostInvocation", "Stop"):
        assert event in spec
        assert isinstance(spec[event], list) and len(spec[event]) >= 1


def test_pet_offline_post_tool_use_fails_open_fast() -> None:
    unused_port = _get_unused_port()
    payload = {
        "hookEventName": "PostToolUse",
        "conversationId": "conv-offline-1",
        "transcriptPath": "/tmp/transcript.jsonl",
        "toolCall": {"id": "call-1", "name": "read_file", "args": {"Path": "README.md"}},
    }
    proc, elapsed = _run_hook(payload, port=unused_port)
    assert proc.returncode == 0
    assert elapsed < 0.5
    assert json.loads(proc.stdout.strip()) == {}


def test_pet_offline_pre_tool_use_returns_ask_fast() -> None:
    unused_port = _get_unused_port()
    payload = {
        "hookEventName": "PreToolUse",
        "conversationId": "conv-offline-2",
        "transcriptPath": "/tmp/transcript.jsonl",
        "toolCall": {"id": "call-2", "name": "run_command", "args": {"CommandLine": "pytest"}},
    }
    proc, elapsed = _run_hook(
        payload,
        port=unused_port,
        extra_env={"JULES_PET_APPROVAL_BRIDGE": "1"},
    )
    assert proc.returncode == 0
    assert elapsed < 0.5
    assert json.loads(proc.stdout.strip()) == {"decision": "ask"}


def test_lifecycle_and_post_tool_use_events_sent_as_json_lines() -> None:
    events = [
        {
            "hookEventName": "SessionStart",
            "conversationId": "conv-123",
            "workspacePaths": ["/workspace"],
            "transcriptPath": "/logs/transcript.jsonl",
        },
        {
            "hookEventName": "PreInvocation",
            "conversationId": "conv-123",
            "transcriptPath": "/logs/transcript.jsonl",
            "invocationNum": 1,
        },
        {
            "hookEventName": "PostToolUse",
            "conversationId": "conv-123",
            "transcriptPath": "/logs/transcript.jsonl",
            "toolCall": {"id": "toolu_01", "name": "run_command", "args": {"CommandLine": "npm test"}},
            "error": "exit status 1",
        },
        {
            "hookEventName": "PostInvocation",
            "conversationId": "conv-123",
            "transcriptPath": "/logs/transcript.jsonl",
            "invocationNum": 1,
        },
        {
            "hookEventName": "Stop",
            "conversationId": "conv-123",
            "transcriptPath": "/logs/transcript.jsonl",
            "terminationReason": "NO_TOOL_CALL",
            "fullyIdle": True,
        },
    ]

    with _MockPetServer() as server:
        for payload in events:
            proc, _ = _run_hook(payload, port=server.port)
            assert proc.returncode == 0
            assert json.loads(proc.stdout.strip()) == {}

    assert len(server.messages) == 5

    session_msg, pre_inv_msg, post_tool_msg, post_inv_msg, stop_msg = server.messages
    assert session_msg["type"] == "lifecycle"
    assert session_msg["event"] == "SessionStart"
    assert session_msg["conversation_id"] == "conv-123"
    assert session_msg["transcript_path"] == "/logs/transcript.jsonl"

    assert pre_inv_msg["type"] == "lifecycle"
    assert pre_inv_msg["event"] == "PreInvocation"

    assert post_tool_msg["type"] == "tool_end"
    assert post_tool_msg["call_id"] == "toolu_01"
    assert post_tool_msg["tool"] == "run_command"
    assert post_tool_msg["ok"] is False
    assert post_tool_msg["error"] == "exit status 1"
    assert post_tool_msg["transcript_path"] == "/logs/transcript.jsonl"

    assert post_inv_msg["type"] == "lifecycle"
    assert post_inv_msg["event"] == "PostInvocation"

    assert stop_msg["type"] == "lifecycle"
    assert stop_msg["event"] == "Stop"
    assert stop_msg["termination_reason"] == "NO_TOOL_CALL"
    assert stop_msg["fully_idle"] is True


def test_pre_tool_use_without_approval_bridge_sends_tool_start_and_asks() -> None:
    payload = {
        "hookEventName": "PreToolUse",
        "conversationId": "conv-456",
        "transcriptPath": "/logs/transcript.jsonl",
        "toolCall": {
            "id": "toolu_02",
            "name": "edit_file",
            "args": {"Path": "jules_pet/config.py"},
        },
    }

    with _MockPetServer() as server:
        proc, _ = _run_hook(payload, port=server.port, extra_env={"JULES_PET_APPROVAL_BRIDGE": "0"})
        assert proc.returncode == 0
        assert json.loads(proc.stdout.strip()) == {"decision": "ask"}

    assert len(server.messages) == 1
    msg = server.messages[0]
    assert msg["type"] == "tool_start"
    assert msg["call_id"] == "toolu_02"
    assert msg["tool"] == "edit_file"
    assert msg["category"] == "edit_write"
    assert msg["transcript_path"] == "/logs/transcript.jsonl"


@pytest.mark.parametrize(
    ("decision", "reason"),
    [
        ("allow", ""),
        ("deny", "Blocked by Jules Pet"),
    ],
)
def test_pre_tool_use_run_command_with_approval_bridge(decision: str, reason: str) -> None:
    def responder(msg: dict) -> dict:
        reply = {
            "type": "approval_response",
            "request_id": msg["request_id"],
            "decision": decision,
        }
        if reason:
            reply["reason"] = reason
        return reply

    payload = {
        "hookEventName": "PreToolUse",
        "conversationId": "conv-789",
        "transcriptPath": "/logs/transcript.jsonl",
        "toolCall": {
            "id": "toolu_03",
            "name": "run_command",
            "args": {"CommandLine": "uv run pytest"},
        },
    }

    with _MockPetServer(responder=responder) as server:
        proc, _ = _run_hook(
            payload,
            port=server.port,
            extra_env={"JULES_PET_APPROVAL_BRIDGE": "1"},
        )
        assert proc.returncode == 0
        out = json.loads(proc.stdout.strip())
        assert out["decision"] == decision
        if reason:
            assert out["reason"] == reason

    assert len(server.messages) == 1
    req = server.messages[0]
    assert req["type"] == "approval_request"
    assert req["tool"] == "run_command"
    assert req["command"] == "uv run pytest"
    assert req["request_id"]
