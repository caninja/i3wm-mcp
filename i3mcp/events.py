"""A background log of i3 events that tools read by cursor, or wait on.

One daemon thread keeps its own SUBSCRIBE socket (events must never share the
command connection) and appends compact entries to a ring buffer. Every entry
gets a sequence number; a reader passes the last one it saw as `since`. When
the socket drops, the thread resubscribes and logs a "reconnected" entry, so a
reader can tell that events may be missing around it.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Callable

from . import ipc, tree
from .ipc import I3Error

SUBSCRIBED = ("workspace", "output", "mode", "window")
PAGE = 50

_NAMES = {
    ipc.EVENT_WORKSPACE: "workspace",
    ipc.EVENT_OUTPUT: "output",
    ipc.EVENT_MODE: "mode",
    ipc.EVENT_WINDOW: "window",
}


def shape(number: int, payload: Any) -> dict | None:
    """Turn one raw event into a compact entry, or None for an unsubscribed kind."""
    name = _NAMES.get(number)
    if name is None or not isinstance(payload, dict):
        return None
    entry: dict[str, Any] = {"event": name, "change": payload.get("change")}
    if name == "window":
        container = payload.get("container") or {}
        props = container.get("window_properties") or {}
        entry["window"] = tree._compact(
            {
                "con_id": container.get("id"),
                "name": container.get("name"),
                "window_class": props.get("class"),
                "marks": container.get("marks") or [],
                "urgent": bool(container.get("urgent")),
            }
        )
    elif name == "workspace":
        for key in ("current", "old"):
            node = payload.get(key)
            if isinstance(node, dict) and node.get("name") is not None:
                entry[key] = node["name"]
    return entry


def _contains(haystack: Any, needle: str) -> bool:
    return needle.lower() in str(haystack or "").lower()


def _passes(entry: dict, filters: dict) -> bool:
    if filters.get("event") is not None and entry["event"] != filters["event"]:
        return False
    if filters.get("change") is not None and entry.get("change") != filters["change"]:
        return False
    window = entry.get("window")
    if any(filters.get(key) is not None for key in ("window_class", "title", "con_id")):
        if window is None:
            return False
        if filters.get("window_class") is not None and not _contains(window.get("window_class"), filters["window_class"]):
            return False
        if filters.get("title") is not None and not _contains(window.get("name"), filters["title"]):
            return False
        if filters.get("con_id") is not None and window.get("con_id") != filters["con_id"]:
            return False
    return True


def _default_factory():
    return ipc.subscribe(list(SUBSCRIBED))


class EventLog:
    """Ring buffer of event entries, fed by a watcher thread once start() runs."""

    def __init__(
        self,
        stream_factory: Callable[[], Any] = _default_factory,
        maxlen: int = 500,
        backoff: float = 1.0,
    ):
        self._factory = stream_factory
        self._entries: deque[tuple[int, float, dict]] = deque(maxlen=maxlen)
        self._seq = 0
        self._cond = threading.Condition()
        self._backoff = backoff
        self._stop = threading.Event()
        self._connected_once = threading.Event()
        self._thread: threading.Thread | None = None
        self._stream: Any = None
        self.connected = False
        self.last_error: str | None = None

    # --- writing ---------------------------------------------------------

    def append(self, entry: dict) -> None:
        with self._cond:
            self._seq += 1
            self._entries.append((self._seq, time.monotonic(), entry))
            self._cond.notify_all()

    def ingest(self, number: int, payload: Any) -> None:
        entry = shape(number, payload)
        if entry is not None:
            self.append(entry)

    # --- reading ---------------------------------------------------------

    def read(self, since: int | None = None, filters: dict | None = None) -> dict:
        """Matching entries after `since`, or the latest page when it is None."""
        with self._cond:
            return self._read_locked(since, filters or {})

    def wait(self, since: int | None = None, filters: dict | None = None, timeout: float = 0) -> dict:
        """Like read, but block up to `timeout` seconds for a first match.

        Without `since`, only events from now on count.
        """
        deadline = time.monotonic() + timeout
        with self._cond:
            if since is None:
                since = self._seq
            while True:
                result = self._read_locked(since, filters or {})
                remaining = deadline - time.monotonic()
                if result["events"] or remaining <= 0:
                    if not result["events"]:
                        result["timed_out"] = True
                    return result
                self._cond.wait(remaining)

    def _read_locked(self, since: int | None, filters: dict) -> dict:
        now = time.monotonic()
        matched = [
            (seq, at, entry)
            for seq, at, entry in self._entries
            if (since is None or seq > since) and _passes(entry, filters)
        ]
        meta: dict[str, Any] = {"cursor": self._seq}
        if since is None:
            matched = matched[-PAGE:]
        else:
            oldest = self._entries[0][0] if self._entries else self._seq + 1
            if since + 1 < oldest:
                meta["dropped"] = True
            if len(matched) > PAGE:
                matched = matched[:PAGE]
                meta["cursor"] = matched[-1][0]
                meta["more"] = True
        events = [{"seq": seq, **entry, "ago": round(now - at, 1)} for seq, at, entry in matched]
        return {"events": events, **meta}

    # --- the watcher thread ----------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="i3mcp-events", daemon=True)
            self._thread.start()

    def wait_connected(self, timeout: float) -> bool:
        return self._connected_once.wait(timeout)

    def stop(self) -> None:
        self._stop.set()
        if self._stream is not None:
            self._stream.close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        delay = self._backoff
        while not self._stop.is_set():
            try:
                stream = self._factory()
            except (I3Error, OSError) as exc:
                self.connected, self.last_error = False, str(exc)
                self._stop.wait(delay)
                delay = min(delay * 2, 5 * self._backoff)
                continue
            self._stream, self.connected, self.last_error = stream, True, None
            delay = self._backoff
            if self._connected_once.is_set():
                self.append({"event": "watcher", "change": "reconnected"})
            self._connected_once.set()
            try:
                while not self._stop.is_set():
                    self.ingest(*stream.read_event())
            except (I3Error, OSError, ValueError) as exc:
                self.connected, self.last_error = False, str(exc)
            finally:
                stream.close()


_log: EventLog | None = None


def get_log() -> EventLog:
    """The process-wide log, started on first use."""
    global _log
    if _log is None:
        _log = EventLog()
        _log.start()
    return _log


def set_log(log: EventLog | None) -> None:
    """Test seam. Pass None to reset to a real log."""
    global _log
    _log = log
