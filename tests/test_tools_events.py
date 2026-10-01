import json
import threading

import pytest

from i3mcp import events, ipc
from tests.conftest import call
from tests.test_events import window_event


@pytest.fixture
def log():
    log = events.EventLog()
    log.connected = True
    events.set_log(log)
    yield log
    events.set_log(None)


async def test_events_returns_recent_events_and_a_cursor(log):
    log.ingest(*window_event("new"))
    result = json.loads(await call("i3_events"))
    assert result["success"] is True
    assert result["cursor"] == 1
    assert result["events"][0]["window"]["con_id"] == 1001


async def test_events_since_and_filters(log):
    log.ingest(*window_event("new"))
    log.ingest(*window_event("close"))
    result = json.loads(await call("i3_events", since=1, change="close"))
    assert [e["seq"] for e in result["events"]] == [2]


async def test_events_wait_blocks_until_one_arrives(log):
    threading.Timer(0.05, lambda: log.ingest(*window_event("urgent"))).start()
    result = json.loads(await call("i3_events", wait_seconds=2, change="urgent"))
    assert [e["change"] for e in result["events"]] == ["urgent"]


async def test_events_wait_times_out(log):
    result = json.loads(await call("i3_events", wait_seconds=0.1))
    assert result["timed_out"] is True


async def test_events_reports_a_disconnected_watcher(log, monkeypatch):
    monkeypatch.setattr("i3mcp.tools.events.CONNECT_GRACE", 0.01)
    log.connected = False
    log.last_error = "Cannot connect to i3"
    result = json.loads(await call("i3_events"))
    assert result["success"] is False
    assert "Cannot connect to i3" in result["error"]
