import json

import pytest

from i3mcp import ipc
from tests.conftest import call
from tests.test_tree import sample_tree


@pytest.mark.asyncio
async def test_query_tree_returns_records_with_context(fake):
    fake.query_replies[ipc.GET_TREE] = sample_tree()
    result = json.loads(await call("i3_query", what="tree"))
    assert result["success"] is True
    con_ids = {w["con_id"] for w in result["windows"]}
    assert con_ids == {2, 4, 6}  # dock excluded
    firefox = next(w for w in result["windows"] if w["con_id"] == 2)
    assert firefox["workspace"] == "3"
    assert firefox["parent_layout"] == "splith"
    assert "floating" not in firefox
    assert "layout" not in firefox


@pytest.mark.asyncio
async def test_query_tree_workspace_filter(fake):
    fake.query_replies[ipc.GET_TREE] = sample_tree()
    result = json.loads(await call("i3_query", what="tree", workspace="999"))
    assert result["windows"] == []


@pytest.mark.asyncio
async def test_query_tree_floating_filter(fake):
    fake.query_replies[ipc.GET_TREE] = sample_tree()
    result = json.loads(await call("i3_query", what="tree", floating=True))
    assert {w["con_id"] for w in result["windows"]} == {4, 6}


@pytest.mark.asyncio
async def test_query_focused(fake):
    fake.query_replies[ipc.GET_TREE] = sample_tree()
    result = json.loads(await call("i3_query", what="focused"))
    assert result["window"]["con_id"] == 2


@pytest.mark.asyncio
async def test_query_scratchpad(fake):
    fake.query_replies[ipc.GET_TREE] = sample_tree()
    result = json.loads(await call("i3_query", what="scratchpad"))
    assert {w["con_id"] for w in result["windows"]} == {6}


@pytest.mark.asyncio
async def test_query_workspaces(fake):
    fake.query_replies[ipc.GET_WORKSPACES] = [
        {"num": 3, "name": "3", "output": "DisplayPort-1", "focused": True, "visible": True, "urgent": False}
    ]
    result = json.loads(await call("i3_query", what="workspaces"))
    assert result["workspaces"][0]["name"] == "3"


@pytest.mark.asyncio
async def test_query_version(fake):
    fake.query_replies[ipc.GET_VERSION] = {"human_readable": "4.25.1"}
    result = json.loads(await call("i3_query", what="version"))
    assert result["version"]["human_readable"] == "4.25.1"


@pytest.mark.asyncio
async def test_query_config_omits_body_unless_asked(fake):
    fake.query_replies[ipc.GET_CONFIG] = {"config": "x" * 5000, "included_configs": []}
    result = json.loads(await call("i3_query", what="config"))
    assert "config" not in result
    assert result["config_length"] == 5000
    full = json.loads(await call("i3_query", what="config", include_config_body=True))
    assert len(full["config"]) == 5000


@pytest.mark.asyncio
async def test_query_bar_config_by_id(fake):
    fake.query_replies[ipc.GET_BAR_CONFIG] = {"id": "bar-0", "position": "top"}
    result = json.loads(await call("i3_query", what="bar_config", bar_id="bar-0"))
    assert result["bar_config"]["position"] == "top"


@pytest.mark.asyncio
async def test_query_tree_workspace_num_filter_matches_digits(fake):
    t = sample_tree()
    workspace = t["nodes"][0]["nodes"][1]["nodes"][0]
    workspace["name"] = "3: web"
    fake.query_replies[ipc.GET_TREE] = t
    result = json.loads(await call("i3_query", what="tree", workspace="3"))
    assert {w["con_id"] for w in result["windows"]} == {2, 4}


@pytest.mark.asyncio
async def test_query_workspaces_records_are_compact(fake):
    fake.query_replies[ipc.GET_WORKSPACES] = [
        {
            "id": 77, "num": 2, "name": "2: mail", "visible": True, "focused": False,
            "urgent": False, "output": "OUT-1",
            "rect": {"x": 0, "y": 20, "width": 800, "height": 580},
        },
        {
            "id": 78, "num": -1, "name": "notes", "visible": False, "focused": False,
            "urgent": False, "output": "OUT-1",
            "rect": {"x": 0, "y": 20, "width": 800, "height": 580},
        },
    ]
    result = json.loads(await call("i3_query", what="workspaces"))
    assert result["workspaces"] == [
        {"con_id": 77, "num": 2, "name": "2: mail", "output": "OUT-1",
         "rect": [0, 20, 800, 580], "visible": True},
        {"con_id": 78, "name": "notes", "output": "OUT-1", "rect": [0, 20, 800, 580]},
    ]


@pytest.mark.asyncio
async def test_query_outputs_records_are_compact(fake):
    fake.query_replies[ipc.GET_OUTPUTS] = [
        {"name": "OUT-1", "active": True, "primary": True, "current_workspace": "1",
         "rect": {"x": 0, "y": 0, "width": 800, "height": 600}},
        {"name": "OUT-2", "active": False, "primary": False, "current_workspace": None,
         "rect": {"x": 0, "y": 0, "width": 0, "height": 0}},
    ]
    result = json.loads(await call("i3_query", what="outputs"))
    assert result["outputs"] == [
        {"name": "OUT-1", "rect": [0, 0, 800, 600], "active": True, "primary": True,
         "current_workspace": "1"},
        {"name": "OUT-2", "rect": [0, 0, 0, 0]},
    ]
