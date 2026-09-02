import json

import pytest

from i3mcp import ipc
from tests.conftest import call

# Fixture layout for i3_query(what="layout"):
#
#   root
#     output OUT-1
#       con "content"
#         workspace "5" (num=5, splith)
#           con(splith) [workspace root container]
#             con(tabbed)       <- ids 11 (tab-one), 12 (tab-two)
#             con id 13 (lone)
#           floating_nodes: [floating_con -> con id 14 (float-one)]
#     output __i3
#       con "content"
#         workspace "__i3_scratch"  (unrelated, ignored)


def _leaf(con_id: int, window_id: int, name: str, cls: str, **extra) -> dict:
    node = {
        "type": "con",
        "id": con_id,
        "window": window_id,
        "name": name,
        "percent": None,
        "focused": False,
        "marks": [],
        "window_properties": {"class": cls, "instance": cls.lower()},
        "nodes": [],
        "floating_nodes": [],
    }
    node.update(extra)
    return node


def layout_fixture_tree() -> dict:
    tab_one = _leaf(11, 2011, "tab one", "TabOne", percent=0.5)
    tab_two = _leaf(12, 2012, "tab two", "TabTwo", percent=0.5, focused=True)
    lone = _leaf(13, 2013, "lone window", "Lone", percent=0.333333, marks=["solo"])
    float_one = _leaf(14, 2014, "float one", "FloatOne", percent=None)

    tabbed_container = {
        "type": "con",
        "id": 101,
        "layout": "tabbed",
        "percent": 0.666667,
        "nodes": [tab_one, tab_two],
        "floating_nodes": [],
    }

    workspace_root_container = {
        "type": "con",
        "id": 100,
        "layout": "splith",
        "percent": None,
        "nodes": [tabbed_container, lone],
        "floating_nodes": [],
    }

    dock_window = {
        "type": "con",
        "id": 999,
        "window": 9999,
        "name": "i3bar",
        "window_type": "dock",
        "window_properties": {"class": "i3bar"},
        "nodes": [],
        "floating_nodes": [],
    }

    return {
        "type": "root",
        "name": "root",
        "nodes": [
            {
                "type": "output",
                "name": "OUT-1",
                "nodes": [
                    {
                        "type": "dockarea",
                        "name": "topdock",
                        "nodes": [dock_window],
                        "floating_nodes": [],
                    },
                    {
                        "type": "con",
                        "name": "content",
                        "nodes": [
                            {
                                "type": "workspace",
                                "id": 50,
                                "name": "5",
                                "num": 5,
                                "output": "OUT-1",
                                "layout": "splith",
                                "nodes": [workspace_root_container],
                                "floating_nodes": [
                                    {
                                        "type": "floating_con",
                                        "id": 141,
                                        "layout": "splith",
                                        "nodes": [float_one],
                                        "floating_nodes": [],
                                    }
                                ],
                            },
                            {
                                "type": "workspace",
                                "id": 60,
                                "name": "6",
                                "num": 6,
                                "output": "OUT-1",
                                "layout": "splith",
                                "nodes": [],
                                "floating_nodes": [],
                            },
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
                                "id": 70,
                                "name": "__i3_scratch",
                                "num": -1,
                                "output": "__i3",
                                "nodes": [],
                                "floating_nodes": [],
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


@pytest.mark.asyncio
async def test_layout_by_workspace_name(fake):
    fake.query_replies[ipc.GET_TREE] = layout_fixture_tree()
    result = json.loads(await call("i3_query", what="layout", workspace="5"))
    assert result["success"] is True
    assert result["workspace"] == "5"
    assert result["workspace_num"] == 5

    nodes = result["nodes"]
    assert len(nodes) == 1
    root_container = nodes[0]
    assert root_container["layout"] == "splith"
    assert "percent" not in root_container  # None omitted

    tabbed, lone = root_container["nodes"]
    assert tabbed["layout"] == "tabbed"
    assert tabbed["percent"] == 0.67  # rounded to 2 decimals
    assert len(tabbed["nodes"]) == 2

    tab_one, tab_two = tabbed["nodes"]
    assert tab_one["con_id"] == 11
    assert tab_one["window_class"] == "TabOne"
    assert tab_one["percent"] == 0.5
    assert "focused" not in tab_one
    assert tab_two["con_id"] == 12
    assert tab_two["focused"] is True

    assert lone["con_id"] == 13
    assert lone["percent"] == 0.33
    assert lone["marks"] == ["solo"]

    floating = result["floating"]
    assert len(floating) == 1
    assert floating[0]["con_id"] == 14
    assert floating[0]["window_class"] == "FloatOne"
    assert "percent" not in floating[0]  # None omitted


@pytest.mark.asyncio
async def test_layout_by_workspace_number(fake):
    fake.query_replies[ipc.GET_TREE] = layout_fixture_tree()
    result = json.loads(await call("i3_query", what="layout", workspace="6"))
    assert result["success"] is True
    assert result["workspace"] == "6"
    assert result["nodes"] == []
    assert "floating" not in result


@pytest.mark.asyncio
async def test_layout_skips_dock_windows(fake):
    fake.query_replies[ipc.GET_TREE] = layout_fixture_tree()
    result = json.loads(await call("i3_query", what="layout", workspace="5"))
    dumped = json.dumps(result)
    assert "i3bar" not in dumped
    assert "9999" not in dumped


@pytest.mark.asyncio
async def test_layout_defaults_to_focused_workspace(fake):
    fake.query_replies[ipc.GET_TREE] = layout_fixture_tree()
    result = json.loads(await call("i3_query", what="layout"))
    assert result["success"] is True
    assert result["workspace"] == "5"  # contains the focused leaf (tab two)


@pytest.mark.asyncio
async def test_layout_unknown_workspace_errors(fake):
    fake.query_replies[ipc.GET_TREE] = layout_fixture_tree()
    result = json.loads(await call("i3_query", what="layout", workspace="does-not-exist"))
    assert result["success"] is False
    assert "does-not-exist" in result["error"]
    assert "hint" in result


@pytest.mark.asyncio
async def test_layout_no_focused_window_and_no_workspace_given_errors(fake):
    t = layout_fixture_tree()
    # Un-focus everything.
    tab_two = t["nodes"][0]["nodes"][1]["nodes"][0]["nodes"][0]["nodes"][0]["nodes"][1]
    assert tab_two["id"] == 12
    tab_two["focused"] = False
    fake.query_replies[ipc.GET_TREE] = t
    result = json.loads(await call("i3_query", what="layout"))
    assert result["success"] is False
    assert "focused" in result["error"].lower()


@pytest.mark.asyncio
async def test_layout_defaults_to_workspace_of_a_focused_floating_window(fake):
    t = layout_fixture_tree()
    workspace_five = t["nodes"][0]["nodes"][1]["nodes"][0]
    tab_two = workspace_five["nodes"][0]["nodes"][0]["nodes"][1]
    assert tab_two["id"] == 12
    tab_two["focused"] = False
    float_one = workspace_five["floating_nodes"][0]["nodes"][0]
    assert float_one["id"] == 14
    float_one["focused"] = True
    fake.query_replies[ipc.GET_TREE] = t
    result = json.loads(await call("i3_query", what="layout"))
    assert result["success"] is True
    assert result["workspace"] == "5"
    assert result["floating"][0]["con_id"] == 14
    assert result["floating"][0]["focused"] is True
