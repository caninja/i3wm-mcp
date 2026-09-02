"""Schema compaction: the unit rules, and what a client actually receives."""

import json
from copy import deepcopy

import pytest

import i3mcp.tools  # noqa: F401  (registers every tool)
from i3mcp.schema import compact
from i3mcp.server import mcp

# A ceiling with headroom, not a target. Measured: 43,609 chars before compaction,
# 29,154 after it, and 23,889 once the argument descriptions were trimmed. The floor
# is WindowCriteria, whose $defs entry is still spelled out in each of the 8 tools
# that take criteria (~1.1k x 8 = ~8.9k of what is left).
SIZE_CEILING = 26_000

# Keys whose values map a name to a schema, so their keys are names, not keywords.
NAME_MAPS = ("properties", "$defs")


def schema_nodes(node):
    """Yield every dict that sits in a schema position, root included."""
    if isinstance(node, dict):
        yield node
        for key, value in node.items():
            if key in NAME_MAPS and isinstance(value, dict):
                for child in value.values():
                    yield from schema_nodes(child)
            elif key not in ("default", "enum", "const", "examples"):
                yield from schema_nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from schema_nodes(item)


def test_titles_are_stripped_at_every_level():
    got = compact(
        {
            "title": "i3_thing_arguments",
            "type": "object",
            "properties": {"mark": {"title": "Mark", "type": "string"}},
            "$defs": {"Unit": {"title": "Unit", "enum": ["px", "ppt"], "type": "string"}},
        }
    )
    assert got == {
        "type": "object",
        "properties": {"mark": {"type": "string"}},
        "$defs": {"Unit": {"enum": ["px", "ppt"], "type": "string"}},
    }


def test_a_property_named_title_survives():
    got = compact({"properties": {"title": {"title": "Title", "type": "string"}}})
    assert got == {"properties": {"title": {"type": "string"}}}


def test_nullable_anyof_collapses_and_keeps_description():
    got = compact(
        {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "Window title.",
            "title": "Title",
        }
    )
    assert got == {"type": "string", "description": "Window title."}


def test_nullable_ref_collapses_to_the_ref():
    got = compact(
        {
            "anyOf": [{"$ref": "#/$defs/WindowCriteria"}, {"type": "null"}],
            "default": None,
            "description": "Which window.",
        }
    )
    assert got == {"$ref": "#/$defs/WindowCriteria", "description": "Which window."}


def test_a_genuine_union_is_left_alone():
    schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    assert compact(schema) == schema


def test_bare_null_default_is_dropped():
    assert compact({"type": "string", "default": None}) == {"type": "string"}


def test_meaningful_keywords_survive():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["mode"],
        "description": "A thing.",
        "properties": {
            "mode": {"enum": ["grow", "shrink"], "type": "string"},
            "amount": {"type": "integer", "default": 10, "minimum": 1, "maximum": 99},
            "unit": {"enum": ["px", "ppt"], "type": "string", "default": "px"},
        },
    }
    assert compact(deepcopy(schema)) == schema


def test_compact_does_not_mutate_its_argument():
    schema = {"title": "Root", "properties": {"a": {"title": "A", "type": "string"}}}
    before = deepcopy(schema)
    compact(schema)
    assert schema == before


@pytest.fixture
async def published_schemas():
    return {tool.name: tool.input_schema for tool in await mcp.list_tools()}


async def test_published_schemas_carry_no_titles(published_schemas):
    for name, schema in published_schemas.items():
        for node in schema_nodes(schema):
            assert "title" not in node, f"{name}: {node}"


async def test_published_schemas_have_no_nullable_anyof(published_schemas):
    for name, schema in published_schemas.items():
        for node in schema_nodes(schema):
            options = node.get("anyOf")
            if options is not None:
                assert {"type": "null"} not in options, f"{name}: {options}"


async def test_only_window_criteria_is_left_as_a_def(published_schemas):
    allowed = {"WindowCriteria"}
    for name, schema in published_schemas.items():
        assert set(schema.get("$defs", {})) <= allowed, name


async def test_total_published_size_stays_under_the_ceiling():
    tools = await mcp.list_tools()
    total = sum(
        len(json.dumps(tool.model_dump(exclude_none=True, by_alias=True), separators=(",", ":")))
        for tool in tools
    )
    assert total < SIZE_CEILING, f"{total} chars"
