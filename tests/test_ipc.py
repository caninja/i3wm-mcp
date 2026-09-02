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
