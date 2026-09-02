"""Native i3 IPC over its unix socket. Stdlib only."""

from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import threading
import time
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

# A frame whose type has the high bit set is an event, not a reply; the low
# bits are the event number (3 = window).
EVENT_MASK = 0x80000000
EVENT_WINDOW = 3


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


def _recv_exactly(sock, count: int) -> bytes:
    buf = b""
    while len(buf) < count:
        chunk = sock.recv(count - len(buf))
        if not chunk:
            raise I3Error("i3 closed the IPC connection")
        buf += chunk
    return buf


def _read_frame(sock) -> tuple[int, Any]:
    """Read one i3 frame: the 14-byte header, then its JSON payload."""
    header = _recv_exactly(sock, HEADER_LEN)
    if header[:6] != MAGIC:
        raise I3Error("Malformed IPC reply header from i3")
    length, msg_type = struct.unpack("=II", header[6:HEADER_LEN])
    return msg_type, json.loads(_recv_exactly(sock, length))


def _send_frame(sock, msg_type: int, payload: str) -> None:
    body = payload.encode()
    sock.sendall(MAGIC + struct.pack("=II", len(body), msg_type) + body)


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

    def _request_once(self, msg_type: int, payload: str) -> Any:
        sock = self._connect()
        _send_frame(sock, msg_type, payload)
        _reply_type, reply = _read_frame(sock)
        return reply

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


class EventStream:
    """A second socket, subscribed to i3 events.

    Events must never share the command connection: they would interleave with
    replies and desynchronise it. Reads are bounded by `next_event`'s timeout;
    a timeout mid-frame leaves the stream unusable, so close it afterwards.
    """

    def __init__(self, sock):
        self._sock = sock

    def handshake(self, events: list[str]) -> None:
        """Send SUBSCRIBE for these event names and check i3 accepted it."""
        self._sock.settimeout(5)
        _send_frame(self._sock, SUBSCRIBE, json.dumps(events))
        _msg_type, reply = _read_frame(self._sock)
        if not (isinstance(reply, dict) and reply.get("success")):
            raise I3Error(f"i3 refused the event subscription for {events}")

    def next_event(self, timeout: float) -> Any | None:
        """Return the next event payload, or None if none arrives in time."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self._sock.settimeout(remaining)
            try:
                msg_type, payload = _read_frame(self._sock)
            except (socket.timeout, TimeoutError):
                return None
            if msg_type & EVENT_MASK:
                return payload

    def close(self) -> None:
        self._sock.close()

    def __enter__(self) -> "EventStream":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def subscribe(events: list[str], socket_path: str | None = None) -> EventStream:
    """Open a fresh socket subscribed to these i3 events."""
    path = socket_path or find_socket_path()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect(path)
    except OSError as exc:
        sock.close()
        raise I3Error(f"Cannot connect to i3 at {path}: {exc}") from exc
    stream = EventStream(sock)
    try:
        stream.handshake(events)
    except (OSError, I3Error):
        stream.close()
        raise
    return stream


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
