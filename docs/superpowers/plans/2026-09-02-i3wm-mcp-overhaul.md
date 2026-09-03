# i3wm-mcp Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the i3wm MCP server on a native IPC transport with shared window criteria, consolidating 43 tools into 13 and fixing ten verified defects.

**Architecture:** A stdlib-only `I3Connection` speaks i3's IPC protocol over its unix socket, replacing per-call `i3-msg` forks and surfacing i3's structured errors. A single `WindowCriteria` model, escaped and anchored, is accepted by every mutating tool so commands can target any window rather than only the focused one. Tools are grouped into 13 verb-shaped modules under `i3mcp/tools/`, each taking flat keyword arguments.

**Tech Stack:** Python 3.10+, `mcp>=2` (`MCPServer`), `pydantic>=2`, `pytest`. No other runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-09-02-i3wm-mcp-overhaul-design.md`

## Global Constraints

- Target i3 **4.25.1**. Every emitted command string must parse on that version.
- Runtime dependencies are **`mcp>=2` and `pydantic>=2` only**. No `i3ipc`, no `fastmcp`, no `subprocess` calls except `i3 --get-socketpath`.
- Import is `from mcp.server.mcpserver import MCPServer`. `FastMCP` does not exist in `mcp` 2.x.
- Tools take **flat keyword arguments**, never a single `params: Model` wrapper.
- Tool docstrings are **at most 6 lines**. Detail belongs in `Field(description=...)`.
- Every tool returns a **JSON string** (`json.dumps(..., indent=2)`) unless the caller asks for markdown.
- Criteria string values default to **exact** matching via `^\Qvalue\E$`.
- `exit` must never be exposed as a tool action.
- Python 3.10+ syntax is fine (`X | None` unions).
- Work happens on branch `overhaul-ipc-criteria`, already checked out.
- Run tests with `uv run --with mcp --with pydantic --with pytest pytest`.

**Already verified against mcp 2.1.1 — do not re-litigate these:**

- `@mcp.tool(name=..., annotations={...})` accepts a plain dict for `annotations`.
- A parameter written `mode: Literal[...] = Field(description="...")` with no
  default is correctly emitted as **required** in the JSON schema.
- A nested pydantic model parameter (`criteria: WindowCriteria | None`) renders
  as a `$ref` and is callable with a plain dict.
- `MCPServer.run()` defaults to the stdio transport.

---

## File Structure

**Create:**

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | Package metadata, deps, entry point |
| `i3mcp/__init__.py` | Empty package marker |
| `i3mcp/ipc.py` | `I3Connection`, `I3Error`, message-type constants |
| `i3mcp/enums.py` | Shared `str, Enum` types |
| `i3mcp/criteria.py` | `WindowCriteria`, escaping, criteria-string builder |
| `i3mcp/tree.py` | Tree walking, window-record extraction, filtering |
| `i3mcp/render.py` | JSON/markdown rendering, safe truncation, result envelope |
| `i3mcp/server.py` | The `MCPServer` instance and tool registration |
| `i3mcp/tools/__init__.py` | Imports every tool module so decorators run |
| `i3mcp/tools/query.py` | `i3_query` |
| `i3mcp/tools/focus.py` | `i3_focus` |
| `i3mcp/tools/move.py` | `i3_move` |
| `i3mcp/tools/resize.py` | `i3_resize` |
| `i3mcp/tools/kill.py` | `i3_kill` |
| `i3mcp/tools/window.py` | `i3_window` |
| `i3mcp/tools/layout.py` | `i3_layout` |
| `i3mcp/tools/workspace.py` | `i3_workspace` |
| `i3mcp/tools/mark.py` | `i3_mark` |
| `i3mcp/tools/scratchpad.py` | `i3_scratchpad` |
| `i3mcp/tools/gaps.py` | `i3_gaps` |
| `i3mcp/tools/bar.py` | `i3_bar` |
| `i3mcp/tools/wm.py` | `i3_wm` |
| `tests/conftest.py` | `FakeTransport` fixture |
| `tests/test_ipc.py` … `tests/test_tools_*.py` | Unit tests |
| `scripts/smoke.py` | Opt-in live smoke test |

**Modify:**

- `i3_mcp.py` — replaced entirely by a shim (Task 14)
- `README.md` — rewritten (Task 14)
- `.claude/settings.local.json` — allowlist updated (Task 14)
- `.gitignore` — add `.venv`, `*.egg-info`, `.pytest_cache`

---

### Task 1: Packaging and the IPC transport

**Files:**
- Create: `pyproject.toml`, `i3mcp/__init__.py`, `i3mcp/ipc.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_ipc.py`

> `tests/__init__.py` is empty but required: later tasks do
> `from tests.test_tree import sample_tree`, which needs `tests` to be a package.
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `i3mcp.ipc.I3Error(Exception)` with attributes `message: str`, `replies: list[dict] | None`
  - `i3mcp.ipc.RUN_COMMAND=0, GET_WORKSPACES=1, SUBSCRIBE=2, GET_OUTPUTS=3, GET_TREE=4, GET_MARKS=5, GET_BAR_CONFIG=6, GET_VERSION=7, GET_BINDING_MODES=8, GET_CONFIG=9, SEND_TICK=10, SYNC=11, GET_BINDING_STATE=12`
  - `i3mcp.ipc.I3Connection` with:
    - `__init__(self, socket_path: str | None = None)`
    - `request(self, msg_type: int, payload: str = "") -> Any`
    - `command(self, cmd: str) -> list[dict]` — raises `I3Error` if any reply has `success: false`
    - `query(self, msg_type: int, payload: str = "") -> Any`
    - `close(self) -> None`
  - `i3mcp.ipc.get_connection() -> I3Connection` — module-level lazily-created singleton
  - `i3mcp.ipc.set_connection(conn) -> None` — test seam

- [ ] **Step 1: Write the failing tests**

Create `tests/conftest.py`:

```python
import pytest

from i3mcp import ipc


class FakeTransport:
    """Stands in for I3Connection. Records commands, returns canned replies."""

    def __init__(self):
        self.commands: list[str] = []
        self.command_replies: list[list[dict]] = []
        self.query_replies: dict[int, object] = {}

    def command(self, cmd: str) -> list[dict]:
        self.commands.append(cmd)
        if self.command_replies:
            reply = self.command_replies.pop(0)
        else:
            reply = [{"success": True}]
        failed = [r for r in reply if not r.get("success")]
        if failed:
            raise ipc.I3Error(failed[0].get("error", "command failed"), replies=reply)
        return reply

    def query(self, msg_type: int, payload: str = ""):
        return self.query_replies[msg_type]

    @property
    def last_command(self) -> str:
        return self.commands[-1]


@pytest.fixture
def fake(monkeypatch):
    transport = FakeTransport()
    ipc.set_connection(transport)
    yield transport
    ipc.set_connection(None)
```

Create `tests/test_ipc.py`:

```python
import json
import socket
import struct
import threading

import pytest

from i3mcp import ipc


def _serve(sock_path, replies):
    """Minimal fake i3: accepts one connection, answers each request in order."""
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)
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
    sock_path = str(tmp_path / "ipc.sock")

    def start(replies):
        thread = threading.Thread(target=_serve, args=(sock_path, replies), daemon=True)
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --with mcp --with pydantic --with pytest pytest tests/test_ipc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'i3mcp'`

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[project]
name = "i3wm-mcp"
version = "0.2.0"
description = "Model Context Protocol server for the i3 window manager"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.10"
dependencies = [
    "mcp>=2",
    "pydantic>=2",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
i3wm-mcp = "i3mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["i3mcp"]
```

- [ ] **Step 4: Write `i3mcp/__init__.py` and `i3mcp/ipc.py`**

`i3mcp/__init__.py` is empty.

`i3mcp/ipc.py` — the protocol below is verified against live i3 4.25.1:

```python
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
```

- [ ] **Step 5: Add to `.gitignore`**

Append these lines to the existing `.gitignore`:

```
.venv
*.egg-info
.pytest_cache
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run --with mcp --with pydantic --with pytest pytest tests/test_ipc.py -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml i3mcp/ tests/ .gitignore
git commit -m "feat: native i3 IPC transport with structured errors"
```

---

### Task 2: Shared enums and window criteria

**Files:**
- Create: `i3mcp/enums.py`, `i3mcp/criteria.py`, `tests/test_criteria.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `i3mcp.enums`: `Direction(LEFT/RIGHT/UP/DOWN)`, `MatchMode(EXACT/SUBSTRING/REGEX)`, `Urgency(LATEST/OLDEST/NEWEST/LAST/RECENT/FIRST)`, `WindowType(NORMAL/DIALOG/UTILITY/TOOLBAR/SPLASH/MENU/DROPDOWN_MENU/POPUP_MENU/TOOLTIP/NOTIFICATION)`, `Unit(PX/PPT)`, `ResponseFormat(JSON/MARKDOWN)` — all `(str, Enum)`
  - `i3mcp.criteria.escape_value(value: str) -> str`
  - `i3mcp.criteria.pattern_for(value: str, mode: MatchMode) -> str`
  - `i3mcp.criteria.WindowCriteria` (pydantic `BaseModel`) with `to_selector(self) -> str` returning `""` when empty, else `[key="value" ...]`
  - `i3mcp.criteria.prefix_command(criteria: WindowCriteria | None, command: str) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_criteria.py`:

```python
import pytest

from i3mcp.criteria import WindowCriteria, escape_value, pattern_for, prefix_command
from i3mcp.enums import MatchMode


def test_escape_order():
    # A backslash must be doubled, and a quote escaped, without double-escaping.
    assert escape_value('say "hi"') == r'say \"hi\"'
    assert escape_value("back\\slash") == "back\\\\slash"


def test_exact_mode_anchors_and_quotes_literally():
    assert pattern_for("Firefox", MatchMode.EXACT) == r"^\QFirefox\E$"


def test_substring_mode_quotes_without_anchors():
    assert pattern_for("fire", MatchMode.SUBSTRING) == r"\Qfire\E"


def test_regex_mode_passes_through():
    assert pattern_for("(?i)^fire", MatchMode.REGEX) == "(?i)^fire"


def test_empty_criteria_is_empty_selector():
    assert WindowCriteria().to_selector() == ""


def test_class_criteria_is_exact_by_default():
    got = WindowCriteria(window_class="Firefox").to_selector()
    assert got == r'[class="^\QFirefox\E$"]'


def test_multiple_criteria_are_anded():
    got = WindowCriteria(window_class="Firefox", con_mark="browser").to_selector()
    assert got == r'[class="^\QFirefox\E$" con_mark="^\Qbrowser\E$"]'


def test_con_id_is_numeric_and_unquoted():
    assert WindowCriteria(con_id=12345).to_selector() == "[con_id=12345]"


def test_window_id_is_numeric_and_unquoted():
    assert WindowCriteria(window_id=98765).to_selector() == "[id=98765]"


def test_valueless_criteria_emit_bare_keys():
    assert WindowCriteria(floating=True).to_selector() == "[floating]"
    assert WindowCriteria(tiling=True).to_selector() == "[tiling]"
    assert WindowCriteria(all=True).to_selector() == "[all]"


def test_urgent_uses_i3_vocabulary_not_yes():
    got = WindowCriteria(urgent="latest").to_selector()
    assert got == "[urgent=latest]"


def test_urgent_rejects_boolean_style_values():
    with pytest.raises(ValueError):
        WindowCriteria(urgent="yes")


def test_regex_mode_applies_to_string_fields():
    got = WindowCriteria(title="term.*", match=MatchMode.REGEX).to_selector()
    assert got == '[title="term.*"]'


def test_prefix_command_without_criteria_is_bare():
    assert prefix_command(None, "kill") == "kill"
    assert prefix_command(WindowCriteria(), "kill") == "kill"


def test_prefix_command_with_criteria():
    got = prefix_command(WindowCriteria(con_mark="term"), "kill")
    assert got == r'[con_mark="^\Qterm\E$"] kill'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --with mcp --with pydantic --with pytest pytest tests/test_criteria.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'i3mcp.criteria'`

- [ ] **Step 3: Write `i3mcp/enums.py`**

```python
"""Shared enumerations. All are (str, Enum) so pydantic renders them as strings."""

from __future__ import annotations

from enum import Enum


class Direction(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


class MatchMode(str, Enum):
    EXACT = "exact"
    SUBSTRING = "substring"
    REGEX = "regex"


class Urgency(str, Enum):
    LATEST = "latest"
    OLDEST = "oldest"
    NEWEST = "newest"
    LAST = "last"
    RECENT = "recent"
    FIRST = "first"


class WindowType(str, Enum):
    NORMAL = "normal"
    DIALOG = "dialog"
    UTILITY = "utility"
    TOOLBAR = "toolbar"
    SPLASH = "splash"
    MENU = "menu"
    DROPDOWN_MENU = "dropdown_menu"
    POPUP_MENU = "popup_menu"
    TOOLTIP = "tooltip"
    NOTIFICATION = "notification"


class Unit(str, Enum):
    PX = "px"
    PPT = "ppt"


class ResponseFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"
```

- [ ] **Step 4: Write `i3mcp/criteria.py`**

```python
"""Window criteria shared by every mutating tool.

i3 matches criteria values as PCRE. Verified on i3 4.25.1: \\Q...\\E literal
quoting works, and \\" escapes correctly inside a quoted criteria value.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import MatchMode, Urgency, WindowType


def escape_value(value: str) -> str:
    """Escape a value for inclusion in a double-quoted i3 criteria string."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def pattern_for(value: str, mode: MatchMode) -> str:
    """Build the PCRE i3 should match against."""
    if mode == MatchMode.REGEX:
        return value
    quoted = f"\\Q{value}\\E"
    if mode == MatchMode.SUBSTRING:
        return quoted
    return f"^{quoted}$"


class WindowCriteria(BaseModel):
    """Selects which window(s) a command applies to.

    Leave every field unset to act on the currently focused window.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    window_class: str | None = Field(
        default=None,
        description="X11 window class, the second part of WM_CLASS (e.g. 'firefox').",
    )
    instance: str | None = Field(
        default=None,
        description="X11 window instance, the first part of WM_CLASS (e.g. 'Navigator').",
    )
    title: str | None = Field(default=None, description="Window title.")
    window_role: str | None = Field(default=None, description="WM_WINDOW_ROLE value.")
    window_type: WindowType | None = Field(default=None, description="Window type.")
    machine: str | None = Field(default=None, description="WM_CLIENT_MACHINE hostname.")
    con_mark: str | None = Field(default=None, description="i3 mark set on the container.")
    workspace: str | None = Field(default=None, description="Name of the containing workspace.")
    con_id: int | None = Field(
        default=None,
        description="i3 container id, from i3_query. The most precise selector.",
    )
    window_id: int | None = Field(default=None, description="X11 window id.")
    urgent: Urgency | None = Field(
        default=None,
        description="Match urgent windows. i3 accepts latest/oldest/newest/last/recent/first, never 'yes'.",
    )
    floating: bool = Field(default=False, description="Match only floating windows.")
    tiling: bool = Field(default=False, description="Match only tiling windows.")
    all: bool = Field(default=False, description="Match every window.")
    match: MatchMode = Field(
        default=MatchMode.EXACT,
        description="How string values match: exact (default), substring, or regex.",
    )

    def is_empty(self) -> bool:
        return not self.to_selector()

    def to_selector(self) -> str:
        """Render as an i3 criteria selector, or '' when nothing is set."""
        parts: list[str] = []
        string_fields = [
            ("class", self.window_class),
            ("instance", self.instance),
            ("title", self.title),
            ("window_role", self.window_role),
            ("machine", self.machine),
            ("con_mark", self.con_mark),
            ("workspace", self.workspace),
        ]
        for key, value in string_fields:
            if value is not None:
                pattern = escape_value(pattern_for(value, self.match))
                parts.append(f'{key}="{pattern}"')
        if self.window_type is not None:
            parts.append(f'window_type="{self.window_type.value}"')
        if self.con_id is not None:
            parts.append(f"con_id={self.con_id}")
        if self.window_id is not None:
            parts.append(f"id={self.window_id}")
        if self.urgent is not None:
            parts.append(f"urgent={self.urgent.value}")
        if self.floating:
            parts.append("floating")
        if self.tiling:
            parts.append("tiling")
        if self.all:
            parts.append("all")
        if not parts:
            return ""
        return "[" + " ".join(parts) + "]"


def prefix_command(criteria: WindowCriteria | None, command: str) -> str:
    """Prefix a command with a criteria selector, if there is one."""
    selector = criteria.to_selector() if criteria is not None else ""
    return f"{selector} {command}" if selector else command
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --with mcp --with pydantic --with pytest pytest tests/test_criteria.py -v`
Expected: 13 passed

- [ ] **Step 6: Commit**

```bash
git add i3mcp/enums.py i3mcp/criteria.py tests/test_criteria.py
git commit -m "feat: shared window criteria with PCRE-safe escaping"
```

---

### Task 3: Tree walking and window records

**Files:**
- Create: `i3mcp/tree.py`, `tests/test_tree.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `i3mcp.tree.WindowRecord` — a `TypedDict`-shaped plain dict with keys `con_id`, `window_id`, `name`, `window_class`, `instance`, `window_role`, `window_type`, `marks`, `workspace`, `output`, `floating`, `focused`, `urgent`, `fullscreen`, `scratchpad_state`, `layout`, `rect`
  - `i3mcp.tree.walk_windows(tree: dict) -> list[dict]` — every window, each carrying workspace/output context
  - `i3mcp.tree.is_dock(record: dict) -> bool`
  - `i3mcp.tree.filter_windows(records, *, window_class=None, title=None, instance=None, window_type=None, workspace=None, mark=None, floating=None, urgent=None, focused=None, scratchpad=None, include_docks=False) -> list[dict]`
  - `i3mcp.tree.find_focused(records) -> dict | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tree.py`. The fixture mirrors the real shape of an i3
4.25.1 tree: floating windows are `type: con` with `floating: "user_on"`,
nested inside a `floating_con` under a workspace.

```python
from i3mcp import tree


def sample_tree():
    return {
        "type": "root",
        "name": "root",
        "nodes": [
            {
                "type": "output",
                "name": "DisplayPort-1",
                "nodes": [
                    {
                        "type": "dockarea",
                        "name": "topdock",
                        "nodes": [
                            {
                                "type": "con",
                                "id": 1,
                                "window": 111,
                                "name": "i3bar for output DisplayPort-1",
                                "floating": "auto_off",
                                "window_type": "dock",
                                "window_properties": {"class": "i3bar"},
                                "nodes": [],
                                "floating_nodes": [],
                            }
                        ],
                        "floating_nodes": [],
                    },
                    {
                        "type": "con",
                        "name": "content",
                        "nodes": [
                            {
                                "type": "workspace",
                                "name": "3",
                                "num": 3,
                                "output": "DisplayPort-1",
                                "layout": "splith",
                                "nodes": [
                                    {
                                        "type": "con",
                                        "id": 2,
                                        "window": 222,
                                        "name": "Firefox — front page",
                                        "floating": "auto_off",
                                        "focused": True,
                                        "urgent": False,
                                        "fullscreen_mode": 0,
                                        "marks": [],
                                        "layout": "splith",
                                        "rect": {"x": 0, "y": 0, "width": 800, "height": 600},
                                        "window_type": "normal",
                                        "window_properties": {
                                            "class": "firefox",
                                            "instance": "Navigator",
                                            "window_role": "browser",
                                        },
                                        "nodes": [],
                                        "floating_nodes": [],
                                    }
                                ],
                                "floating_nodes": [
                                    {
                                        "type": "floating_con",
                                        "id": 3,
                                        "nodes": [
                                            {
                                                "type": "con",
                                                "id": 4,
                                                "window": 444,
                                                "name": "Downloads - Thunar",
                                                "floating": "user_on",
                                                "focused": False,
                                                "urgent": False,
                                                "fullscreen_mode": 0,
                                                "marks": ["files"],
                                                "layout": "splith",
                                                "rect": {"x": 10, "y": 10, "width": 400, "height": 300},
                                                "window_type": "normal",
                                                "window_properties": {
                                                    "class": "Thunar",
                                                    "instance": "thunar",
                                                },
                                                "nodes": [],
                                                "floating_nodes": [],
                                            }
                                        ],
                                        "floating_nodes": [],
                                    }
                                ],
                            }
                        ],
                        "floating_nodes": [],
                    },
                ],
                "floating_nodes": [],
            },
            {
                "type": "output",
                "name": "__i3",
                "nodes": [
                    {
                        "type": "con",
                        "name": "content",
                        "nodes": [
                            {
                                "type": "workspace",
                                "name": "__i3_scratch",
                                "num": -1,
                                "output": "__i3",
                                "nodes": [],
                                "floating_nodes": [
                                    {
                                        "type": "floating_con",
                                        "id": 5,
                                        "nodes": [
                                            {
                                                "type": "con",
                                                "id": 6,
                                                "window": 666,
                                                "name": "scratch term",
                                                "floating": "user_on",
                                                "focused": False,
                                                "marks": ["term"],
                                                "scratchpad_state": "fresh",
                                                "rect": {"x": 0, "y": 0, "width": 10, "height": 10},
                                                "window_properties": {"class": "Alacritty"},
                                                "nodes": [],
                                                "floating_nodes": [],
                                            }
                                        ],
                                        "floating_nodes": [],
                                    }
                                ],
                            }
                        ],
                        "floating_nodes": [],
                    }
                ],
                "floating_nodes": [],
            },
        ],
        "floating_nodes": [],
    }


def test_walk_finds_every_window_including_docks_and_scratchpad():
    records = tree.walk_windows(sample_tree())
    assert {r["con_id"] for r in records} == {1, 2, 4, 6}


def test_records_carry_workspace_and_output_context():
    records = {r["con_id"]: r for r in tree.walk_windows(sample_tree())}
    assert records[2]["workspace"] == "3"
    assert records[2]["output"] == "DisplayPort-1"
    assert records[6]["workspace"] == "__i3_scratch"


def test_floating_read_from_floating_field_not_node_type():
    records = {r["con_id"]: r for r in tree.walk_windows(sample_tree())}
    assert records[4]["floating"] is True
    assert records[2]["floating"] is False


def test_docks_excluded_by_default():
    records = tree.filter_windows(tree.walk_windows(sample_tree()))
    assert 1 not in {r["con_id"] for r in records}


def test_docks_included_on_request():
    records = tree.filter_windows(tree.walk_windows(sample_tree()), include_docks=True)
    assert 1 in {r["con_id"] for r in records}


def test_workspace_filter_actually_filters():
    records = tree.filter_windows(tree.walk_windows(sample_tree()), workspace="3")
    assert {r["con_id"] for r in records} == {2, 4}


def test_workspace_filter_rejects_unknown_workspace():
    assert tree.filter_windows(tree.walk_windows(sample_tree()), workspace="999") == []


def test_floating_filter_matches_floating_windows():
    records = tree.filter_windows(tree.walk_windows(sample_tree()), floating=True)
    assert {r["con_id"] for r in records} == {4, 6}


def test_class_filter_is_case_insensitive_substring():
    records = tree.filter_windows(tree.walk_windows(sample_tree()), window_class="thunar")
    assert {r["con_id"] for r in records} == {4}


def test_scratchpad_filter_selects_scratchpad_workspace():
    records = tree.filter_windows(tree.walk_windows(sample_tree()), scratchpad=True)
    assert {r["con_id"] for r in records} == {6}


def test_find_focused():
    focused = tree.find_focused(tree.walk_windows(sample_tree()))
    assert focused["con_id"] == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --with mcp --with pydantic --with pytest pytest tests/test_tree.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'i3mcp.tree'`

- [ ] **Step 3: Write `i3mcp/tree.py`**

```python
"""Walk the i3 tree into flat window records carrying their context.

i3 4.25.1 puts every managed window in a node of type 'con' with a separate
'floating' field of 'auto_off' | 'auto_on' | 'user_off' | 'user_on'. A node of
type 'floating_con' is the wrapper, not the window, so testing node type for
floating never matches.
"""

from __future__ import annotations

from typing import Any

SCRATCHPAD_WORKSPACE = "__i3_scratch"
_FLOATING_STATES = {"auto_on", "user_on"}


def _record(node: dict, workspace: str | None, output: str | None) -> dict:
    props = node.get("window_properties") or {}
    return {
        "con_id": node.get("id"),
        "window_id": node.get("window"),
        "name": node.get("name"),
        "window_class": props.get("class"),
        "instance": props.get("instance"),
        "window_role": props.get("window_role"),
        "window_type": node.get("window_type"),
        "marks": node.get("marks") or [],
        "workspace": workspace,
        "output": output,
        "floating": node.get("floating") in _FLOATING_STATES,
        "focused": bool(node.get("focused")),
        "urgent": bool(node.get("urgent")),
        "fullscreen": bool(node.get("fullscreen_mode")),
        "scratchpad_state": node.get("scratchpad_state"),
        "layout": node.get("layout"),
        "rect": node.get("rect") or {},
    }


def walk_windows(tree: dict) -> list[dict]:
    """Flatten the tree into window records, tagged with workspace and output."""
    records: list[dict] = []

    def visit(node: dict, workspace: str | None, output: str | None) -> None:
        node_type = node.get("type")
        if node_type == "output":
            output = node.get("name") or output
        elif node_type == "workspace":
            workspace = node.get("name") or workspace
            output = node.get("output") or output

        window_id = node.get("window")
        if window_id:
            records.append(_record(node, workspace, output))

        for child in list(node.get("nodes") or []) + list(node.get("floating_nodes") or []):
            visit(child, workspace, output)

    visit(tree, None, None)
    return records


def is_dock(record: dict) -> bool:
    """i3bar and other docked clients appear in the tree as ordinary windows."""
    return record.get("window_type") == "dock"


def _contains(haystack: Any, needle: str) -> bool:
    return needle.lower() in str(haystack or "").lower()


def filter_windows(
    records: list[dict],
    *,
    window_class: str | None = None,
    title: str | None = None,
    instance: str | None = None,
    window_type: str | None = None,
    workspace: str | None = None,
    mark: str | None = None,
    floating: bool | None = None,
    urgent: bool | None = None,
    focused: bool | None = None,
    scratchpad: bool | None = None,
    include_docks: bool = False,
) -> list[dict]:
    """Filter window records. String filters are case-insensitive substrings."""
    result = []
    for record in records:
        if not include_docks and is_dock(record):
            continue
        if window_class is not None and not _contains(record["window_class"], window_class):
            continue
        if title is not None and not _contains(record["name"], title):
            continue
        if instance is not None and not _contains(record["instance"], instance):
            continue
        if window_type is not None and record.get("window_type") != window_type:
            continue
        if workspace is not None and record.get("workspace") != workspace:
            continue
        if mark is not None and mark not in (record.get("marks") or []):
            continue
        if floating is not None and record["floating"] is not floating:
            continue
        if urgent is not None and record["urgent"] is not urgent:
            continue
        if focused is not None and record["focused"] is not focused:
            continue
        in_scratchpad = record.get("workspace") == SCRATCHPAD_WORKSPACE
        if scratchpad is not None and in_scratchpad is not scratchpad:
            continue
        result.append(record)
    return result


def find_focused(records: list[dict]) -> dict | None:
    for record in records:
        if record["focused"]:
            return record
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with mcp --with pydantic --with pytest pytest tests/test_tree.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add i3mcp/tree.py tests/test_tree.py
git commit -m "feat: tree walking with workspace context and correct floating detection"
```

---

### Task 4: Rendering and safe truncation

**Files:**
- Create: `i3mcp/render.py`, `tests/test_render.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `i3mcp.render.CHARACTER_LIMIT = 25000`
  - `i3mcp.render.ok(**fields) -> str` — `{"success": true, ...}` as indented JSON
  - `i3mcp.render.err(message: str, **fields) -> str` — `{"success": false, "error": ...}`
  - `i3mcp.render.run(command: str, **extra) -> str` — execute via `ipc.get_connection().command`, catch `I3Error`, return `ok`/`err`
  - `i3mcp.render.json_list(key: str, items: list, limit: int = CHARACTER_LIMIT, **fields) -> str` — drops whole items rather than slicing
  - `i3mcp.render.markdown(text: str, limit: int = CHARACTER_LIMIT) -> str`
  - `i3mcp.render.window_lines(records: list[dict]) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_render.py`:

```python
import json

import pytest

from i3mcp import render
from i3mcp.ipc import I3Error


def test_ok_is_valid_json_with_success_true():
    parsed = json.loads(render.ok(command="nop"))
    assert parsed["success"] is True
    assert parsed["command"] == "nop"


def test_err_carries_the_message():
    parsed = json.loads(render.err("boom", command="bad"))
    assert parsed["success"] is False
    assert parsed["error"] == "boom"


def test_run_sends_command_and_reports_success(fake):
    result = json.loads(render.run("nop hello"))
    assert fake.last_command == "nop hello"
    assert result["success"] is True


def test_run_surfaces_i3_error_text(fake):
    fake.command_replies = [[{"success": False, "error": "Expected 'current', 'all'"}]]
    result = json.loads(render.run("gaps inner workspace set 10"))
    assert result["success"] is False
    assert "current" in result["error"]


def test_json_list_stays_valid_json_when_truncated():
    items = [{"name": "x" * 100, "index": i} for i in range(500)]
    out = render.json_list("windows", items, limit=2000)
    parsed = json.loads(out)  # must not raise
    assert parsed["success"] is True
    assert len(parsed["windows"]) < 500
    assert parsed["truncated"] is True
    assert parsed["omitted"] == 500 - len(parsed["windows"])


def test_json_list_untruncated_has_no_truncation_keys():
    parsed = json.loads(render.json_list("windows", [{"a": 1}]))
    assert "truncated" not in parsed
    assert parsed["count"] == 1


def test_markdown_truncation_appends_notice():
    out = render.markdown("y" * 100, limit=50)
    assert len(out) > 50
    assert "truncated" in out.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --with mcp --with pydantic --with pytest pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'i3mcp.render'`

- [ ] **Step 3: Write `i3mcp/render.py`**

```python
"""Response shaping. Every tool returns a JSON string unless asked for markdown."""

from __future__ import annotations

import json
from typing import Any

from . import ipc
from .ipc import I3Error

CHARACTER_LIMIT = 25000


def _dump(payload: dict) -> str:
    return json.dumps(payload, indent=2)


def ok(**fields: Any) -> str:
    return _dump({"success": True, **fields})


def err(message: str, **fields: Any) -> str:
    return _dump({"success": False, "error": message, **fields})


def run(command: str, **extra: Any) -> str:
    """Run an i3 command and render the outcome."""
    try:
        replies = ipc.get_connection().command(command)
    except I3Error as exc:
        payload: dict[str, Any] = {"command": command, **extra}
        if exc.replies is not None:
            payload["i3_replies"] = exc.replies
        return err(str(exc), **payload)
    return ok(command=command, replies=replies, **extra)


def json_list(key: str, items: list, limit: int = CHARACTER_LIMIT, **fields: Any) -> str:
    """Render a list, dropping whole entries rather than slicing mid-structure."""
    kept = list(items)
    while True:
        payload: dict[str, Any] = {"success": True, key: kept, "count": len(kept), **fields}
        if len(kept) < len(items):
            payload["truncated"] = True
            payload["omitted"] = len(items) - len(kept)
            payload["hint"] = "Narrow the filters to see the rest."
        out = _dump(payload)
        if len(out) <= limit or not kept:
            return out
        # Drop roughly the proportion that overflows, at least one entry.
        overflow = len(out) - limit
        drop = max(1, int(len(kept) * overflow / len(out)) + 1)
        kept = kept[: max(0, len(kept) - drop)]


def markdown(text: str, limit: int = CHARACTER_LIMIT) -> str:
    if len(text) <= limit:
        return text
    notice = (
        f"\n\n---\n**Response truncated** (exceeded {limit} characters). "
        "Narrow the filters to see the rest."
    )
    return text[:limit] + notice


def window_lines(records: list[dict]) -> str:
    """Render window records as a compact markdown list."""
    if not records:
        return "No windows match.\n"
    lines = []
    for record in records:
        flags = []
        if record.get("focused"):
            flags.append("focused")
        if record.get("floating"):
            flags.append("floating")
        if record.get("urgent"):
            flags.append("urgent")
        if record.get("fullscreen"):
            flags.append("fullscreen")
        marks = record.get("marks") or []
        if marks:
            flags.append("marks: " + ", ".join(marks))
        suffix = f" [{'; '.join(flags)}]" if flags else ""
        lines.append(
            f"- **{record.get('name') or 'Untitled'}**{suffix}\n"
            f"  - class: `{record.get('window_class')}`  instance: `{record.get('instance')}`\n"
            f"  - workspace: `{record.get('workspace')}`  output: `{record.get('output')}`\n"
            f"  - con_id: `{record.get('con_id')}`  window_id: `{record.get('window_id')}`\n"
        )
    return "".join(lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with mcp --with pydantic --with pytest pytest tests/test_render.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add i3mcp/render.py tests/test_render.py
git commit -m "feat: response rendering with structure-preserving truncation"
```

---

### Task 5: Server instance and `i3_query`

**Files:**
- Create: `i3mcp/server.py`, `i3mcp/tools/__init__.py`, `i3mcp/tools/query.py`, `tests/test_tools_query.py`

**Interfaces:**
- Consumes: `i3mcp.ipc`, `i3mcp.tree`, `i3mcp.render`, `i3mcp.enums`.
- Produces:
  - `i3mcp.server.mcp` — the `MCPServer` instance every tool module decorates
  - `i3mcp.server.main() -> None` — imports `i3mcp.tools` then calls `mcp.run()`
  - `i3mcp.tools.query.i3_query(...)` — async, returns `str`

`i3mcp/tools/__init__.py` must import every tool module so its decorators run.
Add each new module to it as you go.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tools_query.py`:

```python
import json

import pytest

from i3mcp import ipc
from i3mcp.enums import ResponseFormat
from i3mcp.tools.query import i3_query
from tests.test_tree import sample_tree


@pytest.mark.asyncio
async def test_query_tree_returns_records_with_context(fake):
    fake.query_replies[ipc.GET_TREE] = sample_tree()
    result = json.loads(await i3_query(what="tree"))
    assert result["success"] is True
    con_ids = {w["con_id"] for w in result["windows"]}
    assert con_ids == {2, 4, 6}  # dock excluded
    firefox = next(w for w in result["windows"] if w["con_id"] == 2)
    assert firefox["workspace"] == "3"
    assert firefox["floating"] is False


@pytest.mark.asyncio
async def test_query_tree_workspace_filter(fake):
    fake.query_replies[ipc.GET_TREE] = sample_tree()
    result = json.loads(await i3_query(what="tree", workspace="999"))
    assert result["windows"] == []


@pytest.mark.asyncio
async def test_query_tree_floating_filter(fake):
    fake.query_replies[ipc.GET_TREE] = sample_tree()
    result = json.loads(await i3_query(what="tree", floating=True))
    assert {w["con_id"] for w in result["windows"]} == {4, 6}


@pytest.mark.asyncio
async def test_query_focused(fake):
    fake.query_replies[ipc.GET_TREE] = sample_tree()
    result = json.loads(await i3_query(what="focused"))
    assert result["window"]["con_id"] == 2


@pytest.mark.asyncio
async def test_query_scratchpad(fake):
    fake.query_replies[ipc.GET_TREE] = sample_tree()
    result = json.loads(await i3_query(what="scratchpad"))
    assert {w["con_id"] for w in result["windows"]} == {6}


@pytest.mark.asyncio
async def test_query_workspaces(fake):
    fake.query_replies[ipc.GET_WORKSPACES] = [
        {"num": 3, "name": "3", "output": "DisplayPort-1", "focused": True, "visible": True, "urgent": False}
    ]
    result = json.loads(await i3_query(what="workspaces"))
    assert result["workspaces"][0]["name"] == "3"


@pytest.mark.asyncio
async def test_query_version(fake):
    fake.query_replies[ipc.GET_VERSION] = {"human_readable": "4.25.1"}
    result = json.loads(await i3_query(what="version"))
    assert result["version"]["human_readable"] == "4.25.1"


@pytest.mark.asyncio
async def test_query_config_omits_body_unless_asked(fake):
    fake.query_replies[ipc.GET_CONFIG] = {"config": "x" * 5000, "included_configs": []}
    result = json.loads(await i3_query(what="config"))
    assert "config" not in result
    assert result["config_length"] == 5000
    full = json.loads(await i3_query(what="config", include_config_body=True))
    assert len(full["config"]) == 5000


@pytest.mark.asyncio
async def test_query_bar_config_by_id(fake):
    fake.query_replies[ipc.GET_BAR_CONFIG] = {"id": "bar-0", "position": "top"}
    result = json.loads(await i3_query(what="bar_config", bar_id="bar-0"))
    assert result["bar_config"]["position"] == "top"


@pytest.mark.asyncio
async def test_query_markdown_format(fake):
    fake.query_replies[ipc.GET_TREE] = sample_tree()
    out = await i3_query(what="tree", response_format=ResponseFormat.MARKDOWN)
    assert "Firefox" in out
    assert "con_id" in out
```

Add `asyncio_mode = "auto"` so the async tests run without per-test markers.
Append to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

and add `pytest-asyncio>=0.23` to the `dev` extra.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/test_tools_query.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'i3mcp.server'`

- [ ] **Step 3: Write `i3mcp/server.py`**

```python
"""The MCPServer instance. Tool modules import `mcp` and decorate it."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("i3_mcp")


def main() -> None:
    from . import tools  # noqa: F401  (importing registers every tool)

    mcp.run()
```

- [ ] **Step 4: Write `i3mcp/tools/__init__.py`**

```python
"""Importing this package registers every tool on the server."""

from . import (  # noqa: F401
    bar,
    focus,
    gaps,
    kill,
    layout,
    mark,
    move,
    query,
    resize,
    scratchpad,
    window,
    wm,
    workspace,
)
```

Note: this import list references modules created in later tasks. Until Task 13
lands, trim the list to the modules that exist, then restore it in full.

- [ ] **Step 5: Write `i3mcp/tools/query.py`**

```python
"""Read-only inspection of i3 state."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import Field

from .. import ipc, render, tree
from ..enums import ResponseFormat
from ..ipc import I3Error
from ..server import mcp

_SIMPLE_QUERIES = {
    "workspaces": (ipc.GET_WORKSPACES, "workspaces"),
    "outputs": (ipc.GET_OUTPUTS, "outputs"),
    "marks": (ipc.GET_MARKS, "marks"),
    "version": (ipc.GET_VERSION, "version"),
    "binding_modes": (ipc.GET_BINDING_MODES, "binding_modes"),
    "binding_state": (ipc.GET_BINDING_STATE, "binding_state"),
}


@mcp.tool(
    name="i3_query",
    annotations={
        "title": "Query i3 State",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def i3_query(
    what: Literal[
        "tree",
        "focused",
        "scratchpad",
        "workspaces",
        "outputs",
        "marks",
        "version",
        "config",
        "bar_config",
        "binding_modes",
        "binding_state",
    ] = Field(default="tree", description="Which piece of i3 state to read."),
    window_class: str | None = Field(
        default=None, description="tree/scratchpad: case-insensitive substring of the window class."
    ),
    title: str | None = Field(
        default=None, description="tree/scratchpad: case-insensitive substring of the window title."
    ),
    instance: str | None = Field(default=None, description="tree/scratchpad: substring of the instance."),
    window_type: str | None = Field(default=None, description="tree: exact window type, e.g. 'dialog'."),
    workspace: str | None = Field(default=None, description="tree: exact workspace name."),
    mark: str | None = Field(default=None, description="tree: exact mark on the container."),
    floating: bool | None = Field(default=None, description="tree: restrict to floating or tiling windows."),
    urgent: bool | None = Field(default=None, description="tree: restrict to urgent windows."),
    include_docks: bool = Field(default=False, description="tree: include i3bar and other dock windows."),
    bar_id: str | None = Field(
        default=None, description="bar_config: which bar. Omit to list bar ids."
    ),
    include_config_body: bool = Field(
        default=False, description="config: include the full config text, which can be large."
    ),
    response_format: ResponseFormat = Field(
        default=ResponseFormat.JSON, description="json (default) or markdown."
    ),
) -> str:
    """Read i3 state: the window tree, workspaces, outputs, marks, config, bars, or binding modes.

    Window records carry con_id, workspace and output, which is what the other
    tools' `criteria` argument expects.
    """
    conn = ipc.get_connection()
    try:
        if what in ("tree", "focused", "scratchpad"):
            records = tree.walk_windows(conn.query(ipc.GET_TREE))
            if what == "focused":
                found = tree.find_focused(records)
                if response_format == ResponseFormat.MARKDOWN:
                    return render.markdown(render.window_lines([found] if found else []))
                return render.ok(window=found)
            filtered = tree.filter_windows(
                records,
                window_class=window_class,
                title=title,
                instance=instance,
                window_type=window_type,
                workspace=workspace,
                mark=mark,
                floating=floating,
                urgent=urgent,
                scratchpad=True if what == "scratchpad" else None,
                include_docks=include_docks,
            )
            if response_format == ResponseFormat.MARKDOWN:
                header = f"### Windows ({len(filtered)} found)\n\n"
                return render.markdown(header + render.window_lines(filtered))
            return render.json_list("windows", filtered)

        if what == "config":
            data = conn.query(ipc.GET_CONFIG)
            body = data.get("config", "")
            if include_config_body:
                return render.ok(config=body, included_configs=data.get("included_configs", []))
            return render.ok(
                config_length=len(body),
                config_preview=body[:500],
                included_configs=data.get("included_configs", []),
                hint="Pass include_config_body=true for the full text.",
            )

        if what == "bar_config":
            payload = bar_id or ""
            data = conn.query(ipc.GET_BAR_CONFIG, payload)
            if bar_id:
                return render.ok(bar_config=data)
            return render.ok(bar_ids=data, hint="Pass bar_id to read one bar's configuration.")

        msg_type, key = _SIMPLE_QUERIES[what]
        data = conn.query(msg_type)
        if isinstance(data, list):
            return render.json_list(key, data)
        return render.ok(**{key: data})
    except I3Error as exc:
        return render.err(str(exc), what=what)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/ -v`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add i3mcp/server.py i3mcp/tools/ tests/test_tools_query.py pyproject.toml
git commit -m "feat: MCPServer instance and consolidated i3_query tool"
```

---

### Task 6: `i3_focus`

**Files:**
- Create: `i3mcp/tools/focus.py`, `tests/test_tools_focus.py`
- Modify: `i3mcp/tools/__init__.py`

**Interfaces:**
- Consumes: `render.run`, `criteria.WindowCriteria`, `criteria.prefix_command`.
- Produces: `i3mcp.tools.focus.i3_focus(...)`

Commands this tool must be able to emit, all verified on i3 4.25.1:

| Input | Emitted |
|-------|---------|
| `direction="left"` | `focus left` |
| `target="parent"` | `focus parent` |
| `target="floating"` | `focus floating` |
| `sibling="next"` | `focus next sibling` |
| `cycle="prev"` | `focus prev` |
| `output="HDMI-1"` | `focus output HDMI-1` |
| `output="right"` | `focus output right` |
| `criteria={window_class:"firefox"}` | `[class="^\Qfirefox\E$"] focus` |
| `criteria={...}, focus_workspace=True` | `[class="^\Qfirefox\E$"] focus workspace` |

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_focus.py`:

```python
import json

from i3mcp.criteria import WindowCriteria
from i3mcp.tools.focus import i3_focus


async def test_focus_direction(fake):
    await i3_focus(direction="left")
    assert fake.last_command == "focus left"


async def test_focus_parent(fake):
    await i3_focus(target="parent")
    assert fake.last_command == "focus parent"


async def test_focus_floating_mode(fake):
    await i3_focus(target="floating")
    assert fake.last_command == "focus floating"


async def test_focus_next_sibling(fake):
    await i3_focus(sibling="next")
    assert fake.last_command == "focus next sibling"


async def test_focus_cycle_prev(fake):
    await i3_focus(cycle="prev")
    assert fake.last_command == "focus prev"


async def test_focus_output_by_name(fake):
    await i3_focus(output="HDMI-1")
    assert fake.last_command == "focus output HDMI-1"


async def test_focus_by_criteria(fake):
    await i3_focus(criteria=WindowCriteria(window_class="firefox"))
    assert fake.last_command == r'[class="^\Qfirefox\E$"] focus'


async def test_focus_workspace_of_matching_window(fake):
    await i3_focus(criteria=WindowCriteria(con_mark="term"), focus_workspace=True)
    assert fake.last_command == r'[con_mark="^\Qterm\E$"] focus workspace'


async def test_focus_urgent_uses_i3_vocabulary(fake):
    await i3_focus(criteria=WindowCriteria(urgent="latest"))
    assert fake.last_command == "[urgent=latest] focus"


async def test_focus_requires_an_argument(fake):
    result = json.loads(await i3_focus())
    assert result["success"] is False
    assert fake.commands == []


async def test_focus_rejects_conflicting_arguments(fake):
    result = json.loads(await i3_focus(direction="left", target="parent"))
    assert result["success"] is False
    assert fake.commands == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/test_tools_focus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'i3mcp.tools.focus'`

- [ ] **Step 3: Write `i3mcp/tools/focus.py`**

```python
"""Move keyboard focus."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria, prefix_command
from ..enums import Direction
from ..server import mcp


@mcp.tool(
    name="i3_focus",
    annotations={
        "title": "Focus i3 Window or Output",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_focus(
    direction: Direction | None = Field(
        default=None, description="Focus the neighbouring window: left, right, up, or down."
    ),
    target: Literal["parent", "child", "floating", "tiling", "mode_toggle"] | None = Field(
        default=None,
        description="Focus the parent or child container, or switch between floating and tiling.",
    ),
    sibling: Literal["next", "prev"] | None = Field(
        default=None, description="Focus the next or previous sibling container."
    ),
    cycle: Literal["next", "prev"] | None = Field(
        default=None, description="Focus the next or previous container in the tree."
    ),
    output: str | None = Field(
        default=None,
        description="Focus an output by name (e.g. 'HDMI-1') or relative position "
        "(left/right/up/down/current/primary/nonprimary/next).",
    ),
    criteria: WindowCriteria | None = Field(
        default=None, description="Focus the window matching these criteria."
    ),
    focus_workspace: bool = Field(
        default=False,
        description="With criteria: focus the matching window's workspace rather than the window.",
    ),
) -> str:
    """Focus a window by direction, container relationship, criteria, or output.

    Exactly one of direction, target, sibling, cycle, output or criteria.
    """
    chosen = [
        name
        for name, value in (
            ("direction", direction),
            ("target", target),
            ("sibling", sibling),
            ("cycle", cycle),
            ("output", output),
            ("criteria", criteria if criteria and not criteria.is_empty() else None),
        )
        if value is not None
    ]
    if not chosen:
        return render.err(
            "Specify one of: direction, target, sibling, cycle, output, or criteria."
        )
    if len(chosen) > 1:
        return render.err(f"Specify only one of these at a time, got: {', '.join(chosen)}.")

    if direction is not None:
        return render.run(f"focus {direction.value}")
    if target is not None:
        return render.run(f"focus {target}")
    if sibling is not None:
        return render.run(f"focus {sibling} sibling")
    if cycle is not None:
        return render.run(f"focus {cycle}")
    if output is not None:
        return render.run(f"focus output {output}")

    verb = "focus workspace" if focus_workspace else "focus"
    return render.run(prefix_command(criteria, verb))
```

- [ ] **Step 4: Add `focus` to `i3mcp/tools/__init__.py`**

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/ -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add i3mcp/tools/focus.py i3mcp/tools/__init__.py tests/test_tools_focus.py
git commit -m "feat: i3_focus with criteria, siblings, and focus-workspace"
```

---

### Task 7: `i3_move` and `i3_resize`

**Files:**
- Create: `i3mcp/tools/move.py`, `i3mcp/tools/resize.py`, `tests/test_tools_move.py`, `tests/test_tools_resize.py`
- Modify: `i3mcp/tools/__init__.py`

**Interfaces:**
- Consumes: `render.run`, `WindowCriteria`, `prefix_command`, `Direction`, `Unit`.
- Produces: `i3mcp.tools.move.i3_move(...)`, `i3mcp.tools.resize.i3_resize(...)`

Command shapes, from the i3 userguide and verified on 4.25.1:

```
move <left|right|up|down> [<amount> [px|ppt]]
move [absolute] position <x> [px|ppt] <y> [px|ppt]
move [absolute] position center
move position mouse
move [--no-auto-back-and-forth] container to workspace <name>
move [--no-auto-back-and-forth] container to workspace number <n>
move container to workspace prev|next|current
move container to output <name|left|right|up|down|current|primary|nonprimary|next>
move workspace to output <name|...>
move container to mark <mark>
move scratchpad
swap container with id|con_id|mark <arg>

resize grow|shrink <direction> [<px> px [or <ppt> ppt]]
resize set [width] <w> [px|ppt] [height] <h> [px|ppt]
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_move.py`:

```python
import json

from i3mcp.criteria import WindowCriteria
from i3mcp.tools.move import i3_move


async def test_move_direction_default_amount(fake):
    await i3_move(direction="left")
    assert fake.last_command == "move left"


async def test_move_direction_with_px(fake):
    await i3_move(direction="right", amount=30)
    assert fake.last_command == "move right 30 px"


async def test_move_direction_with_ppt(fake):
    await i3_move(direction="up", amount=10, unit="ppt")
    assert fake.last_command == "move up 10 ppt"


async def test_move_to_workspace_by_name(fake):
    await i3_move(workspace="web")
    assert fake.last_command == 'move container to workspace "web"'


async def test_move_to_workspace_by_number(fake):
    await i3_move(workspace="3", by_number=True)
    assert fake.last_command == "move container to workspace number 3"


async def test_move_to_relative_workspace(fake):
    await i3_move(workspace="next")
    assert fake.last_command == "move container to workspace next"


async def test_move_and_follow_emits_two_commands(fake):
    await i3_move(workspace="web", follow=True)
    assert fake.last_command == 'move container to workspace "web"; workspace "web"'


async def test_move_to_output(fake):
    await i3_move(output="HDMI-1")
    assert fake.last_command == "move container to output HDMI-1"


async def test_move_workspace_to_output(fake):
    await i3_move(output="HDMI-1", move_workspace=True)
    assert fake.last_command == "move workspace to output HDMI-1"


async def test_move_absolute_position(fake):
    await i3_move(position_x=100, position_y=200)
    assert fake.last_command == "move absolute position 100 px 200 px"


async def test_move_center(fake):
    await i3_move(center=True)
    assert fake.last_command == "move absolute position center"


async def test_move_to_mouse(fake):
    await i3_move(to_mouse=True)
    assert fake.last_command == "move position mouse"


async def test_move_to_mark(fake):
    await i3_move(to_mark="anchor")
    assert fake.last_command == 'move container to mark "anchor"'


async def test_move_to_scratchpad(fake):
    await i3_move(to_scratchpad=True)
    assert fake.last_command == "move scratchpad"


async def test_move_with_criteria_prefixes(fake):
    await i3_move(criteria=WindowCriteria(con_id=42), workspace="web")
    assert fake.last_command == '[con_id=42] move container to workspace "web"'


async def test_swap_with_mark(fake):
    await i3_move(swap_with_mark="other")
    assert fake.last_command == 'swap container with mark "other"'


async def test_swap_with_con_id(fake):
    await i3_move(swap_with_con_id=99)
    assert fake.last_command == "swap container with con_id 99"


async def test_move_requires_a_destination(fake):
    result = json.loads(await i3_move())
    assert result["success"] is False
    assert fake.commands == []


async def test_move_rejects_two_destinations(fake):
    result = json.loads(await i3_move(workspace="web", center=True))
    assert result["success"] is False
    assert fake.commands == []


async def test_move_rejects_half_a_position(fake):
    result = json.loads(await i3_move(position_x=100))
    assert result["success"] is False
    assert fake.commands == []
```

Create `tests/test_tools_resize.py`:

```python
import json

from i3mcp.criteria import WindowCriteria
from i3mcp.tools.resize import i3_resize


async def test_resize_grow_width_px(fake):
    await i3_resize(mode="grow", direction="right", amount=50)
    assert fake.last_command == "resize grow right 50 px"


async def test_resize_shrink_ppt(fake):
    await i3_resize(mode="shrink", direction="up", amount=5, unit="ppt")
    assert fake.last_command == "resize shrink up 5 ppt"


async def test_resize_set_both_dimensions_px(fake):
    await i3_resize(mode="set", width=800, height=600)
    assert fake.last_command == "resize set width 800 px height 600 px"


async def test_resize_set_width_only_ppt(fake):
    await i3_resize(mode="set", width=60, unit="ppt")
    assert fake.last_command == "resize set width 60 ppt"


async def test_resize_set_does_not_force_floating(fake):
    await i3_resize(mode="set", width=800, height=600)
    assert "floating enable" not in fake.last_command


async def test_resize_with_criteria(fake):
    await i3_resize(criteria=WindowCriteria(con_mark="term"), mode="grow", direction="right", amount=10)
    assert fake.last_command == r'[con_mark="^\Qterm\E$"] resize grow right 10 px'


async def test_resize_grow_requires_direction(fake):
    result = json.loads(await i3_resize(mode="grow", amount=10))
    assert result["success"] is False
    assert fake.commands == []


async def test_resize_set_requires_a_dimension(fake):
    result = json.loads(await i3_resize(mode="set"))
    assert result["success"] is False
    assert fake.commands == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/test_tools_move.py tests/test_tools_resize.py -v`
Expected: FAIL — modules not found

- [ ] **Step 3: Write `i3mcp/tools/move.py`**

```python
"""Move containers and workspaces."""

from __future__ import annotations

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria, escape_value, prefix_command
from ..enums import Direction, Unit
from ..server import mcp

_RELATIVE_WORKSPACES = {"next", "prev", "current", "next_on_output", "prev_on_output"}


@mcp.tool(
    name="i3_move",
    annotations={
        "title": "Move i3 Container",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_move(
    criteria: WindowCriteria | None = Field(
        default=None, description="Which window to move. Omit to move the focused one."
    ),
    direction: Direction | None = Field(default=None, description="Move one step in this direction."),
    amount: int | None = Field(default=None, description="With direction: how far to move.", ge=1),
    unit: Unit = Field(default=Unit.PX, description="Unit for amount and position: px or ppt."),
    workspace: str | None = Field(
        default=None,
        description="Target workspace name, or next/prev/current for a relative move.",
    ),
    by_number: bool = Field(
        default=False,
        description="Treat workspace as a number. Use this with named workspaces like '3: web', "
        "where plain 'workspace 3' would create a new one instead of switching.",
    ),
    follow: bool = Field(default=False, description="Switch to the workspace after moving."),
    no_auto_back_and_forth: bool = Field(
        default=False, description="Suppress i3's automatic back_and_forth behaviour."
    ),
    output: str | None = Field(
        default=None, description="Target output name or relative position."
    ),
    move_workspace: bool = Field(
        default=False, description="With output: move the whole workspace instead of the container."
    ),
    position_x: int | None = Field(default=None, description="Absolute X for a floating window."),
    position_y: int | None = Field(default=None, description="Absolute Y for a floating window."),
    center: bool = Field(default=False, description="Centre a floating window on its output."),
    to_mouse: bool = Field(default=False, description="Move a floating window to the pointer."),
    to_mark: str | None = Field(default=None, description="Move onto the container with this mark."),
    to_scratchpad: bool = Field(default=False, description="Move the container to the scratchpad."),
    swap_with_mark: str | None = Field(default=None, description="Swap with the container holding this mark."),
    swap_with_con_id: int | None = Field(default=None, description="Swap with this container id."),
    swap_with_window_id: int | None = Field(default=None, description="Swap with this X11 window id."),
) -> str:
    """Move a container to a workspace, output, position, mark, or the scratchpad; or swap two containers.

    Pick exactly one destination. Without `criteria` the focused container moves.
    """
    has_position = position_x is not None or position_y is not None
    destinations = {
        "direction": direction is not None,
        "workspace": workspace is not None,
        "output": output is not None,
        "position": has_position,
        "center": center,
        "to_mouse": to_mouse,
        "to_mark": to_mark is not None,
        "to_scratchpad": to_scratchpad,
        "swap": swap_with_mark is not None
        or swap_with_con_id is not None
        or swap_with_window_id is not None,
    }
    chosen = [name for name, present in destinations.items() if present]
    if not chosen:
        return render.err(
            "Specify a destination: direction, workspace, output, position, center, "
            "to_mouse, to_mark, to_scratchpad, or a swap_with_* argument."
        )
    if len(chosen) > 1:
        return render.err(f"Specify only one destination, got: {', '.join(chosen)}.")

    if direction is not None:
        command = f"move {direction.value}"
        if amount is not None:
            command += f" {amount} {unit.value}"
    elif workspace is not None:
        flag = "--no-auto-back-and-forth " if no_auto_back_and_forth else ""
        if workspace in _RELATIVE_WORKSPACES:
            command = f"move container to workspace {workspace}"
        elif by_number:
            command = f"move {flag}container to workspace number {workspace}"
        else:
            command = f'move {flag}container to workspace "{escape_value(workspace)}"'
    elif output is not None:
        subject = "workspace" if move_workspace else "container"
        command = f"move {subject} to output {output}"
    elif has_position:
        if position_x is None or position_y is None:
            return render.err("Give both position_x and position_y, or neither.")
        command = (
            f"move absolute position {position_x} {unit.value} {position_y} {unit.value}"
        )
    elif center:
        command = "move absolute position center"
    elif to_mouse:
        command = "move position mouse"
    elif to_mark is not None:
        command = f'move container to mark "{escape_value(to_mark)}"'
    elif to_scratchpad:
        command = "move scratchpad"
    else:
        if swap_with_mark is not None:
            command = f'swap container with mark "{escape_value(swap_with_mark)}"'
        elif swap_with_con_id is not None:
            command = f"swap container with con_id {swap_with_con_id}"
        else:
            command = f"swap container with id {swap_with_window_id}"

    full = prefix_command(criteria, command)
    if follow and workspace is not None:
        if workspace in _RELATIVE_WORKSPACES:
            follow_cmd = f"workspace {workspace}"
        elif by_number:
            follow_cmd = f"workspace number {workspace}"
        else:
            follow_cmd = f'workspace "{escape_value(workspace)}"'
        full = f"{full}; {follow_cmd}"
    return render.run(full)
```

- [ ] **Step 4: Write `i3mcp/tools/resize.py`**

```python
"""Resize containers."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria, prefix_command
from ..enums import Direction, Unit
from ..server import mcp


@mcp.tool(
    name="i3_resize",
    annotations={
        "title": "Resize i3 Container",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_resize(
    mode: Literal["grow", "shrink", "set"] = Field(
        description="grow or shrink by an amount, or set an absolute size."
    ),
    criteria: WindowCriteria | None = Field(
        default=None, description="Which window to resize. Omit for the focused one."
    ),
    direction: Direction | None = Field(
        default=None, description="Required for grow and shrink: which edge moves."
    ),
    amount: int = Field(default=10, description="How much to grow or shrink.", ge=1),
    width: int | None = Field(default=None, description="For mode=set: target width."),
    height: int | None = Field(default=None, description="For mode=set: target height."),
    unit: Unit = Field(
        default=Unit.PX,
        description="px for pixels, ppt for percent of the parent container.",
    ),
) -> str:
    """Grow, shrink, or set the size of a container.

    ppt works on tiled containers; px suits floating ones.
    """
    if mode == "set":
        if width is None and height is None:
            return render.err("mode=set needs width, height, or both.")
        parts = ["resize set"]
        if width is not None:
            parts.append(f"width {width} {unit.value}")
        if height is not None:
            parts.append(f"height {height} {unit.value}")
        command = " ".join(parts)
    else:
        if direction is None:
            return render.err(f"mode={mode} needs a direction.")
        command = f"resize {mode} {direction.value} {amount} {unit.value}"

    return render.run(prefix_command(criteria, command))
```

- [ ] **Step 5: Add `move` and `resize` to `i3mcp/tools/__init__.py`**

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/ -v`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add i3mcp/tools/move.py i3mcp/tools/resize.py i3mcp/tools/__init__.py tests/test_tools_move.py tests/test_tools_resize.py
git commit -m "feat: i3_move and i3_resize with ppt units and criteria"
```

---

### Task 8: `i3_kill` and `i3_window`

**Files:**
- Create: `i3mcp/tools/kill.py`, `i3mcp/tools/window.py`, `tests/test_tools_window.py`
- Modify: `i3mcp/tools/__init__.py`

**Interfaces:**
- Consumes: `render.run`, `WindowCriteria`, `prefix_command`, `escape_value`.
- Produces: `i3mcp.tools.kill.i3_kill(...)`, `i3mcp.tools.window.i3_window(...)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_window.py`:

```python
import json

from i3mcp.criteria import WindowCriteria
from i3mcp.tools.kill import i3_kill
from i3mcp.tools.window import i3_window


async def test_kill_focused(fake):
    await i3_kill()
    assert fake.last_command == "kill"


async def test_kill_by_criteria(fake):
    await i3_kill(criteria=WindowCriteria(con_id=7))
    assert fake.last_command == "[con_id=7] kill"


async def test_floating_enable(fake):
    await i3_window(floating="enable")
    assert fake.last_command == "floating enable"


async def test_floating_toggle_with_criteria(fake):
    await i3_window(criteria=WindowCriteria(window_class="Thunar"), floating="toggle")
    assert fake.last_command == r'[class="^\QThunar\E$"] floating toggle'


async def test_sticky(fake):
    await i3_window(sticky="enable")
    assert fake.last_command == "sticky enable"


async def test_fullscreen_toggle(fake):
    await i3_window(fullscreen="toggle")
    assert fake.last_command == "fullscreen toggle"


async def test_fullscreen_global(fake):
    await i3_window(fullscreen="enable", fullscreen_global=True)
    assert fake.last_command == "fullscreen enable global"


async def test_border_pixel_with_width(fake):
    await i3_window(border="pixel", border_width=3)
    assert fake.last_command == "border pixel 3"


async def test_border_none_ignores_width(fake):
    await i3_window(border="none", border_width=3)
    assert fake.last_command == "border none"


async def test_border_toggle(fake):
    await i3_window(border="toggle")
    assert fake.last_command == "border toggle"


async def test_title_format(fake):
    await i3_window(title_format="%title (%class)")
    assert fake.last_command == 'title_format "%title (%class)"'


async def test_title_window_icon_on(fake):
    await i3_window(title_window_icon="on")
    assert fake.last_command == "title_window_icon on"


async def test_title_window_icon_with_padding(fake):
    await i3_window(title_window_icon="on", title_window_icon_padding=2)
    assert fake.last_command == "title_window_icon on padding 2 px"


async def test_multiple_properties_chain_with_commas(fake):
    await i3_window(floating="enable", sticky="enable")
    assert fake.last_command == "floating enable, sticky enable"


async def test_criteria_applies_once_to_a_chain(fake):
    await i3_window(criteria=WindowCriteria(con_id=5), floating="enable", sticky="enable")
    assert fake.last_command == "[con_id=5] floating enable, sticky enable"


async def test_window_requires_a_property(fake):
    result = json.loads(await i3_window())
    assert result["success"] is False
    assert fake.commands == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/test_tools_window.py -v`
Expected: FAIL — modules not found

- [ ] **Step 3: Write `i3mcp/tools/kill.py`**

```python
"""Close windows."""

from __future__ import annotations

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria, prefix_command
from ..server import mcp


@mcp.tool(
    name="i3_kill",
    annotations={
        "title": "Close i3 Window",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_kill(
    criteria: WindowCriteria | None = Field(
        default=None,
        description="Which window to close. Omit to close the focused one.",
    ),
) -> str:
    """Close a window. The application may prompt to save first.

    Destructive: confirm the target before calling without criteria.
    """
    return render.run(prefix_command(criteria, "kill"))
```

- [ ] **Step 4: Write `i3mcp/tools/window.py`**

```python
"""Window properties: floating, sticky, fullscreen, border, title."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria, escape_value, prefix_command
from ..server import mcp

Toggle = Literal["enable", "disable", "toggle"]


@mcp.tool(
    name="i3_window",
    annotations={
        "title": "Set i3 Window Properties",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_window(
    criteria: WindowCriteria | None = Field(
        default=None, description="Which window to change. Omit for the focused one."
    ),
    floating: Toggle | None = Field(default=None, description="Float, tile, or toggle the window."),
    sticky: Toggle | None = Field(
        default=None, description="Keep a floating window visible on every workspace."
    ),
    fullscreen: Toggle | None = Field(default=None, description="Fullscreen the window."),
    fullscreen_global: bool = Field(
        default=False, description="With fullscreen: span every output, not just the current one."
    ),
    border: Literal["normal", "pixel", "none", "toggle"] | None = Field(
        default=None, description="Border style. 'normal' keeps the title bar, 'pixel' drops it."
    ),
    border_width: int | None = Field(
        default=None, description="Border width in pixels, for normal and pixel only.", ge=0, le=50
    ),
    title_format: str | None = Field(
        default=None,
        description="Title bar template, e.g. '%title (%class)'. Placeholders: %title, %class, %instance, %machine, %shell.",
    ),
    title_window_icon: Literal["on", "off", "all"] | None = Field(
        default=None, description="Show the application icon in the title bar."
    ),
    title_window_icon_padding: int | None = Field(
        default=None, description="Padding in pixels around the title bar icon.", ge=0
    ),
) -> str:
    """Set floating, sticky, fullscreen, border, or title properties on a window.

    Several properties in one call are applied as a single chained i3 command.
    """
    parts: list[str] = []
    if floating is not None:
        parts.append(f"floating {floating}")
    if sticky is not None:
        parts.append(f"sticky {sticky}")
    if fullscreen is not None:
        parts.append(f"fullscreen {fullscreen}" + (" global" if fullscreen_global else ""))
    if border is not None:
        if border in ("normal", "pixel") and border_width is not None:
            parts.append(f"border {border} {border_width}")
        else:
            parts.append(f"border {border}")
    if title_format is not None:
        parts.append(f'title_format "{escape_value(title_format)}"')
    if title_window_icon is not None:
        command = f"title_window_icon {title_window_icon}"
        if title_window_icon_padding is not None:
            command += f" padding {title_window_icon_padding} px"
        parts.append(command)

    if not parts:
        return render.err(
            "Specify at least one of: floating, sticky, fullscreen, border, "
            "title_format, or title_window_icon."
        )

    return render.run(prefix_command(criteria, ", ".join(parts)))
```

- [ ] **Step 5: Add `kill` and `window` to `i3mcp/tools/__init__.py`**

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/ -v`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add i3mcp/tools/kill.py i3mcp/tools/window.py i3mcp/tools/__init__.py tests/test_tools_window.py
git commit -m "feat: i3_kill and i3_window with criteria targeting"
```

---

### Task 9: `i3_layout` and `i3_mark`

**Files:**
- Create: `i3mcp/tools/layout.py`, `i3mcp/tools/mark.py`, `tests/test_tools_layout.py`, `tests/test_tools_mark.py`
- Modify: `i3mcp/tools/__init__.py`

**Interfaces:**
- Consumes: `render.run`, `WindowCriteria`, `prefix_command`, `escape_value`.
- Produces: `i3mcp.tools.layout.i3_layout(...)`, `i3mcp.tools.mark.i3_mark(...)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_layout.py`:

```python
import json

from i3mcp.criteria import WindowCriteria
from i3mcp.tools.layout import i3_layout


async def test_layout_tabbed(fake):
    await i3_layout(layout="tabbed")
    assert fake.last_command == "layout tabbed"


async def test_layout_toggle_split(fake):
    await i3_layout(layout="toggle split")
    assert fake.last_command == "layout toggle split"


async def test_split_horizontal(fake):
    await i3_layout(split="horizontal")
    assert fake.last_command == "split horizontal"


async def test_split_toggle(fake):
    await i3_layout(split="toggle")
    assert fake.last_command == "split toggle"


async def test_layout_with_criteria(fake):
    await i3_layout(criteria=WindowCriteria(con_id=3), layout="stacking")
    assert fake.last_command == "[con_id=3] layout stacking"


async def test_layout_requires_an_argument(fake):
    result = json.loads(await i3_layout())
    assert result["success"] is False
    assert fake.commands == []
```

Create `tests/test_tools_mark.py`:

```python
import json

from i3mcp.criteria import WindowCriteria
from i3mcp.tools.mark import i3_mark


async def test_mark_replace_is_default(fake):
    await i3_mark(mark="term")
    assert fake.last_command == 'mark --replace "term"'


async def test_mark_add(fake):
    await i3_mark(mark="important", mode="add")
    assert fake.last_command == 'mark --add "important"'


async def test_mark_toggle(fake):
    await i3_mark(mark="pinned", mode="toggle")
    assert fake.last_command == 'mark --toggle "pinned"'


async def test_mark_with_criteria(fake):
    await i3_mark(criteria=WindowCriteria(window_class="firefox"), mark="browser")
    assert fake.last_command == r'[class="^\Qfirefox\E$"] mark --replace "browser"'


async def test_unmark_specific(fake):
    await i3_mark(unmark="term")
    assert fake.last_command == 'unmark "term"'


async def test_unmark_all(fake):
    await i3_mark(unmark_all=True)
    assert fake.last_command == "unmark"


async def test_mark_escapes_quotes(fake):
    await i3_mark(mark='say "hi"')
    assert fake.last_command == r'mark --replace "say \"hi\""'


async def test_mark_requires_an_argument(fake):
    result = json.loads(await i3_mark())
    assert result["success"] is False
    assert fake.commands == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/test_tools_layout.py tests/test_tools_mark.py -v`
Expected: FAIL — modules not found

- [ ] **Step 3: Write `i3mcp/tools/layout.py`**

```python
"""Container layout and split orientation."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria, prefix_command
from ..server import mcp


@mcp.tool(
    name="i3_layout",
    annotations={
        "title": "Set i3 Layout or Split",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_layout(
    criteria: WindowCriteria | None = Field(
        default=None, description="Which container to change. Omit for the focused one."
    ),
    layout: Literal[
        "default", "tabbed", "stacking", "splitv", "splith", "toggle split", "toggle all"
    ] | None = Field(default=None, description="Arrangement for the container's children."),
    split: Literal["horizontal", "vertical", "toggle"] | None = Field(
        default=None, description="Orientation for the next window opened here."
    ),
) -> str:
    """Change a container's layout, or set the split orientation for the next window.

    Give layout, split, or both.
    """
    parts = []
    if layout is not None:
        parts.append(f"layout {layout}")
    if split is not None:
        parts.append(f"split {split}")
    if not parts:
        return render.err("Specify layout, split, or both.")
    return render.run(prefix_command(criteria, ", ".join(parts)))
```

- [ ] **Step 4: Write `i3mcp/tools/mark.py`**

```python
"""Set and remove i3 marks."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import WindowCriteria, escape_value, prefix_command
from ..server import mcp


@mcp.tool(
    name="i3_mark",
    annotations={
        "title": "Mark or Unmark i3 Window",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_mark(
    criteria: WindowCriteria | None = Field(
        default=None, description="Which window to mark. Omit for the focused one."
    ),
    mark: str | None = Field(
        default=None, description="Mark to set. Marks are the stable way to address a window later."
    ),
    mode: Literal["replace", "add", "toggle"] = Field(
        default="replace",
        description="replace clears other marks, add keeps them, toggle flips this one.",
    ),
    unmark: str | None = Field(default=None, description="Mark to remove."),
    unmark_all: bool = Field(default=False, description="Remove every mark from the target."),
) -> str:
    """Set or remove a mark on a window. Marks survive moves and are the best criteria handle.

    Give one of: mark, unmark, or unmark_all.
    """
    chosen = [
        name
        for name, present in (("mark", mark is not None), ("unmark", unmark is not None), ("unmark_all", unmark_all))
        if present
    ]
    if not chosen:
        return render.err("Specify one of: mark, unmark, or unmark_all.")
    if len(chosen) > 1:
        return render.err(f"Specify only one of these at a time, got: {', '.join(chosen)}.")

    if mark is not None:
        command = f'mark --{mode} "{escape_value(mark)}"'
    elif unmark is not None:
        command = f'unmark "{escape_value(unmark)}"'
    else:
        command = "unmark"

    return render.run(prefix_command(criteria, command))
```

- [ ] **Step 5: Add `layout` and `mark` to `i3mcp/tools/__init__.py`**

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/ -v`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add i3mcp/tools/layout.py i3mcp/tools/mark.py i3mcp/tools/__init__.py tests/test_tools_layout.py tests/test_tools_mark.py
git commit -m "feat: i3_layout and i3_mark with criteria targeting"
```

---

### Task 10: `i3_workspace`

**Files:**
- Create: `i3mcp/tools/workspace.py`, `tests/test_tools_workspace.py`
- Modify: `i3mcp/tools/__init__.py`

**Interfaces:**
- Consumes: `render.run`, `render.ok`, `render.err`, `ipc.get_connection`, `escape_value`.
- Produces: `i3mcp.tools.workspace.i3_workspace(...)`

The `number` distinction matters: with a workspace named `"3: web"`, plain
`workspace 3` creates a **new** workspace called `3`, while
`workspace number 3` switches to the existing one.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_workspace.py`:

```python
import json

from i3mcp import ipc
from i3mcp.tools.workspace import i3_workspace


async def test_switch_by_name(fake):
    await i3_workspace(action="switch", name="web")
    assert fake.last_command == 'workspace "web"'


async def test_switch_by_number(fake):
    await i3_workspace(action="switch", name="3", by_number=True)
    assert fake.last_command == "workspace number 3"


async def test_switch_no_auto_back_and_forth(fake):
    await i3_workspace(action="switch", name="web", no_auto_back_and_forth=True)
    assert fake.last_command == 'workspace --no-auto-back-and-forth "web"'


async def test_navigate_next(fake):
    await i3_workspace(action="navigate", direction="next")
    assert fake.last_command == "workspace next"


async def test_navigate_back_and_forth(fake):
    await i3_workspace(action="navigate", direction="back_and_forth")
    assert fake.last_command == "workspace back_and_forth"


async def test_rename_focused(fake):
    await i3_workspace(action="rename", new_name="work")
    assert fake.last_command == 'rename workspace to "work"'


async def test_rename_specific(fake):
    await i3_workspace(action="rename", name="1", new_name="browser")
    assert fake.last_command == 'rename workspace "1" to "browser"'


async def test_move_to_output(fake):
    await i3_workspace(action="move_to_output", output="HDMI-1")
    assert fake.last_command == "move workspace to output HDMI-1"


async def test_move_named_workspace_to_output_switches_first(fake):
    await i3_workspace(action="move_to_output", name="3", output="HDMI-1")
    assert fake.last_command == 'workspace "3"; move workspace to output HDMI-1'


async def test_bulk_move_skips_unknown_workspaces(fake):
    fake.query_replies[ipc.GET_WORKSPACES] = [
        {"name": "1", "output": "eDP"},
        {"name": "2", "output": "eDP"},
    ]
    result = json.loads(
        await i3_workspace(action="bulk_move", names=["1", "2", "99"], output="HDMI-1")
    )
    assert result["moved"] == ["1", "2"]
    assert result["skipped"][0]["name"] == "99"
    assert len(fake.commands) == 2


async def test_bulk_move_preserves_one_workspace(fake):
    fake.query_replies[ipc.GET_WORKSPACES] = [
        {"name": "1", "output": "eDP"},
        {"name": "2", "output": "eDP"},
    ]
    result = json.loads(
        await i3_workspace(action="bulk_move", names=["1", "2"], output="HDMI-1", preserve="2")
    )
    assert result["moved"] == ["1"]


async def test_switch_requires_a_name(fake):
    result = json.loads(await i3_workspace(action="switch"))
    assert result["success"] is False
    assert fake.commands == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/test_tools_workspace.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write `i3mcp/tools/workspace.py`**

```python
"""Workspace switching, renaming, and output assignment."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import ipc, render
from ..criteria import escape_value
from ..ipc import I3Error
from ..server import mcp


def _workspace_ref(name: str, by_number: bool, no_auto_back_and_forth: bool = False) -> str:
    flag = "--no-auto-back-and-forth " if no_auto_back_and_forth else ""
    if by_number:
        return f"workspace {flag}number {name}"
    return f'workspace {flag}"{escape_value(name)}"'


@mcp.tool(
    name="i3_workspace",
    annotations={
        "title": "Manage i3 Workspaces",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_workspace(
    action: Literal["switch", "navigate", "rename", "move_to_output", "bulk_move"] = Field(
        description="What to do with the workspace."
    ),
    name: str | None = Field(
        default=None,
        description="Workspace name. For rename and move_to_output, omit to act on the focused one.",
    ),
    by_number: bool = Field(
        default=False,
        description="Treat name as a number. Needed for named workspaces like '3: web', where "
        "plain 'workspace 3' would create a new workspace instead of switching.",
    ),
    no_auto_back_and_forth: bool = Field(
        default=False, description="Suppress i3's automatic back_and_forth behaviour."
    ),
    direction: Literal[
        "next", "prev", "next_on_output", "prev_on_output", "back_and_forth"
    ] | None = Field(default=None, description="For action=navigate."),
    new_name: str | None = Field(default=None, description="For action=rename: the new name."),
    output: str | None = Field(
        default=None, description="For move_to_output and bulk_move: the target output."
    ),
    names: list[str] | None = Field(
        default=None, description="For action=bulk_move: workspaces to move."
    ),
    preserve: str | None = Field(
        default=None, description="For bulk_move: a workspace to leave where it is."
    ),
) -> str:
    """Switch, navigate, rename, or move workspaces between outputs.

    Use by_number=true whenever workspaces are named like '3: web'.
    """
    if action == "switch":
        if name is None:
            return render.err("action=switch needs a name.")
        return render.run(_workspace_ref(name, by_number, no_auto_back_and_forth))

    if action == "navigate":
        if direction is None:
            return render.err("action=navigate needs a direction.")
        return render.run(f"workspace {direction}")

    if action == "rename":
        if new_name is None:
            return render.err("action=rename needs new_name.")
        if name is None:
            return render.run(f'rename workspace to "{escape_value(new_name)}"')
        return render.run(
            f'rename workspace "{escape_value(name)}" to "{escape_value(new_name)}"'
        )

    if action == "move_to_output":
        if output is None:
            return render.err("action=move_to_output needs an output.")
        command = f"move workspace to output {output}"
        if name is not None:
            command = f"{_workspace_ref(name, by_number)}; {command}"
        return render.run(command)

    # bulk_move
    if not names or output is None:
        return render.err("action=bulk_move needs names and output.")
    try:
        existing = {ws["name"] for ws in ipc.get_connection().query(ipc.GET_WORKSPACES)}
    except I3Error as exc:
        return render.err(str(exc))

    moved: list[str] = []
    skipped: list[dict] = []
    for ws_name in names:
        if preserve is not None and ws_name == preserve:
            skipped.append({"name": ws_name, "reason": "preserved"})
            continue
        if ws_name not in existing:
            skipped.append({"name": ws_name, "reason": "does not exist"})
            continue
        command = f'{_workspace_ref(ws_name, False)}; move workspace to output {output}'
        try:
            ipc.get_connection().command(command)
        except I3Error as exc:
            skipped.append({"name": ws_name, "reason": str(exc)})
            continue
        moved.append(ws_name)

    return render.ok(moved=moved, skipped=skipped, output=output)
```

- [ ] **Step 4: Add `workspace` to `i3mcp/tools/__init__.py`**

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/ -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add i3mcp/tools/workspace.py i3mcp/tools/__init__.py tests/test_tools_workspace.py
git commit -m "feat: i3_workspace with number-vs-name handling"
```

---

### Task 11: `i3_scratchpad`

**Files:**
- Create: `i3mcp/tools/scratchpad.py`, `tests/test_tools_scratchpad.py`
- Modify: `i3mcp/tools/__init__.py`

**Interfaces:**
- Consumes: `render`, `ipc`, `tree`, `WindowCriteria`, `prefix_command`, `escape_value`.
- Produces: `i3mcp.tools.scratchpad.i3_scratchpad(...)`

This closes defect 8: `move` stored a **mark** while `show` looked up by
**title**. Both now key on marks.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_scratchpad.py`:

```python
import json

from i3mcp import ipc
from i3mcp.criteria import WindowCriteria
from i3mcp.tools.scratchpad import i3_scratchpad
from tests.test_tree import sample_tree


async def test_show_default_scratchpad(fake):
    await i3_scratchpad(action="show")
    assert fake.last_command == "scratchpad show"


async def test_show_by_mark_matches_what_move_stores(fake):
    await i3_scratchpad(action="show", mark="term")
    assert fake.last_command == r'[con_mark="^\Qterm\E$"] scratchpad show'


async def test_move_marks_then_moves(fake):
    await i3_scratchpad(action="move", mark="term")
    assert fake.last_command == 'mark --replace "term", move scratchpad'


async def test_move_without_mark(fake):
    await i3_scratchpad(action="move")
    assert fake.last_command == "move scratchpad"


async def test_move_with_criteria(fake):
    await i3_scratchpad(action="move", criteria=WindowCriteria(con_id=9), mark="term")
    assert fake.last_command == '[con_id=9] mark --replace "term", move scratchpad'


async def test_hide_all_hides_visible_scratchpad_windows(fake):
    tree_with_visible = sample_tree()
    workspace = tree_with_visible["nodes"][0]["nodes"][1]["nodes"][0]
    workspace["floating_nodes"].append({
        "type": "floating_con",
        "id": 77,
        "nodes": [{
            "type": "con",
            "id": 78,
            "window": 780,
            "name": "visible scratch",
            "floating": "user_on",
            "scratchpad_state": "changed",
            "marks": [],
            "rect": {},
            "window_properties": {"class": "Alacritty"},
            "nodes": [],
            "floating_nodes": [],
        }],
        "floating_nodes": [],
    })
    fake.query_replies[ipc.GET_TREE] = tree_with_visible
    result = json.loads(await i3_scratchpad(action="hide_all"))
    assert result["hidden_count"] == 1
    assert fake.commands == ["[con_id=78] move scratchpad"]


async def test_hide_all_ignores_windows_already_in_the_scratchpad(fake):
    fake.query_replies[ipc.GET_TREE] = sample_tree()
    result = json.loads(await i3_scratchpad(action="hide_all"))
    assert result["hidden_count"] == 0
    assert fake.commands == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/test_tools_scratchpad.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write `i3mcp/tools/scratchpad.py`**

```python
"""Scratchpad management, keyed consistently on marks."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import ipc, render, tree
from ..criteria import WindowCriteria, escape_value, prefix_command
from ..enums import MatchMode
from ..ipc import I3Error
from ..server import mcp


@mcp.tool(
    name="i3_scratchpad",
    annotations={
        "title": "Manage i3 Scratchpad",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_scratchpad(
    action: Literal["show", "move", "hide_all"] = Field(
        description="show toggles a window in or out; move sends one in; hide_all sends every visible one back."
    ),
    mark: str | None = Field(
        default=None,
        description="Named scratchpad. On move the mark is set; on show it is looked up. "
        "Use the same name for both.",
    ),
    criteria: WindowCriteria | None = Field(
        default=None, description="For move: which window to send. Omit for the focused one."
    ),
) -> str:
    """Show, hide, or populate the scratchpad. Named scratchpads are addressed by mark.

    List what is in the scratchpad with i3_query(what='scratchpad').
    """
    if action == "show":
        if mark is not None:
            selector = WindowCriteria(con_mark=mark, match=MatchMode.EXACT).to_selector()
            return render.run(f"{selector} scratchpad show")
        return render.run("scratchpad show")

    if action == "move":
        parts = []
        if mark is not None:
            parts.append(f'mark --replace "{escape_value(mark)}"')
        parts.append("move scratchpad")
        return render.run(prefix_command(criteria, ", ".join(parts)))

    # hide_all: a scratchpad window is visible when it sits on a real workspace.
    try:
        records = tree.walk_windows(ipc.get_connection().query(ipc.GET_TREE))
    except I3Error as exc:
        return render.err(str(exc))

    visible = [
        record
        for record in records
        if record.get("scratchpad_state")
        and record["scratchpad_state"] != "none"
        and record.get("workspace") != tree.SCRATCHPAD_WORKSPACE
    ]

    hidden: list[dict] = []
    failed: list[dict] = []
    for record in visible:
        try:
            ipc.get_connection().command(f"[con_id={record['con_id']}] move scratchpad")
        except I3Error as exc:
            failed.append({"con_id": record["con_id"], "name": record["name"], "error": str(exc)})
            continue
        hidden.append({"con_id": record["con_id"], "name": record["name"], "class": record["window_class"]})

    return render.ok(hidden_count=len(hidden), hidden=hidden, failed=failed)
```

- [ ] **Step 4: Add `scratchpad` to `i3mcp/tools/__init__.py`**

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/ -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add i3mcp/tools/scratchpad.py i3mcp/tools/__init__.py tests/test_tools_scratchpad.py
git commit -m "fix: address named scratchpads by mark on both show and move"
```

---

### Task 12: `i3_gaps` and `i3_bar`

**Files:**
- Create: `i3mcp/tools/gaps.py`, `i3mcp/tools/bar.py`, `tests/test_tools_gaps.py`, `tests/test_tools_bar.py`
- Modify: `i3mcp/tools/__init__.py`

**Interfaces:**
- Consumes: `render.run`, `render.err`.
- Produces: `i3mcp.tools.gaps.i3_gaps(...)`, `i3mcp.tools.bar.i3_bar(...)`

The runtime gaps command — verified on i3 4.25.1, where `workspace` and
`global` are **rejected** — is:

```
gaps <inner|outer|horizontal|vertical|top|right|bottom|left> <current|all> <set|plus|minus|toggle> <px>
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_gaps.py`:

```python
import json

from i3mcp.tools.gaps import i3_gaps


async def test_set_inner_uses_current_not_workspace(fake):
    await i3_gaps(gap="inner", amount=10)
    assert fake.last_command == "gaps inner current set 10"


async def test_scope_all(fake):
    await i3_gaps(gap="inner", amount=10, scope="all")
    assert fake.last_command == "gaps inner all set 10"


async def test_zero_is_a_valid_amount(fake):
    result = json.loads(await i3_gaps(gap="inner", amount=0))
    assert result["success"] is True
    assert fake.last_command == "gaps inner current set 0"


async def test_plus_operation(fake):
    await i3_gaps(gap="outer", operation="plus", amount=5)
    assert fake.last_command == "gaps outer current plus 5"


async def test_minus_operation(fake):
    await i3_gaps(gap="outer", operation="minus", amount=3)
    assert fake.last_command == "gaps outer current minus 3"


async def test_toggle_operation(fake):
    await i3_gaps(gap="inner", operation="toggle", amount=10)
    assert fake.last_command == "gaps inner current toggle 10"


async def test_edge_specific_gaps(fake):
    await i3_gaps(gap="top", amount=20)
    assert fake.last_command == "gaps top current set 20"


async def test_no_attribute_error_on_literal_fields(fake):
    """Regression: the old code called .value on a Literal, which is a plain str."""
    result = json.loads(await i3_gaps(gap="inner", operation="plus", amount=5))
    assert result["success"] is True
```

Create `tests/test_tools_bar.py`:

```python
import json

from i3mcp.tools.bar import i3_bar


async def test_bar_mode(fake):
    await i3_bar(mode="hide")
    assert fake.last_command == "bar mode hide"


async def test_bar_mode_with_id(fake):
    await i3_bar(mode="dock", bar_id="bar-0")
    assert fake.last_command == "bar mode dock bar-0"


async def test_bar_hidden_state(fake):
    await i3_bar(hidden_state="show")
    assert fake.last_command == "bar hidden_state show"


async def test_bar_requires_an_argument(fake):
    result = json.loads(await i3_bar())
    assert result["success"] is False
    assert fake.commands == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/test_tools_gaps.py tests/test_tools_bar.py -v`
Expected: FAIL — modules not found

- [ ] **Step 3: Write `i3mcp/tools/gaps.py`**

```python
"""Gap control.

The runtime syntax is `gaps <type> <current|all> <operation> <px>`. i3 4.25.1
rejects 'workspace' and 'global' as the scope token.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..server import mcp


@mcp.tool(
    name="i3_gaps",
    annotations={
        "title": "Adjust i3 Gaps",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_gaps(
    amount: int = Field(description="Size in pixels. 0 is valid and removes the gap.", ge=0, le=500),
    gap: Literal[
        "inner", "outer", "horizontal", "vertical", "top", "right", "bottom", "left"
    ] = Field(default="inner", description="Which gap to change."),
    operation: Literal["set", "plus", "minus", "toggle"] = Field(
        default="set", description="Set an absolute size, adjust it, or toggle between it and zero."
    ),
    scope: Literal["current", "all"] = Field(
        default="current", description="The current workspace, or every workspace."
    ),
) -> str:
    """Set or adjust gaps between windows (inner) or around workspace edges (outer).

    amount=0 is meaningful: it removes the gap.
    """
    return render.run(f"gaps {gap} {scope} {operation} {amount}")
```

- [ ] **Step 4: Write `i3mcp/tools/bar.py`**

```python
"""i3bar visibility."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..server import mcp


@mcp.tool(
    name="i3_bar",
    annotations={
        "title": "Control i3bar",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def i3_bar(
    mode: Literal["dock", "hide", "invisible"] | None = Field(
        default=None,
        description="dock is always visible, hide shows on the modifier key, invisible never shows.",
    ),
    hidden_state: Literal["hide", "show"] | None = Field(
        default=None, description="With mode=hide, whether the bar is currently shown."
    ),
    bar_id: str | None = Field(
        default=None, description="Which bar. Omit to affect every bar. List ids with i3_query."
    ),
) -> str:
    """Set i3bar's display mode or its current hidden state.

    Give mode, hidden_state, or both.
    """
    parts = []
    if mode is not None:
        parts.append(f"bar mode {mode}" + (f" {bar_id}" if bar_id else ""))
    if hidden_state is not None:
        parts.append(f"bar hidden_state {hidden_state}" + (f" {bar_id}" if bar_id else ""))
    if not parts:
        return render.err("Specify mode, hidden_state, or both.")
    return render.run("; ".join(parts))
```

- [ ] **Step 5: Add `gaps` and `bar` to `i3mcp/tools/__init__.py`**

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/ -v`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add i3mcp/tools/gaps.py i3mcp/tools/bar.py i3mcp/tools/__init__.py tests/test_tools_gaps.py tests/test_tools_bar.py
git commit -m "fix: correct gaps scope token and accept zero-size gaps"
```

---

### Task 13: `i3_wm`

**Files:**
- Create: `i3mcp/tools/wm.py`, `tests/test_tools_wm.py`
- Modify: `i3mcp/tools/__init__.py`

**Interfaces:**
- Consumes: `render.run`, `render.err`, `escape_value`.
- Produces: `i3mcp.tools.wm.i3_wm(...)`

`exit` is deliberately absent. Do not add it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_wm.py`:

```python
import json

from i3mcp.tools.wm import i3_wm


async def test_exec_uses_no_startup_id(fake):
    await i3_wm(action="exec", command="firefox")
    assert fake.last_command == "exec --no-startup-id firefox"


async def test_exec_on_a_workspace_switches_first(fake):
    await i3_wm(action="exec", command="firefox", workspace="web")
    assert fake.last_command == 'workspace "web"; exec --no-startup-id firefox'


async def test_reload(fake):
    await i3_wm(action="reload")
    assert fake.last_command == "reload"


async def test_restart(fake):
    await i3_wm(action="restart")
    assert fake.last_command == "restart"


async def test_mode(fake):
    await i3_wm(action="mode", mode_name="resize")
    assert fake.last_command == 'mode "resize"'


async def test_nop(fake):
    await i3_wm(action="nop", comment="marker")
    assert fake.last_command == "nop marker"


async def test_shmlog_on(fake):
    await i3_wm(action="shmlog", toggle="on")
    assert fake.last_command == "shmlog on"


async def test_debuglog_off(fake):
    await i3_wm(action="debuglog", toggle="off")
    assert fake.last_command == "debuglog off"


async def test_append_layout(fake):
    await i3_wm(action="append_layout", path="/home/u/layout.json")
    assert fake.last_command == 'append_layout "/home/u/layout.json"'


async def test_exec_requires_a_command(fake):
    result = json.loads(await i3_wm(action="exec"))
    assert result["success"] is False
    assert fake.commands == []


async def test_mode_requires_a_name(fake):
    result = json.loads(await i3_wm(action="mode"))
    assert result["success"] is False
    assert fake.commands == []


async def test_exit_is_not_an_allowed_action(fake):
    """Terminating the session must not be reachable through a tool call."""
    import inspect

    from i3mcp.tools import wm

    assert "exit" not in str(inspect.signature(wm.i3_wm))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/test_tools_wm.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write `i3mcp/tools/wm.py`**

```python
"""Window-manager level operations: launching, reloading, modes, logging."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import render
from ..criteria import escape_value
from ..server import mcp


@mcp.tool(
    name="i3_wm",
    annotations={
        "title": "Control i3 Itself",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def i3_wm(
    action: Literal[
        "exec", "reload", "restart", "mode", "nop", "shmlog", "debuglog", "append_layout"
    ] = Field(description="Which window-manager operation to run."),
    command: str | None = Field(
        default=None, description="For action=exec: the shell command to launch.", max_length=500
    ),
    workspace: str | None = Field(
        default=None, description="For action=exec: switch to this workspace before launching."
    ),
    mode_name: str | None = Field(
        default=None, description="For action=mode: the binding mode to enter, e.g. 'resize'."
    ),
    comment: str | None = Field(default=None, description="For action=nop: a comment to log."),
    toggle: Literal["on", "off", "toggle"] | None = Field(
        default=None, description="For shmlog and debuglog."
    ),
    path: str | None = Field(
        default=None, description="For action=append_layout: path to a saved layout JSON file."
    ),
) -> str:
    """Launch an application, reload or restart i3, switch binding mode, or control logging.

    New windows land on the focused workspace, so exec switches there first when asked.
    """
    if action == "exec":
        if not command:
            return render.err("action=exec needs a command.")
        cmd = f"exec --no-startup-id {command}"
        if workspace:
            cmd = f'workspace "{escape_value(workspace)}"; {cmd}'
        return render.run(cmd)

    if action in ("reload", "restart"):
        return render.run(action)

    if action == "mode":
        if not mode_name:
            return render.err("action=mode needs mode_name.")
        return render.run(f'mode "{escape_value(mode_name)}"')

    if action == "nop":
        return render.run(f"nop {comment}" if comment else "nop")

    if action in ("shmlog", "debuglog"):
        if toggle is None:
            return render.err(f"action={action} needs toggle=on, off, or toggle.")
        if action == "debuglog" and toggle == "toggle":
            return render.err("debuglog accepts only on or off.")
        return render.run(f"{action} {toggle}")

    if not path:
        return render.err("action=append_layout needs a path.")
    return render.run(f'append_layout "{escape_value(path)}"')
```

- [ ] **Step 4: Restore the full module list in `i3mcp/tools/__init__.py`**

All thirteen modules now exist. The import list from Task 5 Step 4 should be
complete and uncommented.

- [ ] **Step 5: Run the whole suite**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/ -v`
Expected: all passed

- [ ] **Step 6: Verify all thirteen tools register**

Run:

```bash
uv run --with mcp --with pydantic python -c "
import asyncio, i3mcp.tools
from i3mcp.server import mcp
tools = asyncio.run(mcp.list_tools())
print(len(tools))
for t in sorted(tools, key=lambda t: t.name):
    print(' ', t.name, len(t.description or ''))
"
```

Expected: `13`, and every description under ~450 characters.

- [ ] **Step 7: Commit**

```bash
git add i3mcp/tools/wm.py i3mcp/tools/__init__.py tests/test_tools_wm.py
git commit -m "feat: i3_wm for exec, reload, restart, modes, and logging"
```

---

### Task 14: Entry point, smoke test, README, allowlist

**Files:**
- Modify: `i3_mcp.py`, `README.md`, `.claude/settings.local.json`
- Create: `scripts/smoke.py`

**Interfaces:**
- Consumes: `i3mcp.server.main`.
- Produces: a runnable server and a live smoke script.

- [ ] **Step 1: Replace `i3_mcp.py` with a shim**

Delete the entire existing contents and replace with:

```python
#!/usr/bin/env python3
"""Entry point for the i3wm MCP server. The implementation lives in the i3mcp package."""

from i3mcp.server import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the server starts and serves 13 tools**

Run:

```bash
uv run --with mcp --with pydantic python -c "
import asyncio
from i3mcp.server import mcp
import i3mcp.tools
print(len(asyncio.run(mcp.list_tools())), 'tools registered')
"
```

Expected: `13 tools registered`

- [ ] **Step 3: Write `scripts/smoke.py`**

```python
#!/usr/bin/env python3
"""Live smoke test. Exercises every tool against the running i3.

Creates a scratch workspace, runs each tool, and restores the previously
focused workspace. Run it deliberately:

    uv run --with mcp --with pydantic python scripts/smoke.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from i3mcp import ipc
from i3mcp.tools.bar import i3_bar
from i3mcp.tools.focus import i3_focus
from i3mcp.tools.gaps import i3_gaps
from i3mcp.tools.layout import i3_layout
from i3mcp.tools.mark import i3_mark
from i3mcp.tools.move import i3_move
from i3mcp.tools.query import i3_query
from i3mcp.tools.resize import i3_resize
from i3mcp.tools.scratchpad import i3_scratchpad
from i3mcp.tools.window import i3_window
from i3mcp.tools.wm import i3_wm
from i3mcp.tools.workspace import i3_workspace

SCRATCH_WS = "__smoke_test"

results: list[tuple[str, bool, str]] = []


async def check(label: str, coro) -> dict:
    raw = await coro
    parsed = json.loads(raw) if raw.lstrip().startswith("{") else {"success": True}
    ok = parsed.get("success", True)
    results.append((label, ok, "" if ok else parsed.get("error", "")))
    return parsed


async def main() -> int:
    conn = ipc.get_connection()
    workspaces = conn.query(ipc.GET_WORKSPACES)
    original = next((ws["name"] for ws in workspaces if ws.get("focused")), None)

    try:
        await check("workspace switch", i3_workspace(action="switch", name=SCRATCH_WS))

        # Read-only queries.
        for what in (
            "tree", "focused", "scratchpad", "workspaces", "outputs", "marks",
            "version", "config", "bar_config", "binding_modes", "binding_state",
        ):
            await check(f"query {what}", i3_query(what=what))

        # Commands that are safe with no window present.
        await check("gaps set 0", i3_gaps(gap="inner", amount=0))
        await check("gaps plus", i3_gaps(gap="inner", operation="plus", amount=0))
        await check("bar hidden_state", i3_bar(hidden_state="show"))
        await check("wm nop", i3_wm(action="nop", comment="smoke"))
        await check("workspace navigate", i3_workspace(action="navigate", direction="back_and_forth"))
        await check("workspace switch back", i3_workspace(action="switch", name=SCRATCH_WS))

        # Launch a window and drive it.
        await check("wm exec", i3_wm(action="exec", command="xterm -T i3mcp-smoke"))
        for _ in range(40):
            await asyncio.sleep(0.25)
            tree = json.loads(await i3_query(what="tree", workspace=SCRATCH_WS))
            if tree.get("windows"):
                break
        else:
            results.append(("window appeared", False, "no window on the scratch workspace"))
            raise SystemExit

        from i3mcp.criteria import WindowCriteria

        target = WindowCriteria(title="i3mcp-smoke", match="substring")
        await check("focus criteria", i3_focus(criteria=target))
        await check("mark set", i3_mark(criteria=target, mark="smoke"))
        by_mark = WindowCriteria(con_mark="smoke")
        await check("layout tabbed", i3_layout(criteria=by_mark, layout="tabbed"))
        await check("layout splith", i3_layout(criteria=by_mark, layout="splith"))
        await check("window floating", i3_window(criteria=by_mark, floating="enable"))
        await check("window border", i3_window(criteria=by_mark, border="pixel", border_width=2))
        await check("window title_format", i3_window(criteria=by_mark, title_format="%title"))
        await check("resize set px", i3_resize(criteria=by_mark, mode="set", width=600, height=400))
        await check("move center", i3_move(criteria=by_mark, center=True))
        await check("move position", i3_move(criteria=by_mark, position_x=50, position_y=50))
        await check("window tiling", i3_window(criteria=by_mark, floating="disable"))
        await check("resize grow ppt", i3_resize(criteria=by_mark, mode="grow", direction="right", amount=1, unit="ppt"))
        await check("scratchpad move", i3_scratchpad(action="move", criteria=by_mark, mark="smoke"))
        await check("scratchpad show", i3_scratchpad(action="show", mark="smoke"))
        await check("scratchpad hide_all", i3_scratchpad(action="hide_all"))
        await check("scratchpad show again", i3_scratchpad(action="show", mark="smoke"))
        await check("mark unmark", i3_mark(criteria=by_mark, unmark="smoke"))

        from i3mcp.tools.kill import i3_kill

        await check("kill", i3_kill(criteria=WindowCriteria(title="i3mcp-smoke", match="substring")))

    finally:
        if original:
            conn.command(f'workspace "{original}"')

    failures = [(label, error) for label, ok, error in results if not ok]
    for label, ok, error in results:
        print(f"{'ok  ' if ok else 'FAIL'}  {label}" + (f"  — {error.splitlines()[0]}" if error else ""))
    print(f"\n{len(results) - len(failures)}/{len(results)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 4: Run the smoke test**

Run: `uv run --with mcp --with pydantic python scripts/smoke.py`
Expected: every line `ok`. Fix any command i3 rejects — that is exactly the
failure class this script exists to catch. `xterm` may be absent; substitute
whatever terminal is installed and note the substitution in the script header.

- [ ] **Step 5: Rewrite `.claude/settings.local.json`**

```json
{
  "permissions": {
    "allow": [
      "mcp__i3__i3_query",
      "mcp__i3__i3_focus",
      "mcp__i3__i3_move",
      "mcp__i3__i3_resize",
      "mcp__i3__i3_window",
      "mcp__i3__i3_layout",
      "mcp__i3__i3_workspace",
      "mcp__i3__i3_mark",
      "mcp__i3__i3_scratchpad",
      "mcp__i3__i3_gaps",
      "mcp__i3__i3_bar",
      "mcp__i3__i3_wm",
      "Bash(i3-msg:*)"
    ],
    "deny": [],
    "ask": []
  }
}
```

`i3_kill` is deliberately left out so closing a window still prompts.

- [ ] **Step 6: Rewrite `README.md`**

Keep the existing badges, the title, and the "Vibecode alert" note. Replace
everything else. Required content:

- **Install** — `uv` only, no pipx, no manual venv:
  ```bash
  git clone https://github.com/caninja/i3wm-mcp.git
  cd i3wm-mcp
  claude mcp add --transport stdio i3 -- uv run --directory /absolute/path/to/i3wm-mcp i3wm-mcp
  ```
  With the manual `~/.claude.json` equivalent:
  ```json
  {
    "mcpServers": {
      "i3": {
        "command": "uv",
        "args": ["run", "--directory", "/absolute/path/to/i3wm-mcp", "i3wm-mcp"]
      }
    }
  }
  ```
- **Requirements** — Python 3.10+, i3 4.x (developed against 4.25.1), `uv`.
  State plainly that dependencies are `mcp>=2` and `pydantic>=2`, resolved by
  `uv` from `pyproject.toml`. Remove every mention of `pipx`, `fastmcp`, and
  `pacman -S python-pydantic`.
- **Tools** — a table of all 13 with one line each.
- **Criteria** — explain that most tools take a `criteria` object, that
  matching is exact by default with `substring` and `regex` available, and
  that `con_id` from `i3_query` is the most precise handle.
- **Verification**:
  ```bash
  uv run --with pytest --with pytest-asyncio pytest    # offline unit tests
  uv run python scripts/smoke.py                        # live, drives real i3
  ```
- **Gotchas** — a short section covering: use `by_number=true` for workspaces
  named like `3: web`; `i3_wm(action="exec")` returns as soon as i3 accepts
  the command, so poll `i3_query` for the new window rather than assuming it
  exists; `exit` is not exposed on purpose.
- Delete the stale `## TODO` section.

- [ ] **Step 7: Confirm nothing references the old modules**

Run: `grep -rn "fastmcp\|FastMCP\|run_i3_msg\|i3-msg" --include=*.py --include=*.md . | grep -v '^./docs/'`
Expected: no hits in `i3mcp/`, `scripts/`, `tests/` or `README.md`. Hits inside
`docs/superpowers/` are the spec and this plan quoting the old code; leave them.

- [ ] **Step 8: Run the full suite one last time**

Run: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/ -v`
Expected: all passed

- [ ] **Step 9: Commit**

```bash
git add i3_mcp.py README.md .claude/settings.local.json scripts/smoke.py
git commit -m "feat: package entry point, live smoke test, rewritten README"
```

---

## Verification Checklist

Confirm each defect from the spec is closed, with a test naming it:

- [ ] 1 — imports `MCPServer` from `mcp.server.mcpserver`; `pyproject.toml` declares `mcp>=2`
- [ ] 2 — `test_set_inner_uses_current_not_workspace`
- [ ] 3 — `test_no_attribute_error_on_literal_fields`
- [ ] 4 — `test_zero_is_a_valid_amount`
- [ ] 5 — `test_floating_read_from_floating_field_not_node_type`
- [ ] 6 — `test_workspace_filter_actually_filters`
- [ ] 7 — `test_urgent_rejects_boolean_style_values`, `test_focus_urgent_uses_i3_vocabulary`
- [ ] 8 — `test_show_by_mark_matches_what_move_stores`
- [ ] 9 — `test_command_failure_raises_with_i3_error_detail`, `test_partial_failure_in_multi_reply_raises`
- [ ] 10 — `test_json_list_stays_valid_json_when_truncated`
- [ ] Criteria reach every mutator — `i3_kill`, `i3_move`, `i3_resize`, `i3_window`, `i3_layout`, `i3_mark`, `i3_scratchpad` all take `criteria`
- [ ] ppt reachable — `test_move_direction_with_ppt`, `test_resize_shrink_ppt`, `test_resize_set_width_only_ppt`
- [ ] `workspace number` reachable — `test_switch_by_number`, `test_move_to_workspace_by_number`
- [ ] Exactly 13 tools registered, `exit` not among their actions
- [ ] `scripts/smoke.py` passes against live i3
