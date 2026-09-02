# i3wm-mcp Overhaul — Design

**Date:** 2026-09-02
**Status:** Approved
**Target:** i3 4.25.1 (verified live), Python 3.10+, `mcp>=2`

## Problem

A sweep of `i3_mcp.py` (3,679 lines, 43 tools) cross-referenced against the
i3 userguide and a live i3 4.25.1 found the server broken on fresh install,
several tools non-functional, and large gaps in i3 coverage.

### Verified defects

| # | Defect | Evidence |
|---|--------|----------|
| 1 | `from mcp.server.fastmcp import FastMCP` fails on `mcp` 2.x (renamed `MCPServer`). No dependency manifest, so a fresh install gets 2.x and the server never starts. | `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` |
| 2 | All three gaps tools emit `workspace`/`global` as the scope token; i3 requires `current`/`all`. | `"Expected one of these tokens: 'current', 'all'"` |
| 3 | `i3_gaps_adjust` calls `.value` on `Literal[...]` fields (plain `str`, not `Enum`) and crashes before reaching i3. | `AttributeError: 'str' object has no attribute 'value'` |
| 4 | `i3_gaps_set` uses `if not params.inner`, so `inner=0` is rejected as "not specified". | `"Must specify at least one of: inner, outer"` |
| 5 | Floating detection tests `node["type"] == "floating_con"`. Window nodes are `type: con` with a separate `floating: user_on\|auto_off` field, so the test never matches. | `floating=True` → 0 windows; live tree shows `type=con floating=user_on` |
| 6 | The `workspace` filter in `i3_get_tree` is a literal `pass`. | `workspace="999"` returned all 14 windows |
| 7 | `i3_focus_by_criteria` emits `urgent=yes`; i3 accepts only `latest\|oldest\|newest\|last\|recent\|first`. | `"You have to specify which window/container should be focused"` |
| 8 | `i3_scratchpad_move` stores a **mark**; `i3_scratchpad_show` looks up by `[title=...]`. They cannot find each other. | Code inspection |
| 9 | `i3-msg` exits 2 on failure; `check=True` raises and discards the JSON body carrying `parse_error` / `errorposition`. `run_i3_msg` also never inspects `output[0]["success"]`. | Live: exit 2 with rich JSON on stdout |
| 10 | `truncate_response` hard-slices JSON at 25,000 chars, returning invalid JSON. | Code inspection |

### Coverage gaps vs. the i3 userguide

- Criteria work only for `focus`. Every other mutator acts on the focused
  window, so a named window cannot be closed or moved without focusing first.
- No `ppt` support anywhere (`resize grow width 10 ppt`, `resize set 50 ppt`,
  `move left 10 ppt`).
- `workspace number <n>` missing — with named workspaces (`"3: web"`),
  `workspace 3` creates a new workspace instead of switching.
- Missing: `reload`, `restart`, `append_layout`, `title_format`,
  `title_window_icon`, `focus next|prev [sibling]`, `[criteria] focus workspace`,
  `move container to workspace next|prev|current`, `nop`, `shmlog`, `debuglog`,
  `--no-auto-back-and-forth`, standalone `move workspace to output`.
- Missing IPC: `send_tick`, `subscribe`.
- Window listings include i3bar dock windows as real windows.
- Window records omit `con_id` (the only stable criteria handle) and the
  containing workspace/output.

### Structural problems

- 43 tools carrying 31,357 chars of docstring (~8k tokens) plus 43 JSON
  schemas, billed on every request in every session.
- Tools take a single `params: Model` argument, forcing calls through
  `{"params": {...}}` with a `$defs`/`$ref` indirection.
- 3,679 lines in one file; ~250 lines of duplicated `ConfigDict` boilerplate;
  `i3_get_bar_config` bypasses the helpers with its own `subprocess` call.
- No tests, no packaging.
- Unescaped quotes in user strings inject into i3 command syntax. Not a shell
  escape (`i3-msg` is invoked with argv), but `mark_as='x"; exec foo; mark "y'`
  does inject i3 commands.

## Decisions

### D1 — Transport: native IPC socket, no new dependencies

Replace per-call `subprocess` forks with i3's IPC protocol over the unix
socket. Stdlib only (`socket`, `struct`, `json`).

Protocol, verified live against i3 4.25.1:

- Socket path from `$I3SOCK`, else `i3 --get-socketpath`.
- Request: `b"i3-ipc"` + `struct.pack("=II", len(payload), msg_type)` + payload.
- Reply: identical 14-byte header, then `length` bytes of JSON.
- Message types: `RUN_COMMAND=0`, `GET_WORKSPACES=1`, `SUBSCRIBE=2`,
  `GET_OUTPUTS=3`, `GET_TREE=4`, `GET_MARKS=5`, `GET_BAR_CONFIG=6`,
  `GET_VERSION=7`, `GET_BINDING_MODES=8`, `GET_CONFIG=9`, `SEND_TICK=10`,
  `SYNC=11`, `GET_BINDING_STATE=12`.

`RUN_COMMAND` replies are an **array**, one entry per sub-command — verified:
`resize set width 60 ppt` returned `[{success:false,…},{success:false}]`.
Success is therefore `all(r.get("success") for r in reply)`, and failures
surface i3's own `error`, `parse_error` and `errorposition`.

Rejected: the `i3ipc` library (adds a dependency and a large unused API
surface); keeping `subprocess` (retains the fork and rules out events).

### D2 — Shared criteria on every mutator

One `WindowCriteria` model reused by every mutating tool. Omitted → the
command acts on the focused window, matching today's behaviour.

Fields: `window_class`, `instance`, `title`, `window_role`, `window_type`,
`machine`, `con_id`, `con_mark`, `window_id`, `workspace`, `floating`,
`tiling`, `urgent`, `all`.

`urgent` is constrained to `latest|oldest|newest|last|recent|first`.

String values carry a `match` mode, defaulting to **exact**:

| mode | emitted |
|------|---------|
| `exact` | `^\Qvalue\E$` |
| `substring` | `\Qvalue\E` |
| `regex` | value verbatim |

Verified live: i3's PCRE accepts `\Q…\E`, and `\"` escapes correctly inside a
quoted criteria value. Escaping rule: backslash first, then double quote.

### D3 — Tool surface: 43 → 13, flat arguments

Flat keyword arguments rather than a `params` wrapper. Criteria remains a
nested object. Docstrings capped at ~6 lines; detail lives in `Field`
descriptions, which are already paid for in the schema.

| Tool | Scope |
|------|-------|
| `i3_query` | `what` = tree/focused/workspaces/outputs/marks/scratchpad/version/config/bar_config/binding_modes/binding_state |
| `i3_focus` | direction, parent/child, floating/tiling/mode_toggle, next/prev [sibling], output, criteria, `[criteria] focus workspace` |
| `i3_move` | direction (+px/ppt), position (abs/center/mouse), workspace (name/number/next/prev/current), output, mark, scratchpad, swap_with |
| `i3_resize` | grow/shrink (px/ppt), `resize set` width/height (px/ppt) |
| `i3_kill` | criteria-aware, `destructiveHint: true` |
| `i3_window` | floating, sticky, fullscreen, border, title_format, title_window_icon |
| `i3_layout` | layout and split |
| `i3_workspace` | switch, number, rename, move-to-output, navigate, bulk-move |
| `i3_mark` | set, unset |
| `i3_scratchpad` | show, move, hide_all — all keyed on marks |
| `i3_gaps` | 8 gap types × current/all × set/plus/minus/toggle |
| `i3_bar` | mode, hidden_state |
| `i3_wm` | exec, reload, restart, mode, nop, shmlog, debuglog, append_layout |

`exit` is deliberately not exposed — killing the user's session is not
something a tool call should be able to do by accident.

### D4 — Query output

Every window record gains `con_id`, `workspace` and `output`. `floating` is
read from the real `floating` field. i3bar dock windows are excluded unless
`include_docks=true`. JSON responses that exceed the character budget drop
whole entries and report the count elided, instead of slicing mid-structure.

### D5 — Package layout

`i3_mcp.py` stays as the entry point so existing MCP configs keep working; it
becomes a two-line shim over the `i3mcp` package.

### D6 — Packaging and tests

`pyproject.toml` declaring `mcp>=2` and `pydantic>=2`, installable with
`uv run` / `uvx`. `MCPServer` is decorator-compatible with the existing code
(`@mcp.tool(name=…, annotations={…})`, `mcp.run()`), verified against mcp 2.1.1.

Two layers of test:

- `pytest` against a stubbed transport, asserting the exact i3 command string
  each tool emits. Catches every defect in the table above with no running i3.
- `scripts/smoke.py`, opt-in, exercising every tool against real i3 on a
  scratch workspace and restoring state. Catches syntax i3 rejects — the
  failure mode that produced defects 2, 3 and 7.

## Out of scope

- Event subscription (`SUBSCRIBE`). The transport makes it possible; no tool
  exposes it yet.
- sway compatibility.
- Any `exit` / session-terminating command.
