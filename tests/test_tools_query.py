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
