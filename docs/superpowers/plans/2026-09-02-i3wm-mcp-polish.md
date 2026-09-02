# i3wm-mcp Polish Plan

**Goal:** Fix six live-verified i3 syntax bugs, close the silent no-op gap on criteria commands, shrink the tool schema payload by roughly half, remove test-shaped production code, and add the three coverage items (layout outline, scratchpad show by criteria, exec that waits for its window).

**Architecture:** Unchanged. Native IPC over the unix socket (`i3mcp/ipc.py`), one `WindowCriteria` model, 13 tools under `i3mcp/tools/`, `MCPServer` from `mcp>=2`. This plan edits inside that shape; it adds no tools and no dependencies.

**Spec:** `docs/superpowers/specs/2026-09-02-i3wm-mcp-overhaul-design.md` (the design this code implements). The findings below were verified against live i3 4.25.1 on 2026-09-02; each task cites its evidence.

## Global Constraints

- Target i3 **4.25.1**. Every emitted command string must parse on that version. When in doubt, verify with `i3-msg '<command>'` against the running instance; never reason from memory about i3 syntax.
- Runtime dependencies are **`mcp>=2` and `pydantic>=2` only**. No new dependencies of any kind.
- Import is `from mcp.server.mcpserver import MCPServer`. `FastMCP` does not exist in `mcp` 2.x.
- Tools take **flat keyword arguments**, never a single `params` wrapper. `criteria` stays a nested object.
- Tool docstrings are **at most 6 lines**. Detail belongs in `Field(description=...)`. Do not restore long docstrings.
- Every tool returns a **JSON string** (`json.dumps(..., indent=2)`).
- Criteria string values default to **exact** matching via `^\Qvalue\E$`. Escaping rule: backslash first, then double quote (`criteria.escape_value`).
- `exit` must never be exposed as a tool action. Exactly 13 tools stay registered.
- Python 3.10+ syntax (`X | None`).
- Never hardcode a workspace name, output name, binding-mode name, or application from any user's config. Tests use generic fixture values.
- Run tests with: `uv run --with mcp --with pydantic --with pytest --with pytest-asyncio pytest tests/ -q`
- Live smoke test (drives real i3, opens/closes an xterm on a scratch workspace, restores the focused workspace): `uv run --with mcp --with pydantic python scripts/smoke.py`
- Commit after each task with a conventional-commit subject and the trailer lines:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01TzQwMqk4S2JT3YY6RtUWfD
  ```
- TDD: write the failing test, run it and see it fail, implement, run it and see it pass.

## File Structure

Existing files this plan modifies: `i3mcp/server.py`, `i3mcp/ipc.py`, `i3mcp/enums.py`, `i3mcp/criteria.py`, `i3mcp/tree.py`, `i3mcp/render.py`, every module under `i3mcp/tools/`, every file under `tests/`, `scripts/smoke.py`, `README.md`.

New files: `i3mcp/schema.py` (schema compaction), `scripts/schema_size.py` (measurement), `tests/test_schema.py`, `tests/test_tools_query_layout.py`, `tests/test_matching.py`.

---

### Task 1: Test through `call_tool`; delete `resolve_defaults`

**Files:** `i3mcp/server.py`, every `i3mcp/tools/*.py`, `tests/conftest.py`, every `tests/test_tools_*.py`, `scripts/smoke.py`.

**Why:** `resolve_defaults` in `i3mcp/server.py` wraps every tool in `pydantic.validate_call` purely so unit tests can call the coroutines directly. That is production code shaped by test convenience, and it means the tests never exercise the real MCP dispatch path (argument-model validation, defaults, enum coercion), which is exactly where the "FieldInfo left as default" bug class lives.

**Do:**

1. Add to `tests/conftest.py`:
   ```python
   from i3mcp.server import mcp
   import i3mcp.tools  # noqa: F401  (registers every tool)


   async def call(name: str, **arguments) -> str:
       """Invoke a tool the way an MCP client does and return its text payload."""
       result = await mcp.call_tool(name, arguments)
       return result.content[0].text
   ```
   Expose it as a plain importable helper (`from tests.conftest import call` works because `tests/__init__.py` exists) or as a fixture; pick one and use it consistently.
2. Migrate every `await i3_xxx(...)` in `tests/test_tools_*.py` to `await call("i3_xxx", ...)`. Tests that pass a `WindowCriteria(...)` instance should pass a plain dict instead (`criteria={"window_class": "firefox"}`), which is what a client sends.
3. Tests that expect a validation failure (for example an `urgent` value i3 does not accept) must assert `pytest.raises(ToolError)` where `ToolError` is `from mcp.server.mcpserver.exceptions import ToolError` (confirm the import path in the installed `mcp` package; adjust if it lives elsewhere).
4. Delete `resolve_defaults` from `i3mcp/server.py` and the `@resolve_defaults` line plus its import from every tool module.
5. Migrate `scripts/smoke.py` to the same `call(name, **args)` pattern (define the helper locally in the script; do not import from tests).
6. Run the full suite; every test must pass with no warnings.

**Acceptance:** `grep -rn resolve_defaults i3mcp tests scripts` returns nothing. `mcp.list_tools()` still reports 13 tools. Full suite green.

**Commit:** `refactor: test tools through MCP dispatch and drop resolve_defaults`

---

### Task 2: Live-verified syntax fixes

**Files:** `i3mcp/tools/wm.py`, `i3mcp/tools/window.py`, `i3mcp/tools/move.py`, `i3mcp/tools/workspace.py`, `i3mcp/tools/resize.py`, `i3mcp/tools/scratchpad.py`, `i3mcp/enums.py`, matching tests.

Each item below was verified against live i3 4.25.1 on 2026-09-02. Write the failing test first for each.

**2a. `exec` must quote the command.**
Evidence: `exec --no-startup-id sh -c "true; true"` → parse error at `;` (i3 splits sub-commands on `;` and `,`). `exec --no-startup-id "sh -c \"true; true\""` → success. `exec --no-startup-id "true, true"` → success.
Fix in `wm.py`: emit `exec --no-startup-id "{escape_value(command)}"`. With `workspace` set the prefix stays: `workspace "{ws}"; exec --no-startup-id "{cmd}"`.
Tests: `command='sh -c "echo a; echo b"'` emits exactly `exec --no-startup-id "sh -c \"echo a; echo b\""`; a command with a comma is emitted quoted.

**2b. `title_window_icon` grammar.**
Evidence: `title_window_icon on padding 3 px` → parse error. `title_window_icon all` → parse error ("Expected one of these tokens: 'padding', 'toggle', '1', 'yes', 'true', 'on', 'enable', 'active', '0', 'no', 'false', 'off', 'disable', 'inactive'"). `title_window_icon toggle` → ok. `title_window_icon padding 3px` → ok.
Fix in `window.py`: `title_window_icon: Literal["on", "off", "toggle"] | None`. `title_window_icon_padding` becomes its own chained sub-command `title_window_icon padding {n}px` (note: `3px`, no space) appended after the on/off part, and it is valid on its own without `title_window_icon`.
Tests: `title_window_icon="on", title_window_icon_padding=3` emits `title_window_icon on, title_window_icon padding 3px`; padding alone emits `title_window_icon padding 3px`.

**2c. Centre on the current output, not the whole screen.**
Evidence on a two-output machine: `move position center` placed the window at y=559 (centred on its output); `move absolute position center` placed it at y=1149 (centred across both outputs, straddling the bezel). The tool's own description says "on its output" but it emits `absolute`.
Fix in `move.py`: `center=True` emits `move position center`; `position_x/position_y` emit `move position {x} {unit} {y} {unit}`. Add `absolute: bool = Field(default=False, description="With center or position: use coordinates spanning every output instead of the current one.")`; when true, insert `absolute` after `move`.
Tests: default centre → `move position center`; `absolute=True` → `move absolute position center`; position with `absolute=True` → `move absolute position 100 px 200 px`.

**2d. Navigation keywords must not be quoted into workspace names.**
Evidence: `move container to workspace back_and_forth` and `move container to workspace next_on_output` both succeed unquoted; quoting them creates a workspace literally named `back_and_forth`.
Fix: in `move.py` add `"back_and_forth"` to `_RELATIVE_WORKSPACES`. In `workspace.py`, `action="switch"` with `name` in `{"next", "prev", "next_on_output", "prev_on_output", "back_and_forth"}` emits `workspace {name}` unquoted (same as `navigate`). Put the keyword set in one place (`workspace.py` may import it from `move.py` or both from a tiny shared constant in `enums.py`; do not duplicate the literal set).
Tests: `i3_move(workspace="back_and_forth")` → `move container to workspace back_and_forth`; `i3_workspace(action="switch", name="next")` → `workspace next`.

**2e. `resize` must accept `width` and `height` directions.**
Evidence: `resize grow width 1 px or 1 ppt` parses; `resize grow width 10 ppt` is a parse error (the existing `px or ppt` workaround stays).
Fix in `resize.py`: `direction: Literal["width", "height", "left", "right", "up", "down"] | None`. Update the description: "which edge or dimension changes".
Tests: `mode="grow", direction="width", amount=10` → `resize grow width 10 px`; `unit="ppt"` → `resize grow width 10 px or 10 ppt`.

**2f. `debuglog toggle` is valid.**
Evidence: `debuglog toggle` → success (run twice to restore).
Fix in `wm.py`: remove the guard that rejects it. Test: `action="debuglog", toggle="toggle"` → `debuglog toggle`.

**2g. `scratchpad show` by criteria.**
Real setups address scratchpad windows by class, instance or title, not only by mark. Fix in `scratchpad.py`: `action="show"` accepts `criteria` (non-empty) as an alternative to `mark`: emit `{selector} scratchpad show`. If both `mark` and a non-empty `criteria` are given, return `render.err("Give mark or criteria for show, not both.")`. Update the `criteria` field description to say it applies to show and move.
Tests: `action="show", criteria={"window_class": "term"}` → `[class="^\Qterm\E$"] scratchpad show`; both given → error JSON with `success: false`.

**Acceptance:** every new test passes; full suite green; `uv run --with mcp --with pydantic python scripts/smoke.py` passes against live i3.

**Commit:** one commit per sub-item is fine, or one commit `fix: live-verified i3 syntax (exec quoting, title icon, centre, keywords, resize dims)`.

---

### Task 3: Schema compaction

**Files:** new `i3mcp/schema.py`, new `scripts/schema_size.py`, new `tests/test_schema.py`, `i3mcp/tools/__init__.py`, `i3mcp/enums.py`, `i3mcp/criteria.py`, every tool module that used an enum's `.value`.

**Baseline (measured 2026-09-02, `list_tools()` serialised compact):** 43,405 chars total, of which 21,570 (50%) are `$defs` blocks; `WindowCriteria` plus six enums are inlined into each of the 8 criteria-taking tools.

**How mcp builds the schema (verified in `mcp` 2.1.1 source):** `Tool.from_function` calls `arg_model.model_json_schema(by_alias=True)` once at registration and stores the dict as `tool.parameters`; `MCPServer.list_tools()` re-reads `info.parameters` on every call. So a dict compacted in place after registration is what every client sees. Server-side validation still runs against the pydantic model and is unaffected.

**Do:**

1. `i3mcp/schema.py` with `def compact(schema: dict) -> dict` that returns a deep-copied, compacted schema:
   - remove every `"title"` key at every level (root, properties, `$defs` entries);
   - collapse `{"anyOf": [X, {"type": "null"}], ...}` into `X` merged with the remaining sibling keys (keep `description`, drop a `"default": None`);
   - drop any remaining `"default": None`;
   - keep non-null defaults, `enum`, `minimum`/`maximum`, `additionalProperties`, `required`, `description`.
   Unit-test `compact` directly on a hand-written schema fragment covering each rule.
2. In `i3mcp/tools/__init__.py`, after the imports, compact every registered tool:
   ```python
   from ..schema import compact
   from ..server import mcp

   for _tool in mcp._tool_manager.list_tools():
       _tool.parameters = compact(_tool.parameters)
   ```
   (`_tool_manager` is the only handle mcp 2.1.1 offers; note that in a comment.)
3. Replace the `(str, Enum)` classes in `i3mcp/enums.py` with `Literal` aliases so they render inline instead of as `$defs` + `$ref`:
   `Direction = Literal["left", "right", "up", "down"]`, `MatchMode = Literal["exact", "substring", "regex"]`, `Urgency = Literal[...]`, `WindowType = Literal[...]`, `Unit = Literal["px", "ppt"]`. Delete `ResponseFormat` only if Task 4 has already landed; otherwise leave it for Task 4. Update every `.value` use in tools and `criteria.py` to use the plain string.
4. Trim `WindowCriteria` (every character here is paid 8 times):
   - merge `floating: bool` and `tiling: bool` into `floating: bool | None = Field(default=None, description="true: only floating windows; false: only tiling.")` → emits `floating` / `tiling`;
   - drop `machine` (WM_CLIENT_MACHINE; no realistic tool call targets a window by hostname);
   - shorten descriptions to one clause each, e.g. `window_class`: "WM_CLASS class, e.g. 'firefox'."; `instance`: "WM_CLASS instance."; `con_id`: "Container id from i3_query; the most precise selector."; `urgent`: "Pick an urgent window: latest, oldest, newest, last, recent or first."; `match`: "How strings match: exact (default), substring, regex.";
   - the model docstring becomes one line: "Which window(s) to act on. Omit every field for the focused window."
5. `scripts/schema_size.py`: prints per-tool total chars, `$defs` chars and description chars, plus the grand total and an approximate token count (chars / 3.5). Usable as `uv run --with mcp --with pydantic python scripts/schema_size.py`.
6. `tests/test_schema.py`: (a) `compact` unit tests; (b) an integration test over `await mcp.list_tools()` asserting no `"title"` key anywhere in any `inputSchema`, no `anyOf` containing `{"type": "null"}`, no `$defs` entry other than `WindowCriteria`, and total compact-serialised size below **26,000** chars (a ceiling with headroom, not a target).

**Acceptance:** measured total at or below ~22,000 chars (report the exact before/after numbers in the task report); 13 tools; full suite green; smoke passes.

**Commit:** `perf: compact tool schemas (inline enums, strip titles, collapse nullables)`

---

### Task 4: Compact query output; drop `response_format`

**Files:** `i3mcp/render.py`, `i3mcp/tree.py`, `i3mcp/tools/query.py`, `i3mcp/enums.py`, `tests/test_render.py`, `tests/test_tree.py`, `tests/test_tools_query.py`, and any tool test asserting `replies` on success.

**Why:** `response_format="markdown"` is honoured by 3 of 11 `i3_query` types and silently ignored by the other 8. A parameter that does nothing is worse than none. Its purpose (fewer tokens) is served better by compact JSON everywhere.

**Do:**

1. Remove `response_format` from `i3_query`, delete `ResponseFormat` from `enums.py`, delete `render.markdown` and `render.window_lines` and their tests.
2. Window records (`tree._record`) become compact:
   - omit any key whose value is `None`, `False`, `[]` or `{}` (document in the `i3_query` docstring: "absent boolean means false");
   - replace the misleading `layout` field (the leaf's own layout, always `splith`) with `parent_layout`: the layout of the enclosing container (`splith|splitv|tabbed|stacked`), or `"floating"` for a floating window. `walk_windows` passes the parent's layout down;
   - add `sticky: true` when the node's `sticky` is true;
   - add `workspace_num` (the workspace node's `num`) when it is a non-negative integer;
   - `rect` becomes a 4-element list `[x, y, width, height]`; say so in the docstring.
3. `filter_windows(workspace=...)`: a value that is all digits also matches `workspace_num`, so `"3"` finds a workspace named `"3: web"`. Update the `workspace` field description on `i3_query`.
4. `render.run`: on success return `ok(command=command, **extra)` without the constant `replies` list. On failure keep `i3_replies`.
5. Update fixtures and assertions in `tests/test_tree.py`, `tests/test_tools_query.py`, `tests/test_render.py` accordingly; keep the named regression tests from the spec (`test_floating_read_from_floating_field_not_node_type`, `test_workspace_filter_actually_filters`, `test_json_list_stays_valid_json_when_truncated`).

**Acceptance:** `i3_query` schema has no `response_format`; a tiled focused window record contains `parent_layout` and no `layout`, no `floating`, no `urgent` keys; full suite green.

**Commit:** `feat: compact window records and drop the half-implemented response_format`

---

### Task 5: Report targets; refuse silent no-ops

**Files:** `i3mcp/criteria.py`, `i3mcp/render.py`, `tests/conftest.py`, new `tests/test_matching.py`, the criteria-taking tools (`focus`, `move`, `resize`, `kill`, `window`, `layout`, `mark`, `scratchpad`) and their tests.

**Evidence (live i3 4.25.1):** with criteria that match nothing, `kill`, `floating enable`, `resize set …`, `layout tabbed` and `move scratchpad` all return `[{"success": true}]`. Only `focus`, `mark`, and `move container to workspace` report the miss. A tool call that returns success while doing nothing is the worst outcome for an LLM caller.

**Do:**

1. `WindowCriteria.matches(record: dict) -> bool` in `criteria.py`, evaluated against the compact window records from Task 4. Semantics mirror i3's, applied to the raw value with the chosen `match` mode (exact `==`, substring `in`, regex `re.search`; case-sensitive):
   - `window_class` ↔ `window_class`; `instance` ↔ `instance`; `title` ↔ `name`; `window_role` ↔ `window_role`; `window_type` ↔ `window_type` (exact);
   - `con_mark` ↔ any entry of `marks`; `workspace` ↔ `workspace` name;
   - `con_id`, `window_id` ↔ equality;
   - `floating` True/False ↔ `floating` present/absent; `urgent` (any keyword) ↔ `urgent` present; `all` ↔ always true.
   All set fields must match (AND). An invalid regex raises `ValueError` with a message naming the field.
2. `render.run_targeted(criteria, command, **extra) -> str` in `render.py`:
   - fetch the tree once (`ipc.get_connection().query(ipc.GET_TREE)`), walk to records excluding docks;
   - if `criteria` is None or empty: `targets` = the focused record (list of 0 or 1);
   - else `targets` = records matching; if empty return `err("No window matches the criteria.", criteria=<selector string>, hint="List windows with i3_query; con_id is the most reliable selector.")` **without sending the command**;
   - otherwise run `prefix_command(criteria, command)` and include `targets` in the success payload as `[{"con_id", "name", "window_class"}]`, capped at 20 entries plus `target_count`.
   - an `I3Error` from the tree fetch returns `err(str(exc))`.
3. Switch every criteria-bearing code path in the eight tools from `render.run(prefix_command(criteria, cmd))` to `render.run_targeted(criteria, cmd)`. Non-criteria paths (`focus left`, `focus output …`, `scratchpad show` with no mark/criteria, bulk operations) keep `render.run`.
4. `tests/conftest.py`: `FakeTransport.query_replies` gets a default `GET_TREE` reply, a small generic tree fixture with a focused tiled window (class `Alpha`, title `alpha one`, con_id 1001, marks `["m1"]`), a floating window (class `Beta`, con_id 1002, on the same workspace) and a window on another workspace (class `Gamma`, con_id 1003). Existing tool tests that use criteria must target fixture windows.
5. `tests/test_matching.py`: exact/substring/regex per field, `con_mark` against a marks list, tri-state `floating`, `all`, AND across fields, invalid regex error. Tool-level tests: zero-match returns the error JSON and sends no command; a match returns `targets` and sends the prefixed command; a call without criteria reports the focused window as its target.

**Acceptance:** `i3_kill(criteria={"window_class": "Nope"})` returns `success: false` and `fake.commands` is empty; `i3_window(criteria={"con_id": 1002}, floating="disable")` returns `targets=[{con_id: 1002, …}]`; full suite green; smoke passes.

**Commit:** `feat: report targets and refuse criteria that match nothing`

---

### Task 6: `i3_query(what="layout")`

**Files:** `i3mcp/tree.py`, `i3mcp/tools/query.py`, new `tests/test_tools_query_layout.py`, `tests/test_tree.py`.

**Why:** the flat window list hides container structure. An LLM cannot see that two windows share a tabbed container, and `i3_layout` can only target a split container by `con_id`, which nothing exposes. Live tree shape (4.25.1): `root → output → con(content) → workspace → con(split, layout=tabbed|splith|…) → con(window)`; floating windows sit under `floating_nodes` as `floating_con → con(window)`; every node carries `id`, `type`, `layout`, `orientation`, `percent`, `focused`, `nodes`, `floating_nodes`.

**Do:**

1. `tree.outline(tree: dict, workspace: str | None) -> dict | None`:
   - choose the workspace node: by exact name, or by `num` when `workspace` is all digits, or, when `workspace` is None, the workspace containing the node with `focused: true`; return `None` when nothing matches;
   - render recursively. A leaf (node with `window`) becomes `{"con_id", "name", "window_class", "percent", "focused": true?, "marks"?}`; a container becomes `{"con_id", "layout", "percent", "nodes": [...]}`; the workspace root is `{"con_id", "workspace": name, "workspace_num"?, "layout", "nodes": [...], "floating": [leaf, ...]}` where `floating` lists the windows under `floating_nodes` (skip the `floating_con` wrapper). Omit `percent` when None, round it to 2 decimals, and omit empty `floating`/`marks`. Skip dock windows.
2. `i3_query`: add `"layout"` to the `what` Literal; `workspace` filter applies (name or number); docstring gains one line: "layout: nested containers of one workspace, with con_ids that i3_layout can target."
3. Tests: fixture tree with a workspace holding a tabbed container of two windows beside a lone window plus one floating window; assert the nested shape, con_ids, `percent` rounding, floating list, and the focused-workspace default; unknown workspace returns `success: false` with a clear error.

**Acceptance:** full suite green; against live i3 `i3_query(what="layout")` returns the focused workspace's structure.

**Commit:** `feat: i3_query layout outline of one workspace`

---

### Task 7: `exec` that waits for its window

**Files:** `i3mcp/ipc.py`, `i3mcp/tools/wm.py`, `tests/test_ipc.py`, `tests/test_tools_wm.py`, `README.md` gotcha line.

**Evidence (live, 2026-09-02):** on a second socket, `SUBSCRIBE ["window"]` replies `{"success": true}`; after `exec --no-startup-id "xterm -T probe"` on the command socket, the event socket delivers a frame with header type `0x80000003` (high bit = event, low bits `3` = window) whose payload is `{"change": "new", "container": {...}}` about 20 ms later. The `container` carries `id`, `window`, `name`, `window_properties.class/instance`, `output`, `floating`, `marks`, `window_type`, but **no workspace**. The title may still be provisional at `new` time.

**Do:**

1. `ipc.py`:
   - `EVENT_WINDOW = 3` and `EVENT_MASK = 0x80000000`; `_request_once` already ignores the reply type, leave it;
   - `class EventStream`: opens its **own** socket to the same path (never the shared command connection: events would interleave with replies), sends `SUBSCRIBE` with the JSON list of event names, checks `{"success": true}`, and exposes `next_event(timeout: float) -> dict | None` (returns the decoded payload, or `None` on timeout via `socket.settimeout` + catching `socket.timeout`), plus `close()` and context-manager support. Reuse the framing helpers; do not duplicate `_recv_exactly`.
   - `def subscribe(events: list[str]) -> EventStream` factory that tests can monkeypatch on the `ipc` module.
2. `wm.py`: `wait_seconds: float | None = Field(default=None, ge=0.1, le=60, description="For action=exec: wait up to this long for a new window and return it (con_id, class, name).")`.
   - Without `wait_seconds`: unchanged.
   - With it: open the stream **before** sending the exec command (so the `new` event cannot be missed), run the command, then read events until one has `change == "new"` or the deadline passes. Do the blocking work in a plain function executed via `asyncio.to_thread`. Return `ok(command=cmd, window=<record>, waited_seconds=<rounded>)` on success; on timeout `ok(command=cmd, window=None, timed_out=True, hint="The command was accepted but no new window appeared in time; check i3_query.")`. A command failure returns the usual `err`.
   - Build the record with `tree._record(container, workspace=None, output=container.get("output"), parent_layout=None)` (match the signature Task 4 gave `_record`; omit `parent_layout` if it is absent).
3. Tests: a `FakeEventStream` yielding canned payloads (`focus` then `new`, then `None`), monkeypatched via `ipc.subscribe`; assert the exec command is sent after subscription (order of operations), the `new` window is returned as a compact record, timeout returns `timed_out: true`, and `wait_seconds` outside `[0.1, 60]` is rejected by validation. In `tests/test_ipc.py`, frame a fake event with header type `0x80000003` through a fake socket and assert `next_event` decodes it.
4. README gotcha: replace "poll `i3_query`" with "pass `wait_seconds` to get the new window's con_id back".

**Acceptance:** full suite green; live check `i3_wm(action="exec", command="xterm -T probe", wait_seconds=5)` returns the window record within a second, then kill it.

**Commit:** `feat: exec can wait for the window it launches`

---

### Task 8: Docs, smoke coverage, final measurement

**Files:** `README.md`, `scripts/smoke.py`.

**Do:**

1. `scripts/smoke.py`: add steps for `resize grow width`, `scratchpad show` by criteria, `i3_query(what="layout")`, `i3_wm(exec, wait_seconds=5)` (use its returned `con_id` as the criteria for the following steps instead of polling), and a `title_window_icon` padding call. Keep the scratch-workspace-and-restore discipline.
2. `README.md`: Tools table gains the layout query and exec wait; Criteria section mentions `targets` in every mutator response and the "no window matches" error; Gotchas: exec commands may contain `;` and `,` freely (the tool quotes them), `wait_seconds`, centre is per-output with `absolute` for the whole screen. Delete the "poll i3_query" gotcha. Do not add config-specific examples.
3. Run the live smoke test and `scripts/schema_size.py`; put both outputs in the task report.

**Acceptance:** smoke passes on live i3; README matches the shipped surface.

**Commit:** `docs: README and smoke coverage for the polish round`

---

### Task 9: Trim tool argument descriptions

**Files:** every `i3mcp/tools/*.py`, `tests/test_schema.py`.

**Why:** After Task 3 the schema measures ~29,000 chars. `WindowCriteria` is spelled out once per criteria-taking tool by the protocol itself (about 1,400 chars × 8) and is already trimmed; the remaining slack is the 13 tools' flat argument descriptions (~5,900 chars) plus their docstrings. Each character there is paid by every client on every request.

**Do:**

1. Rewrite each `Field(description=...)` on the 13 tools to one short clause that tells an LLM when to use the field and what value shape it takes. Rules of thumb: no repetition of the field name; no repetition of information already in the `enum`/`Literal` values; no full sentences where a fragment does; the same wording for the same concept across tools (`by_number`, `no_auto_back_and_forth`, `criteria`, `unit`, `bar_id` appear in more than one tool). Keep every fact an LLM needs to choose correctly: e.g. `by_number` must still say it is for workspaces named like `"3: web"`; `unit` must still say ppt is percent of the parent; `wait_seconds` must still say what comes back.
2. Tighten tool docstrings to at most 3 lines where the extra lines only restate the field descriptions.
3. Lower `SIZE_CEILING` in `tests/test_schema.py` to **26,000** and make `test_only_window_criteria_is_left_as_a_def` allow exactly one `$defs` name (Task 4 has removed `ResponseFormat` by then).
4. Run `scripts/schema_size.py` before and after; put both in the report. Target: ≤ 24,000 chars total.

**Acceptance:** full suite green with the 26,000 ceiling; smoke passes; every tool still has a description that says what it does.

**Commit:** `perf: trim tool argument descriptions`
