"""Compaction of the JSON schemas MCP publishes for every tool.

Pydantic emits a schema aimed at validators; a client pays for it in tokens on
every request. Three rewrites cut it roughly in half without changing which
arguments validate: titles are noise next to the property name, a nullable
field reads as `{"anyOf": [X, {"type": "null"}], "default": null}` where plain
X says the same to a model, and an explicit null default says nothing at all.
An omitted argument is still None, and an explicit null is still accepted:
validation runs against the pydantic model, not against what is published here.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# Keys whose values map a *name* to a schema. Their keys are user-chosen names,
# not schema keywords, so "title" there is a property called title, not a label.
_NAME_MAPS = ("properties", "$defs", "definitions", "patternProperties")

# Keys whose values are data, not schemas, and so must be left exactly as they are.
_OPAQUE = ("default", "enum", "const", "examples", "required")

_NULL = {"type": "null"}


def compact(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a smaller equivalent of a pydantic-generated JSON schema.

    Pure: the argument is deep-copied, never mutated.
    """
    return _compact_node(deepcopy(schema))


def _compact_node(node: Any) -> Any:
    if isinstance(node, list):
        return [_compact_node(item) for item in node]
    if not isinstance(node, dict):
        return node

    node.pop("title", None)
    for key, value in list(node.items()):
        if key in _OPAQUE:
            continue
        if key in _NAME_MAPS and isinstance(value, dict):
            node[key] = {name: _compact_node(sub) for name, sub in value.items()}
        else:
            node[key] = _compact_node(value)

    node = _collapse_nullable(node)
    if "default" in node and node["default"] is None:
        del node["default"]
    return node


def _collapse_nullable(node: dict[str, Any]) -> dict[str, Any]:
    """Fold `{"anyOf": [X, {"type": "null"}], ...}` into X plus its siblings."""
    options = node.get("anyOf")
    if not isinstance(options, list) or len(options) != 2 or _NULL not in options:
        return node
    other = options[1] if options[0] == _NULL else options[0]
    if not isinstance(other, dict):
        return node
    siblings = {key: value for key, value in node.items() if key != "anyOf"}
    return {**other, **siblings}
