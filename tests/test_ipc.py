"""Headless tests for IPC protocol, QTcpServer, and TranscriptWatcher."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtNetwork import QAbstractSocket, QTcpSocket
from PySide6.QtWidgets import QApplication

from jules_pet.ipc_protocol import (
    DEFAULT_IPC_HOST,
    DEFAULT_IPC_PORT,
    categorize_tool,
    parse_ipc_message,
)
from jules_pet.ipc_server import JulesIpcServer
from jules_pet.transcript_watcher import TranscriptWatcher


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _pump_events_until(app: QApplication, predicate, timeout_ms: int = 1500) -> bool:
    """Run the Qt event loop until predicate() returns True or timeout_ms expires."""
    if predicate():
        return True
    loop = QEventLoop()
    timed_out = False

    def _on_timeout() -> None:
        nonlocal timed_out
        timed_out = True
        loop.quit()

    timeout_timer = QTimer()
    timeout_timer.setSingleShot(True)
    timeout_timer.timeout.connect(_on_timeout)
    timeout_timer.start(timeout_ms)

    poll_timer = QTimer()
    poll_timer.setInterval(10)

    def _check() -> None:
        if predicate():
            loop.quit()

    poll_timer.timeout.connect(_check)
    poll_timer.start()

    loop.exec()
    poll_timer.stop()
    timeout_timer.stop()
    return not timed_out and predicate()


def test_parse_ipc_message_valid_empty_and_malformed() -> None:
    assert DEFAULT_IPC_HOST == "127.0.0.1"
    assert DEFAULT_IPC_PORT == 18765

    parsed = parse_ipc_message('{"type": "lifecycle", "event": "SessionStart"}\n')
    assert parsed == {"type": "lifecycle", "event": "SessionStart"}

    assert parse_ipc_message("") is None
    assert parse_ipc_message("   \r\n  ") is None
    assert parse_ipc_message("{malformed json") is None
    assert parse_ipc_message('{"type": "tool_start", "truncated": ') is None
    assert parse_ipc_message("[1, 2, 3]") is None
    assert parse_ipc_message('"just a string"') is None


def test_categorize_tool_mappings() -> None:
    for tool in ("read_file", "grep_search", "find_by_name", "list_dir"):
        assert categorize_tool(tool) == "read_search"

    for tool in ("edit_file", "write_file"):
        assert categorize_tool(tool) == "edit_write"

    assert categorize_tool("run_command") == "terminal"
    assert categorize_tool("browser_click") == "browser"
    assert categorize_tool("browser_navigate") == "browser"
    assert categorize_tool("invoke_subagent") == "subagent"
    assert categorize_tool("unknown_custom_tool") == "other"
    assert categorize_tool("") == "other"


def test_ipc_server_receives_events_over_loopback_tcp(qapp: QApplication) -> None:
    server = JulesIpcServer(host="127.0.0.1", port=0)
    assert server.is_listening
    assert server.port > 0

    received: list[dict] = []
    server.event_received.connect(received.append)

    client = QTcpSocket()
    client.connectToHost("127.0.0.1", server.port)
    assert client.waitForConnected(1000)

    payload_1 = {"type": "lifecycle", "event": "PreInvocation", "conversation_id": "c-1"}
    payload_2 = {"type": "tool_start", "call_id": "t-1", "tool": "read_file"}

    # Send malformed line between valid lines, plus a message split across two writes
    part_a = (
        json.dumps(payload_1) + "\n{broken\n" + json.dumps(payload_2)[:15]
    ).encode("utf-8")
    part_b = (json.dumps(payload_2)[15:] + "\n").encode("utf-8")
    client.write(part_a)
    client.flush()
    _pump_events_until(qapp, lambda: len(received) == 1)
    client.write(part_b)
    client.flush()

    assert _pump_events_until(qapp, lambda: len(received) == 2)
    assert received == [payload_1, payload_2]

    client.disconnectFromHost()
    if client.state() != QAbstractSocket.SocketState.UnconnectedState:
        client.waitForDisconnected(500)
    server.close()


def test_ipc_server_approval_request_and_resolve(qapp: QApplication) -> None:
    server = JulesIpcServer(host="127.0.0.1", port=0)
    requests: list[tuple[str, str, str]] = []
    server.approval_requested.connect(
        lambda req_id, tool, cmd: requests.append((req_id, tool, cmd))
    )

    client = QTcpSocket()
    client.connectToHost("127.0.0.1", server.port)
    assert client.waitForConnected(1000)

    req = {
        "type": "approval_request",
        "request_id": "req-123",
        "tool": "run_command",
        "command": "uv run pytest",
        "timeout_ms": 2000,
    }
    client.write((json.dumps(req) + "\n").encode("utf-8"))
    client.flush()

    assert _pump_events_until(qapp, lambda: len(requests) == 1)
    assert requests[0] == ("req-123", "run_command", "uv run pytest")

    assert server.resolve_approval("req-123", "allow", "ok") is True
    # Resolving twice must be a safe no-op
    assert server.resolve_approval("req-123", "deny", "late") is False

    assert _pump_events_until(qapp, lambda: client.bytesAvailable() > 0)
    raw_reply = bytes(client.readAll()).decode("utf-8")
    assert raw_reply.endswith("\n")
    reply = json.loads(raw_reply.strip())
    assert reply == {
        "type": "approval_response",
        "request_id": "req-123",
        "decision": "allow",
        "reason": "ok",
    }

    client.disconnectFromHost()
    server.close()


def test_ipc_server_approval_timeout_falls_back_to_ask(qapp: QApplication) -> None:
    server = JulesIpcServer(host="127.0.0.1", port=0)
    requests: list[tuple[str, str, str]] = []
    server.approval_requested.connect(
        lambda req_id, tool, cmd: requests.append((req_id, tool, cmd))
    )

    client = QTcpSocket()
    client.connectToHost("127.0.0.1", server.port)
    assert client.waitForConnected(1000)

    req = {
        "type": "approval_request",
        "request_id": "req-timeout",
        "tool": "run_command",
        "command": "rm -rf /tmp/test",
        "timeout_ms": 80,
    }
    client.write((json.dumps(req) + "\n").encode("utf-8"))
    client.flush()

    assert _pump_events_until(qapp, lambda: len(requests) == 1)
    assert _pump_events_until(qapp, lambda: client.bytesAvailable() > 0, timeout_ms=1500)

    raw_reply = bytes(client.readAll()).decode("utf-8")
    assert raw_reply.endswith("\n")
    reply = json.loads(raw_reply.strip())
    assert reply == {
        "type": "approval_response",
        "request_id": "req-timeout",
        "decision": "ask",
        "reason": "timeout",
    }

    # Resolving after timeout must return False
    assert server.resolve_approval("req-timeout", "allow", "too late") is False

    client.disconnectFromHost()
    server.close()


def test_transcript_watcher_incremental_context_subagents_and_malformed(
    qapp: QApplication, tmp_path: Path
) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("", encoding="utf-8")

    watcher = TranscriptWatcher()
    context_events: list[tuple[int, int, float]] = []
    subagent_events: list[tuple[str, str, str, str]] = []
    watcher.context_updated.connect(
        lambda inp, cache, ratio: context_events.append((inp, cache, ratio))
    )
    watcher.subagent_event.connect(
        lambda kind, sid, role, tname: subagent_events.append((kind, sid, role, tname))
    )

    watcher.set_transcript_path(str(transcript))
    watcher.poll()
    assert context_events == []
    assert subagent_events == []

    # Append a malformed line, a PLANNER_RESPONSE with tokens + invoke_subagent
    lines_batch_1 = [
        "{corrupted json line",
        json.dumps(
            {
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "input_tokens": 120000,
                "cache_read_tokens": 80000,
                "tool_calls": [
                    {
                        "name": "invoke_subagent",
                        "args": {
                            "Role": "Codebase Researcher",
                            "TypeName": "research",
                            "conversationId": "sub-abc-1",
                        },
                    }
                ],
            }
        ),
    ]
    with transcript.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines_batch_1) + "\n")

    watcher.poll()
    assert len(context_events) == 1
    inp, cache, ratio = context_events[0]
    assert inp == 120000
    assert cache == 80000
    assert 0.0 < ratio <= 1.0

    assert subagent_events == [
        ("spawn", "sub-abc-1", "Codebase Researcher", "research")
    ]

    # Polling again without new lines should not re-emit old events
    watcher.poll()
    assert len(context_events) == 1
    assert len(subagent_events) == 1

    # Append SYSTEM_MESSAGE completion + another malformed line + second PLANNER_RESPONSE
    lines_batch_2 = [
        '{"broken": ',
        json.dumps(
            {
                "step_index": 2,
                "source": "SYSTEM",
                "type": "SYSTEM_MESSAGE",
                "status": "DONE",
                "content": (
                    "<SYSTEM_MESSAGE>\n"
                    "[Message] timestamp=2026-11-24T16:15:00Z "
                    "sender=sub-abc-1 priority=MESSAGE_PRIORITY_HIGH content=Done\n"
                    "</SYSTEM_MESSAGE>"
                ),
            }
        ),
        json.dumps(
            {
                "step_index": 3,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "input_tokens": 150000,
                "cache_read_tokens": 100000,
                "tool_calls": [],
            }
        ),
    ]
    with transcript.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines_batch_2) + "\n")

    watcher.poll()
    assert len(context_events) == 2
    assert context_events[1][0] == 150000
    assert context_events[1][1] == 100000
    assert context_events[1][2] > context_events[0][2]

    assert subagent_events == [
        ("spawn", "sub-abc-1", "Codebase Researcher", "research"),
        ("done", "sub-abc-1", "Codebase Researcher", "research"),
    ]


def test_transcript_watcher_correlates_generic_result_conversation_id(
    qapp: QApplication, tmp_path: Path
) -> None:
    transcript = tmp_path / "real_style.jsonl"
    watcher = TranscriptWatcher(context_window=200_000)
    subagent_events: list[tuple[str, str, str, str]] = []
    watcher.subagent_event.connect(
        lambda kind, sid, role, tname: subagent_events.append((kind, sid, role, tname))
    )

    lines = [
        json.dumps(
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "input_tokens": 50000,
                "cache_read_tokens": 50000,
                "tool_calls": [
                    {
                        "name": "invoke_subagent",
                        "args": {
                            "Role": '"Test Runner"',
                            "TypeName": '"self"',
                        },
                    }
                ],
            }
        ),
        json.dumps(
            {
                "step_index": 2,
                "type": "GENERIC",
                "content": "Subagent launched with conversationId: 99aabbcc-1122-3344",
            }
        ),
        json.dumps(
            {
                "step_index": 3,
                "type": "SYSTEM_MESSAGE",
                "content": "[Message] sender=99aabbcc-1122-3344 content=All done",
            }
        ),
    ]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    watcher.set_transcript_path(str(transcript))
    watcher.poll()

    assert subagent_events == [
        ("spawn", "99aabbcc-1122-3344", "Test Runner", "self"),
        ("done", "99aabbcc-1122-3344", "Test Runner", "self"),
    ]
