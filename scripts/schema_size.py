#!/usr/bin/env python3
"""Report how many characters of JSON schema every MCP client pays for.

Serialises each tool exactly the way an MCP client receives it, so the numbers
are comparable across runs:

    uv run --with mcp --with pydantic python scripts/schema_size.py
"""

from __future__ import annotations

import asyncio
import json

import i3mcp.tools  # noqa: F401  (registers every tool)
from i3mcp.server import mcp

CHARS_PER_TOKEN = 3.5


def _dump(value: object) -> str:
    return json.dumps(value, separators=(",", ":"))


def _description_chars(node: object) -> int:
    """Total characters of every "description" string, at every depth."""
    if isinstance(node, dict):
        total = 0
        for key, value in node.items():
            if key == "description" and isinstance(value, str):
                total += len(value)
            else:
                total += _description_chars(value)
        return total
    if isinstance(node, list):
        return sum(_description_chars(item) for item in node)
    return 0


async def main() -> None:
    tools = await mcp.list_tools()
    rows: list[tuple[str, int, int, int]] = []
    for tool in tools:
        payload = tool.model_dump(exclude_none=True, by_alias=True)
        schema = payload.get("inputSchema") or {}
        rows.append(
            (
                tool.name,
                len(_dump(payload)),
                len(_dump(schema["$defs"])) if "$defs" in schema else 0,
                _description_chars(payload),
            )
        )

    print(f"{'tool':<16}{'total':>9}{'$defs':>9}{'descs':>9}")
    print("-" * 43)
    for name, total, defs, descs in sorted(rows, key=lambda row: -row[1]):
        print(f"{name:<16}{total:>9}{defs:>9}{descs:>9}")
    print("-" * 43)
    total = sum(row[1] for row in rows)
    defs = sum(row[2] for row in rows)
    descs = sum(row[3] for row in rows)
    print(f"{f'{len(rows)} tools':<16}{total:>9}{defs:>9}{descs:>9}")
    print(f"\n{total} chars total, ~{total / CHARS_PER_TOKEN:,.0f} tokens at {CHARS_PER_TOKEN} chars/token")


if __name__ == "__main__":
    asyncio.run(main())
