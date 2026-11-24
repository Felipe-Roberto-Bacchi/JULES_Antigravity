"""Loopback QTcpServer for receiving hook events and resolving tool approvals."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QTcpServer, QTcpSocket

from jules_pet.ipc_protocol import (
    DEFAULT_APPROVAL_TIMEOUT_MS,
    DEFAULT_IPC_HOST,
    DEFAULT_IPC_PORT,
    encode_ipc_message,
    parse_ipc_message,
)


class JulesIpcServer(QObject):
    """Local JSON-Lines TCP server for Antigravity hook communication."""

    event_received = Signal(dict)
    approval_requested = Signal(str, str, str)

    def __init__(
        self,
        host: str = DEFAULT_IPC_HOST,
        port: int = DEFAULT_IPC_PORT,
        parent: QObject | None = None,
        *,
        auto_start: bool = True,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._port = port
        self._server = QTcpServer(self)
        self._server.newConnection.connect(self._on_new_connection)

        self._buffers: dict[QTcpSocket, bytearray] = {}
        self._pending_approvals: dict[str, tuple[QTcpSocket, QTimer]] = {}
        self._timer_to_request: dict[QTimer, str] = {}

        if auto_start:
            self.start()

    @property
    def is_listening(self) -> bool:
        return bool(self._server.isListening())

    @property
    def port(self) -> int:
        return int(self._server.serverPort())

    def start(self) -> bool:
        """Start listening on the configured host and port."""
        if self._server.isListening():
            return True
        return bool(self._server.listen(QHostAddress(self._host), self._port))

    def close(self) -> None:
        """Stop all pending approval timers, disconnect clients, and close the server."""
        for request_id in list(self._pending_approvals.keys()):
            _, timer = self._pending_approvals.pop(request_id)
            self._timer_to_request.pop(timer, None)
            timer.stop()

        for sock in list(self._buffers.keys()):
            self._buffers.pop(sock, None)
            sock.blockSignals(True)
            sock.abort()

        self._server.close()

    def resolve_approval(self, request_id: str, decision: str, reason: str = "") -> bool:
        """Send an approval_response back to the waiting hook client."""
        entry = self._pending_approvals.pop(request_id, None)
        if entry is None:
            return False

        sock, timer = entry
        self._timer_to_request.pop(timer, None)
        timer.stop()

        response = {
            "type": "approval_response",
            "request_id": request_id,
            "decision": decision,
            "reason": reason,
        }
        if sock.state() == QAbstractSocket.SocketState.ConnectedState or sock.isOpen():
            sock.write(encode_ipc_message(response))
            sock.flush()
        return True

    @Slot()
    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            if sock is None:
                continue
            self._buffers[sock] = bytearray()
            sock.readyRead.connect(self._on_ready_read)
            sock.disconnected.connect(self._on_disconnected)

    @Slot()
    def _on_ready_read(self) -> None:
        sock = self.sender()
        if not isinstance(sock, QTcpSocket):
            return
        buf = self._buffers.get(sock)
        if buf is None:
            return
        buf.extend(bytes(sock.readAll()))

        while b"\n" in buf:
            newline_idx = buf.index(b"\n")
            raw_line = bytes(buf[:newline_idx])
            del buf[: newline_idx + 1]

            msg = parse_ipc_message(raw_line)
            if msg is not None:
                self._dispatch_message(sock, msg)

    def _dispatch_message(self, sock: QTcpSocket, msg: dict[str, Any]) -> None:
        self.event_received.emit(msg)

        if msg.get("type") != "approval_request":
            return

        request_id = str(msg.get("request_id") or "")
        if not request_id:
            return

        tool = str(msg.get("tool") or "")
        command = str(msg.get("command") or "")

        raw_timeout = msg.get("timeout_ms", DEFAULT_APPROVAL_TIMEOUT_MS)
        try:
            timeout_ms = max(1, int(raw_timeout))
        except (TypeError, ValueError):
            timeout_ms = DEFAULT_APPROVAL_TIMEOUT_MS

        # Replace any stale timer for the same request_id
        previous = self._pending_approvals.pop(request_id, None)
        if previous is not None:
            _, prev_timer = previous
            self._timer_to_request.pop(prev_timer, None)
            prev_timer.stop()

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._on_approval_timeout)
        self._pending_approvals[request_id] = (sock, timer)
        self._timer_to_request[timer] = request_id
        timer.start(timeout_ms)

        self.approval_requested.emit(request_id, tool, command)

    @Slot()
    def _on_approval_timeout(self) -> None:
        timer = self.sender()
        if not isinstance(timer, QTimer):
            return
        request_id = self._timer_to_request.pop(timer, None)
        if request_id is not None:
            self.resolve_approval(request_id, "ask", "timeout")

    @Slot()
    def _on_disconnected(self) -> None:
        sock = self.sender()
        if not isinstance(sock, QTcpSocket):
            return
        self._buffers.pop(sock, None)
        for request_id in [
            rid for rid, (pending_sock, _) in self._pending_approvals.items() if pending_sock is sock
        ]:
            _, timer = self._pending_approvals.pop(request_id)
            self._timer_to_request.pop(timer, None)
            timer.stop()
        sock.deleteLater()
