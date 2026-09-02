#!/usr/bin/env python3
"""Live smoke test. Exercises every tool against the running i3.

Uses xterm to launch a real window. Creates a scratch workspace, runs each
tool, and restores the previously focused workspace. Run it deliberately:

    uv run --with mcp --with pydantic python scripts/smoke.py
"""

from __future__ import annotations

import asyncio
import json
import sys

import i3mcp.tools  # noqa: F401  (registers every tool)
from i3mcp import ipc
from i3mcp.server import mcp

SCRATCH_WS = "i3mcp_smoke_test"

results: list[tuple[str, bool, str]] = []


async def call(name: str, /, **arguments) -> str:
    """Invoke a tool the way an MCP client does and return its text payload."""
    result = await mcp.call_tool(name, arguments)
    return result.content[0].text


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
        await check("workspace switch", call("i3_workspace", action="switch", name=SCRATCH_WS))

        # Read-only queries.
        for what in (
            "tree", "focused", "scratchpad", "workspaces", "outputs", "marks",
            "version", "config", "bar_config", "binding_modes", "binding_state",
        ):
            await check(f"query {what}", call("i3_query", what=what))

        # Commands that are safe with no window present.
        await check("gaps set 0", call("i3_gaps", gap="inner", amount=0))
        await check("gaps plus", call("i3_gaps", gap="inner", operation="plus", amount=0))
        await check("bar hidden_state", call("i3_bar", hidden_state="show"))
        await check("wm nop", call("i3_wm", action="nop", comment="smoke"))
        await check("workspace navigate", call("i3_workspace", action="navigate", direction="back_and_forth"))
        await check("workspace switch back", call("i3_workspace", action="switch", name=SCRATCH_WS))

        # Launch a window and wait for it directly, rather than polling
        # i3_query -- exec's wait_seconds hands back the new window's own
        # record, con_id included, which is the criteria the rest of this
        # run targets by.
        exec_result = await check(
            "wm exec",
            call("i3_wm", action="exec", command="xterm -T i3mcp-smoke", wait_seconds=5),
        )
        window = exec_result.get("window") or {}
        con_id = window.get("con_id")
        if con_id is None:
            results.append(("window appeared", False, "exec timed out waiting for a new window"))
            raise SystemExit

        by_id = {"con_id": con_id}
        await check("focus criteria", call("i3_focus", criteria=by_id))
        await check("mark set", call("i3_mark", criteria=by_id, mark="smoke"))
        by_mark = {"con_mark": "smoke"}
        await check("layout tabbed", call("i3_layout", criteria=by_mark, layout="tabbed"))
        await check("layout splith", call("i3_layout", criteria=by_mark, layout="splith"))
        await check("query layout", call("i3_query", what="layout", workspace=SCRATCH_WS))
        await check("window floating", call("i3_window", criteria=by_mark, floating="enable"))
        await check("window border", call("i3_window", criteria=by_mark, border="pixel", border_width=2))
        await check("window title_format", call("i3_window", criteria=by_mark, title_format="%title"))
        await check(
            "window icon padding",
            call(
                "i3_window",
                criteria=by_mark,
                title_window_icon="on",
                title_window_icon_padding=4,
            ),
        )
        await check("resize set px", call("i3_resize", criteria=by_mark, mode="set", width=600, height=400))
        # Grow/shrink needs a sibling to take space from once tiled -- this
        # scratch workspace has only one window, so exercise it here, while
        # still floating, where resize applies to the window itself.
        await check(
            "resize grow ppt",
            call("i3_resize", criteria=by_mark, mode="grow", direction="right", amount=1, unit="ppt"),
        )
        await check(
            "resize grow width",
            call("i3_resize", criteria=by_mark, mode="grow", direction="width", amount=10),
        )
        await check("move center", call("i3_move", criteria=by_mark, center=True))
        await check("move position", call("i3_move", criteria=by_mark, position_x=50, position_y=50))
        await check("window tiling", call("i3_window", criteria=by_mark, floating="disable"))
        await check("scratchpad move", call("i3_scratchpad", action="move", criteria=by_mark, mark="smoke"))
        await check("scratchpad show", call("i3_scratchpad", action="show", mark="smoke"))
        await check("scratchpad hide_all", call("i3_scratchpad", action="hide_all"))
        await check("scratchpad show by criteria", call("i3_scratchpad", action="show", criteria=by_mark))
        await check("mark unmark", call("i3_mark", criteria=by_mark, unmark="smoke"))

        await check("kill", call("i3_kill", criteria=by_id))

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
