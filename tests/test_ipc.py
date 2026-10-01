import json
import socket
import struct
import threading

import pytest

from i3mcp import ipc


def _serve(srv, replies):
    """Minimal fake i3: accepts one connection, answers each request in order."""
    conn, _ = srv.accept()
    for reply in replies:
        header = b""
        while len(header) < 14:
            header += conn.recv(14 - len(header))
        length, msg_type = struct.unpack("=II", header[6:14])
        body = b""
        while len(body) < length:
            body += conn.recv(length - len(body))
        payload = json.dumps(reply).encode()
        conn.sendall(b"i3-ipc" + struct.pack("=II", len(payload), msg_type) + payload)
    conn.close()
    srv.close()


@pytest.fixture
def fake_i3(tmp_path):
    # Bind and listen here, on the main thread, before returning the path,
    # so a client connecting immediately after start() is guaranteed a
    # listening socket. Binding inside the server thread races the client.
    sock_path = str(tmp_path / "ipc.sock")

    def start(replies):
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(sock_path)
        srv.listen(1)
        thread = threading.Thread(target=_serve, args=(srv, replies), daemon=True)
        thread.start()
        return sock_path

    return start


def test_query_roundtrip(fake_i3):
    path = fake_i3([{"human_readable": "4.25.1"}])
    conn = ipc.I3Connection(socket_path=path)
    assert conn.query(ipc.GET_VERSION)["human_readable"] == "4.25.1"
    conn.close()


def test_command_success_returns_replies(fake_i3):
    path = fake_i3([[{"success": True}]])
    conn = ipc.I3Connection(socket_path=path)
    assert conn.command("nop hello") == [{"success": True}]
    conn.close()


def test_command_failure_raises_with_i3_error_detail(fake_i3):
    path = fake_i3([[{
        "success": False,
        "parse_error": True,
        "error": "Expected one of these tokens: 'current', 'all'",
        "errorposition": "  ^^^^",
    }]])
    conn = ipc.I3Connection(socket_path=path)
    with pytest.raises(ipc.I3Error) as excinfo:
        conn.command("gaps inner workspace set 10")
    assert "current" in str(excinfo.value)
    assert excinfo.value.replies[0]["parse_error"] is True
    conn.close()


def test_partial_failure_in_multi_reply_raises(fake_i3):
    """RUN_COMMAND returns one reply per sub-command; any failure is a failure."""
    path = fake_i3([[{"success": True}, {"success": False, "error": "nope"}]])
    conn = ipc.I3Connection(socket_path=path)
    with pytest.raises(ipc.I3Error):
        conn.command("floating enable, resize set 800 600")
    conn.close()


class FakeSocket:
    """Hands out canned bytes; raises socket.timeout once the script is empty."""

    def __init__(self, data: bytes):
        self.data = data
        self.sent = b""
        self.timeouts: list[float] = []
        self.closed = False

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def sendall(self, payload):
        self.sent += payload

    def recv(self, count):
        if not self.data:
            raise socket.timeout("timed out")
        chunk, self.data = self.data[:count], self.data[count:]
        return chunk

    def shutdown(self, how):
        self.shut_down = how

    def close(self):
        self.closed = True


def _frame(msg_type: int, payload) -> bytes:
    body = json.dumps(payload).encode()
    return b"i3-ipc" + struct.pack("=II", len(body), msg_type) + body


def test_next_event_decodes_an_event_frame():
    """Window events arrive with the high bit set on the reply type."""
    event = {"change": "new", "container": {"id": 94, "name": "probe"}}
    sock = FakeSocket(_frame(ipc.EVENT_MASK | ipc.EVENT_WINDOW, event))
    stream = ipc.EventStream(sock)
    assert stream.next_event(1.0) == event


def test_next_event_returns_none_on_timeout():
    stream = ipc.EventStream(FakeSocket(b""))
    assert stream.next_event(0.05) is None


def test_next_event_skips_a_non_event_frame():
    """A reply frame left on the wire must not be mistaken for an event."""
    event = {"change": "new", "container": {"id": 7}}
    frames = _frame(ipc.RUN_COMMAND, [{"success": True}]) + _frame(0x80000003, event)
    sock = FakeSocket(frames)
    stream = ipc.EventStream(sock)
    assert stream.next_event(1.0) == event


def test_read_event_blocks_without_a_timeout_and_names_the_event():
    event = {"change": "focus", "current": {"name": "2"}}
    frames = _frame(ipc.RUN_COMMAND, [{"success": True}]) + _frame(ipc.EVENT_MASK | ipc.EVENT_WORKSPACE, event)
    sock = FakeSocket(frames)
    assert ipc.EventStream(sock).read_event() == (ipc.EVENT_WORKSPACE, event)
    assert sock.timeouts == [None]


def test_event_stream_handshake_sends_the_event_list():
    sock = FakeSocket(_frame(ipc.SUBSCRIBE, {"success": True}))
    stream = ipc.EventStream(sock)
    stream.handshake(["window"])
    assert sock.sent == b"i3-ipc" + struct.pack("=II", 10, ipc.SUBSCRIBE) + b'["window"]'


def test_event_stream_handshake_rejects_a_refusal():
    sock = FakeSocket(_frame(ipc.SUBSCRIBE, {"success": False}))
    with pytest.raises(ipc.I3Error):
        ipc.EventStream(sock).handshake(["window"])


def test_event_stream_closes_its_own_socket():
    sock = FakeSocket(b"")
    with ipc.EventStream(sock) as stream:
        assert stream is not None
    assert sock.closed is True
    assert sock.shut_down == socket.SHUT_RDWR


def _serve_event(srv, event):
    """Fake i3 event socket: answer SUBSCRIBE, then push one window event."""
    conn, _ = srv.accept()
    header = b""
    while len(header) < 14:
        header += conn.recv(14 - len(header))
    length, _msg_type = struct.unpack("=II", header[6:14])
    body = b""
    while len(body) < length:
        body += conn.recv(length - len(body))
    conn.sendall(_frame(2, {"success": True}))
    conn.sendall(_frame(0x80000003, event))
    conn.close()
    srv.close()


def test_subscribe_opens_its_own_socket_and_reads_an_event(tmp_path):
    sock_path = str(tmp_path / "event.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)
    event = {"change": "new", "container": {"id": 12, "name": "probe"}}
    threading.Thread(target=_serve_event, args=(srv, event), daemon=True).start()
    with ipc.subscribe(["window"], socket_path=sock_path) as stream:
        assert stream.next_event(2.0) == event


def test_subscribe_reuses_the_command_connections_socket_path(tmp_path, monkeypatch):
    """Re-resolving the path forks `i3 --get-socketpath`; the connection knows it."""
    sock_path = str(tmp_path / "event.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)
    event = {"change": "new", "container": {"id": 12, "name": "probe"}}
    threading.Thread(target=_serve_event, args=(srv, event), daemon=True).start()

    def no_lookup():
        raise AssertionError("subscribe must not re-resolve the socket path")

    monkeypatch.setattr(ipc, "find_socket_path", no_lookup)
    ipc.set_connection(ipc.I3Connection(socket_path=sock_path))
    try:
        with ipc.subscribe(["window"]) as stream:
            assert stream.next_event(2.0) == event
    finally:
        ipc.set_connection(None)
