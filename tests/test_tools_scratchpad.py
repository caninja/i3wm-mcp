import json

from i3mcp import ipc
from tests.conftest import call
from tests.test_tree import sample_tree


async def test_show_default_scratchpad(fake):
    await call("i3_scratchpad", action="show")
    assert fake.last_command == "scratchpad show"


async def test_show_by_mark_matches_what_move_stores(fake):
    await call("i3_scratchpad", action="show", mark="term")
    assert fake.last_command == r'[con_mark="^\Qterm\E$"] scratchpad show'


async def test_show_by_criteria(fake):
    await call("i3_scratchpad", action="show", criteria={"window_class": "term"})
    assert fake.last_command == r'[class="^\Qterm\E$"] scratchpad show'


async def test_show_rejects_mark_and_criteria_together(fake):
    result = json.loads(
        await call(
            "i3_scratchpad", action="show", mark="term", criteria={"window_class": "term"}
        )
    )
    assert result["success"] is False
    assert fake.commands == []


async def test_move_marks_then_moves(fake):
    await call("i3_scratchpad", action="move", mark="term")
    assert fake.last_command == 'mark --replace "term", move scratchpad'


async def test_move_without_mark(fake):
    await call("i3_scratchpad", action="move")
    assert fake.last_command == "move scratchpad"


async def test_move_with_criteria(fake):
    await call("i3_scratchpad", action="move", criteria={"con_id": 9}, mark="term")
    assert fake.last_command == '[con_id=9] mark --replace "term", move scratchpad'


async def test_hide_all_hides_visible_scratchpad_windows(fake):
    tree_with_visible = sample_tree()
    workspace = tree_with_visible["nodes"][0]["nodes"][1]["nodes"][0]
    workspace["floating_nodes"].append({
        "type": "floating_con",
        "id": 77,
        "nodes": [{
            "type": "con",
            "id": 78,
            "window": 780,
            "name": "visible scratch",
            "floating": "user_on",
            "scratchpad_state": "changed",
            "marks": [],
            "rect": {},
            "window_properties": {"class": "Alacritty"},
            "nodes": [],
            "floating_nodes": [],
        }],
        "floating_nodes": [],
    })
    fake.query_replies[ipc.GET_TREE] = tree_with_visible
    result = json.loads(await call("i3_scratchpad", action="hide_all"))
    assert result["hidden_count"] == 1
    assert fake.commands == ["[con_id=78] move scratchpad"]


async def test_hide_all_ignores_windows_already_in_the_scratchpad(fake):
    fake.query_replies[ipc.GET_TREE] = sample_tree()
    result = json.loads(await call("i3_scratchpad", action="hide_all"))
    assert result["hidden_count"] == 0
    assert fake.commands == []
