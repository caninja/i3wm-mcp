"""Native i3 IPC over its unix socket. Stdlib only."""

from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import threading
from typing import Any

MAGIC = b"i3-ipc"
HEADER_LEN = 14

RUN_COMMAND = 0
GET_WORKSPACES = 1
SUBSCRIBE = 2
GET_OUTPUTS = 3
GET_TREE = 4
GET_MARKS = 5
GET_BAR_CONFIG = 6
GET_VERSION = 7
GET_BINDING_MODES = 8
GET_CONFIG = 9
SEND_TICK = 10
SYNC = 11
GET_BINDING_STATE = 12


class I3Error(Exception):
    """An i3 command or query failed. Carries i3's own reply for detail."""

    def __init__(self, message: str, replies: list[dict] | None = None):
        super().__init__(message)
        self.message = message
        self.replies = replies


def find_socket_path() -> str:
    path = os.environ.get("I3SOCK")
    if path:
        return path
    try:
        result = subprocess.run(
            ["i3", "--get-socketpath"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise I3Error(f"Cannot locate the i3 IPC socket: {exc}") from exc
    path = result.stdout.strip()
    if not path:
        raise I3Error("i3 --get-socketpath returned nothing; is i3 running?")
    return path


class I3Connection:
    """A single reconnecting connection to i3's IPC socket."""

    def __init__(self, socket_path: str | None = None):
        self._socket_path = socket_path
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()

    @property
    def socket_path(self) -> str:
        if self._socket_path is None:
            self._socket_path = find_socket_path()
        return self._socket_path

    def _connect(self) -> socket.socket:
        if self._sock is None:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(5)
            try:
                sock.connect(self.socket_path)
            except OSError as exc:
                raise I3Error(f"Cannot connect to i3 at {self.socket_path}: {exc}") from exc
            self._sock = sock
        return self._sock

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def _recv_exactly(self, sock: socket.socket, count: int) -> bytes:
        buf = b""
        while len(buf) < count:
            chunk = sock.recv(count - len(buf))
            if not chunk:
                raise I3Error("i3 closed the IPC connection")
            buf += chunk
        return buf

    def _request_once(self, msg_type: int, payload: str) -> Any:
        sock = self._connect()
        body = payload.encode()
        sock.sendall(MAGIC + struct.pack("=II", len(body), msg_type) + body)
        header = self._recv_exactly(sock, HEADER_LEN)
        if header[:6] != MAGIC:
            raise I3Error("Malformed IPC reply header from i3")
        length, _reply_type = struct.unpack("=II", header[6:HEADER_LEN])
        return json.loads(self._recv_exactly(sock, length))

    def request(self, msg_type: int, payload: str = "") -> Any:
        """Send one message, retrying once on a dropped connection."""
        with self._lock:
            try:
                return self._request_once(msg_type, payload)
            except (OSError, I3Error):
                self.close()
                return self._request_once(msg_type, payload)

    def query(self, msg_type: int, payload: str = "") -> Any:
        return self.request(msg_type, payload)

    def command(self, cmd: str) -> list[dict]:
        """Run an i3 command. Raises I3Error if any sub-command failed."""
        replies = self.request(RUN_COMMAND, cmd)
        if not isinstance(replies, list):
            replies = [replies]
        failed = [r for r in replies if not r.get("success")]
        if failed:
            first = failed[0]
            detail = first.get("error", "i3 rejected the command")
            if first.get("errorposition"):
                detail = f"{detail}\n  {cmd}\n  {first['errorposition']}"
            raise I3Error(detail, replies=replies)
        return replies


_connection: I3Connection | None = None


def get_connection() -> I3Connection:
    global _connection
    if _connection is None:
        _connection = I3Connection()
    return _connection


def set_connection(conn) -> None:
    """Test seam. Pass None to reset to a real connection."""
    global _connection
    _connection = conn
