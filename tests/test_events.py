"""The background event log, driven without i3."""

import queue
import threading
import time

from i3mcp import events, ipc
from i3mcp.ipc import I3Error


def window_event(change: str, con_id: int = 1001, name: str = "alpha one", cls: str = "Alpha") -> tuple:
    container = {"id": con_id, "name": name, "window_properties": {"class": cls}, "marks": [], "urgent": False}
    return ipc.EVENT_WINDOW, {"change": change, "container": container}


def workspace_event(change: str, current: str, old: str | None = None) -> tuple:
    payload = {"change": change, "current": {"name": current}, "old": {"name": old} if old else None}
    return ipc.EVENT_WORKSPACE, payload


def test_window_events_are_shaped_compactly():
    log = events.EventLog()
    log.ingest(*window_event("new"))
    [entry] = log.read()["events"]
    assert entry["seq"] == 1
    assert entry["event"] == "window"
    assert entry["change"] == "new"
    assert entry["window"] == {"con_id": 1001, "name": "alpha one", "window_class": "Alpha"}
    assert isinstance(entry["ago"], float)


def test_workspace_and_mode_events_name_what_changed():
    log = events.EventLog()
    log.ingest(*workspace_event("focus", "2", "1"))
    log.ingest(ipc.EVENT_MODE, {"change": "resize", "pango_markup": False})
    ws, mode = log.read()["events"]
    assert (ws["current"], ws["old"]) == ("2", "1")
    assert mode == {"seq": 2, "event": "mode", "change": "resize", "ago": mode["ago"]}


def test_unknown_event_numbers_are_ignored():
    log = events.EventLog()
    log.ingest(5, {"change": "run"})  # binding events are not subscribed to
    assert log.read() == {"events": [], "cursor": 0}


def test_since_returns_only_newer_events_and_the_cursor():
    log = events.EventLog()
    for change in ("new", "focus", "title"):
        log.ingest(*window_event(change))
    first = log.read()
    assert first["cursor"] == 3
    log.ingest(*window_event("close"))
    later = log.read(since=first["cursor"])
    assert [e["change"] for e in later["events"]] == ["close"]
    assert later["cursor"] == 4


def test_filters_by_event_change_class_title_and_con_id():
    log = events.EventLog()
    log.ingest(*window_event("new", 1, "editor", "Edit"))
    log.ingest(*window_event("urgent", 2, "chat", "Talk"))
    log.ingest(*workspace_event("focus", "2"))
    assert [e["seq"] for e in log.read(filters={"event": "workspace"})["events"]] == [3]
    assert [e["seq"] for e in log.read(filters={"change": "urgent"})["events"]] == [2]
    assert [e["seq"] for e in log.read(filters={"window_class": "talk"})["events"]] == [2]
    assert [e["seq"] for e in log.read(filters={"title": "EDIT"})["events"]] == [1]
    assert [e["seq"] for e in log.read(filters={"con_id": 1})["events"]] == [1]


def test_a_cursor_older_than_the_buffer_reports_dropped():
    log = events.EventLog(maxlen=2)
    for change in ("new", "focus", "title", "close"):
        log.ingest(*window_event(change))
    result = log.read(since=1)
    assert result["dropped"] is True
    assert [e["seq"] for e in result["events"]] == [3, 4]


def test_a_long_backlog_is_paged_by_the_cursor():
    log = events.EventLog()
    for _ in range(events.PAGE + 5):
        log.ingest(*window_event("title"))
    page = log.read(since=0)
    assert len(page["events"]) == events.PAGE
    assert page["more"] is True
    assert page["cursor"] == events.PAGE
    rest = log.read(since=page["cursor"])
    assert len(rest["events"]) == 5 and "more" not in rest


def test_without_since_only_the_latest_page_is_returned():
    log = events.EventLog()
    for _ in range(events.PAGE + 5):
        log.ingest(*window_event("title"))
    result = log.read()
    assert result["events"][0]["seq"] == 6
    assert result["cursor"] == events.PAGE + 5


def test_wait_wakes_when_a_matching_event_arrives():
    log = events.EventLog()
    log.ingest(*window_event("focus"))
    timer = threading.Timer(0.05, lambda: log.ingest(*window_event("urgent")))
    timer.start()
    started = time.monotonic()
    result = log.wait(timeout=2, filters={"change": "urgent"})
    assert time.monotonic() - started < 1
    assert [e["change"] for e in result["events"]] == ["urgent"]


def test_wait_times_out_with_no_events():
    log = events.EventLog()
    result = log.wait(timeout=0.05)
    assert result["events"] == []
    assert result["timed_out"] is True


def test_wait_returns_at_once_when_since_already_has_matches():
    log = events.EventLog()
    log.ingest(*window_event("new"))
    result = log.wait(since=0, timeout=5)
    assert [e["seq"] for e in result["events"]] == [1]


class FakeStream:
    """read_event blocks on a queue; close() makes it raise, like a closed socket."""

    def __init__(self, items):
        self.items = queue.Queue()
        for item in items:
            self.items.put(item)

    def read_event(self):
        item = self.items.get()
        if item is None:
            raise I3Error("i3 closed the IPC connection")
        return item

    def close(self):
        self.items.put(None)


def wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition never became true")
        time.sleep(0.01)


def test_watcher_thread_logs_events_and_marks_a_reconnect():
    streams = [FakeStream([window_event("new"), None]), FakeStream([window_event("close")])]
    log = events.EventLog(stream_factory=lambda: streams.pop(0), backoff=0.01)
    log.start()
    try:
        wait_for(lambda: log.read()["cursor"] == 3)
        changes = [(e["event"], e["change"]) for e in log.read()["events"]]
        assert changes == [("window", "new"), ("watcher", "reconnected"), ("window", "close")]
        assert log.connected
    finally:
        log.stop()


def test_watcher_keeps_retrying_when_i3_is_unreachable():
    attempts = []

    def factory():
        attempts.append(1)
        if len(attempts) < 3:
            raise I3Error("Cannot connect to i3")
        return FakeStream([])

    log = events.EventLog(stream_factory=factory, backoff=0.01)
    log.start()
    try:
        wait_for(lambda: log.connected)
        assert len(attempts) == 3
        # Never connected before, so nothing was lost: no reconnect marker.
        assert log.read()["events"] == []
    finally:
        log.stop()
