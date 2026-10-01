# Tier 1 polish and background events — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut what every response and the tool list cost a model, fix the
bugs found in the 2026-10-01 read pass, and add a background event log an
agent can poll or block on.

**Architecture:** One `MCPServer` subclass owns schema compaction and the
text-only output default. Rendering switches to compact JSON. A daemon
thread keeps one SUBSCRIBE socket open and fills a ring buffer; a new
`i3_events` tool reads it by cursor, optionally waiting.

**Tech Stack:** Python 3.10+, `mcp` 2.2.0 (`MCPServer`), pydantic 2, stdlib
sockets/threads, pytest + pytest-asyncio.

**Spec:** the 2026-10-01 read-pass findings (conversation), scoped by the
user to Tier 1 (items 1–5) plus item 8 (waiting for events in the
background). Screenshots (6) and layout save/restore (7, overlaps with
i3-resurrect) are deferred.

## Global Constraints

- Runtime deps stay `mcp>=2` and `pydantic>=2`; nothing else.
- Never expose i3's `exit`.
- Docstrings ≤ 6 lines. Schema size is a goal: run `scripts/schema_size.py` before and after.
- Every emitted i3 command shape is verified live with `i3-msg` on a scratch
  workspace with a uniquely marked xterm; record and restore the focused workspace.
  A bare `workspace <word>` is never a safe probe (it creates the workspace).
- Fixtures and docs use generic names only.

## Baseline (measured 2026-10-01, mcp 2.1.1)

- 278 tests pass. Input schemas 23,952 chars; full tools/list 25,718
  (1,745 of it output schemas the size script does not count).
- A workspaces reply the model sees: 1,705 chars vs 844 compact.
  A 13-window tree reply: 6,855 vs 4,072. Raw `get_tree`: 32,914.
- WindowCriteria `$defs`: 1,112 chars, repeated in 7 tools (8,896 total).

---

### Task 1: Server subclass, text-only output, compact JSON, honest size script

**Files:**
- Modify: `i3mcp/server.py`, `i3mcp/tools/__init__.py`, `i3mcp/render.py`,
  `scripts/schema_size.py`, `pyproject.toml` (`mcp>=2.2`), `uv.lock`
- Test: `tests/test_schema.py`, `tests/test_render.py`

**Interfaces:**
- Produces: `i3mcp.server.I3Server(MCPServer)` with `tool()` defaulting
  `structured_output=False` and `list_tools()` returning compacted input schemas.
  `mcp` stays the module-level instance.

- [ ] Failing tests: every published tool has `output_schema is None`; a call
  result has `structured_content is None`; `render.ok(a=1)` has no newline and
  uses `","`/`":"` separators.
- [ ] Implement:

```python
class I3Server(MCPServer):
    def tool(self, *args, structured_output: bool | None = False, **kwargs):
        return super().tool(*args, structured_output=structured_output, **kwargs)

    async def list_tools(self):
        return [t.model_copy(update={"input_schema": compact(t.input_schema)})
                for t in await super().list_tools()]
```

  Delete the `_tool_manager` loop from `tools/__init__.py`.
  `render._dump` → `json.dumps(payload, separators=(",", ":"))`.
- [ ] `schema_size.py` reports full tools/list size (it already dumps the whole
  tool; add an `out` column for output schemas so a regression shows).
- [ ] Lower `SIZE_CEILING` to the new measurement plus ~8% headroom.
- [ ] Commit: `perf: text-only tool output and compact JSON replies`.

### Task 2: Compact workspaces and outputs

**Files:** Modify `i3mcp/tree.py` (add `workspace_record`, `output_record`),
`i3mcp/tools/query.py`. Test: `tests/test_tools_query.py`.

- [ ] Failing tests: `what="workspaces"` returns
  `{"con_id", "num", "name", "output", "rect": [x,y,w,h]}` plus `focused`/
  `visible`/`urgent` only when true; `num` omitted when < 0.
  `what="outputs"` returns `name`, `rect` list, and `active`/`primary`/
  `current_workspace` only when truthy.
- [ ] Implement with the existing `_compact` and `_rect_list`.
- [ ] Commit: `perf: compact workspace and output records`.

### Task 3: Bug fixes

**Files:** `i3mcp/tools/move.py`, `i3mcp/render.py`, `i3mcp/tree.py`,
`i3mcp/criteria.py`. Tests alongside.

- [ ] `i3_move(workspace="current", follow=true)` emits only the move: the
  window lands on the focused workspace, so there is nothing to follow, and
  `workspace current` creates a workspace named "current" (seen live).
- [ ] No-criteria targeting reports the focused *node*: when focus sits on a
  split container or an empty workspace, the target is
  `{"con_id", "type": "con"|"workspace", "windows": n}` instead of nothing.
  Add `tree.find_focused_node(tree_root) -> dict | None`.
- [ ] `\E` inside an exact/substring value: build the PCRE first, then escape
  the whole pattern for the i3 string:
  `escape_value(pattern_for(value, mode))`, with `pattern_for` splitting
  literal `\E` as `\E\\E\Q`. Verify live against an xterm titled with `\E`.
- [ ] Zero-match refusal with `match="exact"` adds `near_misses` (≤ 5 targets)
  for windows a case-insensitive substring match on the same fields would hit,
  and a hint naming `match="substring"`. This bridges i3_query's
  case-insensitive filters and exact criteria.
- [ ] Commit per fix.

### Task 4: Trim WindowCriteria

**Files:** `i3mcp/criteria.py`, `i3mcp/enums.py`. Test: `tests/test_criteria.py`.

- [ ] `urgent` accepts `latest | oldest` only (the rest are i3 synonyms).
- [ ] `window_type` becomes a plain string, description "e.g. 'dialog'";
  matching unchanged (exact). Zero matches still refuse before anything is sent.
- [ ] Re-measure; record the new number in `test_schema.py`'s comment.
- [ ] Commit: `perf: trim the shared criteria schema`.

### Task 5: Background event log and `i3_events`

**Files:**
- Create: `i3mcp/events.py`, `i3mcp/tools/events.py`, `tests/test_events.py`,
  `tests/test_tools_events.py`
- Modify: `i3mcp/ipc.py` (`EventStream.read_event()` blocking, returns
  `(event_number, payload)`), `i3mcp/server.py` (`main` starts the log),
  `i3mcp/tools/__init__.py`

**Interfaces:**
- `events.EventLog(stream_factory, maxlen=500)` with `ingest(number, payload)`,
  `read(since, filters, limit) -> dict`, `wait(since, filters, timeout) -> dict`,
  `start()`, `stop()`. `events.get_log()` / `events.set_log()` mirror `ipc`.
- Event entries: `{"seq", "event": "window"|"workspace"|"output"|"mode",
  "change", "ago": seconds}` plus `window` (con_id, name, window_class, marks,
  urgent) for window events, `current`/`old` workspace names for workspace
  events, `mode` name for mode events. A reconnect appends
  `{"event": "watcher", "change": "reconnected"}` so gaps are visible.

- [ ] Failing tests on `EventLog` without threads (ingest, cursor, filters by
  event/change/class/title, `dropped: true` when `since` predates the buffer,
  `wait` wakes on ingest from another thread, `wait` times out with
  `timed_out: true`).
- [ ] Failing tool tests: `i3_events()` returns recent events and `cursor`;
  `since` returns only newer; `wait_seconds` blocks then returns.
- [ ] Implement. Watcher thread: subscribe `["window","workspace","output","mode"]`,
  loop on `read_event`, on error back off 1→5 s and resubscribe.
- [ ] Live check: start the log, open the marked xterm, see `new` then `close`.
- [ ] Commit: `feat: background event log with i3_events`.

### Task 6: Docs, smoke, final verification

- [ ] README: tools table (14 tools), events section, exec-wait note pointing
  at `i3_events` for a specific window, `match` near-miss behaviour.
- [ ] `scripts/smoke.py`: an `i3_events` step around the existing window open.
- [ ] Full test run, `schema_size.py`, `smoke.py` against live i3.
- [ ] Commit: `docs: README and smoke for events and tier 1`.

## Deferred

- Screenshots as image content (item 6).
- Layout save/restore (item 7): revisit alongside i3-resurrect rather than duplicate it.
