import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from i3mcp import ipc
from tests.conftest import call


async def test_exec_uses_no_startup_id(fake):
    await call("i3_wm", action="exec", command="firefox")
    assert fake.last_command == 'exec --no-startup-id "firefox"'


async def test_exec_on_a_workspace_switches_first(fake):
    await call("i3_wm", action="exec", command="firefox", workspace="web")
    assert fake.last_command == 'workspace "web"; exec --no-startup-id "firefox"'


async def test_exec_quotes_a_command_with_semicolons(fake):
    await call("i3_wm", action="exec", command='sh -c "echo a; echo b"')
    assert fake.last_command == 'exec --no-startup-id "sh -c \\"echo a; echo b\\""'


async def test_exec_quotes_a_command_with_a_comma(fake):
    await call("i3_wm", action="exec", command="true, true")
    assert fake.last_command == 'exec --no-startup-id "true, true"'


async def test_reload(fake):
    await call("i3_wm", action="reload")
    assert fake.last_command == "reload"


async def test_restart(fake):
    await call("i3_wm", action="restart")
    assert fake.last_command == "restart"


async def test_mode(fake):
    await call("i3_wm", action="mode", mode_name="resize")
    assert fake.last_command == 'mode "resize"'


async def test_nop(fake):
    await call("i3_wm", action="nop", comment="marker")
    assert fake.last_command == 'nop "marker"'


async def test_shmlog_on(fake):
    await call("i3_wm", action="shmlog", toggle="on")
    assert fake.last_command == "shmlog on"


async def test_debuglog_off(fake):
    await call("i3_wm", action="debuglog", toggle="off")
    assert fake.last_command == "debuglog off"


async def test_debuglog_toggle(fake):
    await call("i3_wm", action="debuglog", toggle="toggle")
    assert fake.last_command == "debuglog toggle"


async def test_append_layout(fake):
    await call("i3_wm", action="append_layout", path="/home/u/layout.json")
    assert fake.last_command == 'append_layout "/home/u/layout.json"'


async def test_exec_requires_a_command(fake):
    result = json.loads(await call("i3_wm", action="exec"))
    assert result["success"] is False
    assert fake.commands == []


async def test_mode_requires_a_name(fake):
    result = json.loads(await call("i3_wm", action="mode"))
    assert result["success"] is False
    assert fake.commands == []


async def test_exit_is_not_an_allowed_action(fake):
    """Terminating the session must not be reachable through a tool call."""
    import inspect

    from i3mcp.tools import wm

    assert "exit" not in str(inspect.signature(wm.i3_wm))


class FakeEventStream:
    """Stands in for ipc.EventStream, yielding canned payloads then timing out."""

    def __init__(self, events, log):
        self.events = list(events)
        self.timeouts: list[float] = []
        self.closed = False
        log.append("subscribe")

    def next_event(self, timeout):
        self.timeouts.append(timeout)
        return self.events.pop(0) if self.events else None

    def close(self):
        self.closed = True


def _stream(monkeypatch, fake, events):
    """Wire a FakeEventStream in and record the order of subscribe vs. command."""
    log: list[str] = []
    streams: list[FakeEventStream] = []
    plain_command = fake.command

    def command(cmd):
        log.append("command")
        return plain_command(cmd)

    monkeypatch.setattr(fake, "command", command)

    def subscribe(event_names):
        assert event_names == ["window"]
        stream = FakeEventStream(events, log)
        streams.append(stream)
        return stream

    monkeypatch.setattr(ipc, "subscribe", subscribe)
    return log, streams


NEW_WINDOW = {
    "change": "new",
    "container": {
        "id": 94208,
        "window": 39845889,
        "name": "probe",
        "output": "OUT-1",
        "floating": "auto_off",
        "marks": [],
        "window_type": "normal",
        "window_properties": {"class": "XTerm", "instance": "xterm"},
        "rect": {"x": 0, "y": 0, "width": 800, "height": 600},
    },
}


async def test_exec_with_wait_returns_the_new_window(fake, monkeypatch):
    _stream(monkeypatch, fake, [{"change": "focus", "container": {"id": 1}}, NEW_WINDOW])
    result = json.loads(await call("i3_wm", action="exec", command="xterm", wait_seconds=2))
    assert result["success"] is True
    assert result["window"]["con_id"] == 94208
    assert result["window"]["window_class"] == "XTerm"
    assert result["window"]["name"] == "probe"
    assert result["waited_seconds"] >= 0
    assert fake.last_command == 'exec --no-startup-id "xterm"'


async def test_exec_with_wait_returns_a_compact_record(fake, monkeypatch):
    """The event container carries no workspace, so those keys stay out."""
    _stream(monkeypatch, fake, [NEW_WINDOW])
    result = json.loads(await call("i3_wm", action="exec", command="xterm", wait_seconds=2))
    assert "workspace" not in result["window"]
    assert "floating" not in result["window"]
    assert "parent_layout" not in result["window"]


async def test_exec_subscribes_before_running_the_command(fake, monkeypatch):
    log, _ = _stream(monkeypatch, fake, [NEW_WINDOW])
    await call("i3_wm", action="exec", command="xterm", wait_seconds=2)
    assert log == ["subscribe", "command"]


async def test_exec_with_wait_reports_a_timeout(fake, monkeypatch):
    _stream(monkeypatch, fake, [])
    result = json.loads(await call("i3_wm", action="exec", command="xterm", wait_seconds=0.2))
    assert result["success"] is True
    assert result["window"] is None
    assert result["timed_out"] is True
    assert "i3_query" in result["hint"]


async def test_exec_with_wait_closes_the_stream(fake, monkeypatch):
    _, streams = _stream(monkeypatch, fake, [NEW_WINDOW])
    await call("i3_wm", action="exec", command="xterm", wait_seconds=2)
    assert streams[0].closed is True


async def test_exec_with_wait_closes_the_stream_when_the_command_fails(fake, monkeypatch):
    _, streams = _stream(monkeypatch, fake, [NEW_WINDOW])
    fake.command_replies = [[{"success": False, "error": "no such command"}]]
    result = json.loads(await call("i3_wm", action="exec", command="xterm", wait_seconds=2))
    assert result["success"] is False
    assert result["command"] == 'exec --no-startup-id "xterm"'
    assert streams[0].closed is True


async def test_exec_without_wait_never_subscribes(fake, monkeypatch):
    log, streams = _stream(monkeypatch, fake, [NEW_WINDOW])
    result = json.loads(await call("i3_wm", action="exec", command="xterm"))
    assert log == ["command"]
    assert streams == []
    assert "window" not in result


@pytest.mark.parametrize("value", [0.05, 61])
async def test_wait_seconds_out_of_range_is_rejected(fake, value):
    with pytest.raises(ToolError):
        await call("i3_wm", action="exec", command="xterm", wait_seconds=value)
    assert fake.commands == []


async def test_nop_quotes_a_comment_with_a_semicolon(fake):
    await call("i3_wm", action="nop", comment="hello; nop injected")
    assert fake.last_command == 'nop "hello; nop injected"'


class FakeClock:
    """A monotonic clock the test moves by hand, standing in for the time module."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now


async def test_wait_budget_starts_after_the_subscribe_handshake(fake, monkeypatch):
    """Opening the event socket is a round-trip to i3; it must not eat wait_seconds."""
    from i3mcp.tools import wm

    clock = FakeClock()
    monkeypatch.setattr(wm, "time", clock)
    streams: list[FakeEventStream] = []

    def subscribe(event_names):
        clock.now += 1.0
        stream = FakeEventStream([], [])
        streams.append(stream)
        return stream

    monkeypatch.setattr(ipc, "subscribe", subscribe)
    result = json.loads(await call("i3_wm", action="exec", command="xterm", wait_seconds=0.5))
    assert result["timed_out"] is True
    assert streams[0].timeouts == [0.5]


async def test_wait_timeouts_shrink_across_events(fake, monkeypatch):
    _, streams = _stream(monkeypatch, fake, [{"change": "focus", "container": {"id": 1}}, NEW_WINDOW])
    await call("i3_wm", action="exec", command="xterm", wait_seconds=2)
    timeouts = streams[0].timeouts
    assert len(timeouts) == 2
    assert all(timeout > 0 for timeout in timeouts)
    assert timeouts[1] < timeouts[0]


async def test_exec_reports_a_refused_subscription_and_sends_no_command(fake, monkeypatch):
    def subscribe(event_names):
        raise ipc.I3Error("i3 refused the event subscription for ['window']")

    monkeypatch.setattr(ipc, "subscribe", subscribe)
    result = json.loads(await call("i3_wm", action="exec", command="xterm", wait_seconds=2))
    assert result["success"] is False
    assert "Cannot subscribe to i3 events" in result["error"]
    assert result["command"] == 'exec --no-startup-id "xterm"'
    assert fake.commands == []


async def test_exec_reports_an_oserror_from_the_subscribe_handshake(fake, monkeypatch):
    def subscribe(event_names):
        raise OSError("connection reset by peer")

    monkeypatch.setattr(ipc, "subscribe", subscribe)
    result = json.loads(await call("i3_wm", action="exec", command="xterm", wait_seconds=2))
    assert result["success"] is False
    assert "Cannot subscribe to i3 events" in result["error"]
    assert fake.commands == []


OTHER_WINDOW = {
    "change": "new",
    "container": {"id": 555, "window": 777, "name": "popup", "window_properties": {"class": "Other"}},
}


async def test_wait_match_skips_unrelated_new_windows(fake, monkeypatch):
    # Another app's popup can open in the same instant as the launched window.
    _stream(monkeypatch, fake, [OTHER_WINDOW, NEW_WINDOW])
    result = json.loads(
        await call("i3_wm", action="exec", command="xterm", wait_seconds=2, wait_match="xterm")
    )
    assert result["window"]["con_id"] == 94208


async def test_wait_match_also_matches_the_title(fake, monkeypatch):
    _stream(monkeypatch, fake, [OTHER_WINDOW, NEW_WINDOW])
    result = json.loads(
        await call("i3_wm", action="exec", command="xterm", wait_seconds=2, wait_match="PROBE")
    )
    assert result["window"]["con_id"] == 94208


async def test_wait_match_with_no_match_times_out(fake, monkeypatch):
    _stream(monkeypatch, fake, [OTHER_WINDOW])
    result = json.loads(
        await call("i3_wm", action="exec", command="xterm", wait_seconds=0.5, wait_match="xterm")
    )
    assert result["timed_out"] is True
