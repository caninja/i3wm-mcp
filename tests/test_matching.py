import json

import pytest

from i3mcp import ipc, render, tree
from i3mcp.criteria import WindowCriteria
from tests.conftest import call, fixture_tree


def record(con_id: int) -> dict:
    for candidate in tree.walk_windows(fixture_tree()):
        if candidate["con_id"] == con_id:
            return candidate
    raise AssertionError(f"no fixture window with con_id {con_id}")


ALPHA = record(1001)
BETA = record(1002)
GAMMA = record(1003)


def test_exact_class_matches_the_whole_value():
    assert WindowCriteria(window_class="Alpha").matches(ALPHA)
    assert not WindowCriteria(window_class="Alph").matches(ALPHA)


def test_matching_is_case_sensitive():
    assert not WindowCriteria(window_class="alpha").matches(ALPHA)


def test_substring_matches_a_fragment():
    criteria = WindowCriteria(window_class="lph", match="substring")
    assert criteria.matches(ALPHA)
    assert not criteria.matches(BETA)


def test_regex_matches_a_pattern():
    criteria = WindowCriteria(title="^alpha .*e$", match="regex")
    assert criteria.matches(ALPHA)
    assert not criteria.matches(BETA)


def test_title_matches_the_record_name():
    assert WindowCriteria(title="beta two").matches(BETA)


def test_instance_and_role_match():
    assert WindowCriteria(instance="beta").matches(BETA)
    assert WindowCriteria(window_role="main").matches(BETA)
    assert not WindowCriteria(window_role="popup").matches(BETA)


def test_window_type_is_always_exact():
    assert WindowCriteria(window_type="normal", match="substring").matches(ALPHA)
    assert not WindowCriteria(window_type="dialog").matches(ALPHA)


def test_con_mark_matches_any_entry_of_marks():
    assert WindowCriteria(con_mark="m1").matches(ALPHA)
    assert not WindowCriteria(con_mark="m1").matches(BETA)


def test_workspace_matches_the_workspace_name():
    assert WindowCriteria(workspace="1").matches(ALPHA)
    assert WindowCriteria(workspace="2").matches(GAMMA)
    assert not WindowCriteria(workspace="2").matches(ALPHA)


def test_con_id_and_window_id_compare_by_equality():
    assert WindowCriteria(con_id=1002).matches(BETA)
    assert not WindowCriteria(con_id=1002).matches(ALPHA)
    assert WindowCriteria(window_id=2002).matches(BETA)


def test_floating_is_tri_state():
    assert WindowCriteria(floating=True).matches(BETA)
    assert not WindowCriteria(floating=True).matches(ALPHA)
    assert WindowCriteria(floating=False).matches(ALPHA)
    assert not WindowCriteria(floating=False).matches(BETA)
    unset = WindowCriteria(window_class="Beta")
    assert unset.matches(BETA)


def test_urgent_keyword_matches_any_urgent_window():
    assert WindowCriteria(urgent="latest").matches(GAMMA)
    assert not WindowCriteria(urgent="latest").matches(ALPHA)


def test_all_matches_every_window():
    criteria = WindowCriteria(all=True)
    assert criteria.matches(ALPHA)
    assert criteria.matches(BETA)
    assert criteria.matches(GAMMA)


def test_fields_are_anded():
    assert WindowCriteria(window_class="Alpha", workspace="1").matches(ALPHA)
    assert not WindowCriteria(window_class="Alpha", workspace="2").matches(ALPHA)


def test_a_missing_property_never_matches():
    assert not WindowCriteria(window_role="main").matches({"con_id": 5})


def test_invalid_regex_names_the_field():
    with pytest.raises(ValueError, match="title"):
        WindowCriteria(title="alpha(", match="regex").matches(ALPHA)


# --- run_targeted -----------------------------------------------------------


def test_zero_match_sends_nothing_and_explains(fake):
    result = json.loads(render.run_targeted(WindowCriteria(window_class="Nope"), "kill"))
    assert result["success"] is False
    assert result["error"] == "No window matches the criteria."
    assert result["criteria"] == r'[class="^\QNope\E$"]'
    assert "i3_query" in result["hint"]
    assert fake.commands == []


def test_targets_are_capped_at_twenty(fake):
    windows = []
    for index in range(25):
        windows.append({
            "type": "con",
            "id": 3000 + index,
            "window": 4000 + index,
            "name": f"many {index}",
            "floating": "auto_off",
            "marks": [],
            "rect": {},
            "window_type": "normal",
            "window_properties": {"class": "Many"},
            "nodes": [],
            "floating_nodes": [],
        })
    fake.query_replies[ipc.GET_TREE] = {
        "type": "root",
        "name": "root",
        "nodes": [{
            "type": "workspace",
            "name": "1",
            "num": 1,
            "output": "OUT-1",
            "layout": "splith",
            "nodes": windows,
            "floating_nodes": [],
        }],
        "floating_nodes": [],
    }
    result = json.loads(render.run_targeted(WindowCriteria(window_class="Many"), "kill"))
    assert result["target_count"] == 25
    assert len(result["targets"]) == 20


def test_tree_failure_is_reported(fake):
    def boom(msg_type, payload=""):
        raise ipc.I3Error("i3 closed the IPC connection")

    fake.query = boom
    result = json.loads(render.run_targeted(WindowCriteria(con_id=1001), "kill"))
    assert result["success"] is False
    assert "closed" in result["error"]
    assert fake.commands == []


# --- tool level -------------------------------------------------------------


async def test_kill_refuses_criteria_that_match_nothing(fake):
    result = json.loads(await call("i3_kill", criteria={"window_class": "Nope"}))
    assert result["success"] is False
    assert fake.commands == []


async def test_window_reports_its_target(fake):
    result = json.loads(await call("i3_window", criteria={"con_id": 1002}, floating="disable"))
    assert result["success"] is True
    assert result["command"] == "[con_id=1002] floating disable"
    assert result["targets"] == [{"con_id": 1002, "name": "beta two", "window_class": "Beta"}]
    assert result["target_count"] == 1


async def test_a_call_without_criteria_targets_the_focused_window(fake):
    result = json.loads(await call("i3_kill"))
    assert fake.last_command == "kill"
    assert result["targets"] == [{"con_id": 1001, "name": "alpha one", "window_class": "Alpha"}]
    assert result["target_count"] == 1


async def test_matching_several_windows_reports_them_all(fake):
    result = json.loads(await call("i3_mark", criteria={"all": True}, mark="every"))
    assert result["target_count"] == 3
    assert [target["con_id"] for target in result["targets"]] == [1001, 1002, 1003]


async def test_every_criteria_tool_refuses_a_miss(fake):
    misses = [
        ("i3_focus", {"criteria": {"window_class": "Nope"}}),
        ("i3_move", {"criteria": {"window_class": "Nope"}, "to_scratchpad": True}),
        ("i3_resize", {"criteria": {"window_class": "Nope"}, "mode": "set", "width": 100}),
        ("i3_kill", {"criteria": {"window_class": "Nope"}}),
        ("i3_window", {"criteria": {"window_class": "Nope"}, "floating": "enable"}),
        ("i3_layout", {"criteria": {"window_class": "Nope"}, "layout": "tabbed"}),
        ("i3_mark", {"criteria": {"window_class": "Nope"}, "mark": "x"}),
        ("i3_scratchpad", {"action": "move", "criteria": {"window_class": "Nope"}}),
    ]
    for name, arguments in misses:
        result = json.loads(await call(name, **arguments))
        assert result["success"] is False, name
        assert result["error"] == "No window matches the criteria.", name
    assert fake.commands == []


async def test_scratchpad_show_by_missing_mark_is_reported(fake):
    result = json.loads(await call("i3_scratchpad", action="show", mark="absent"))
    assert result["success"] is False
    assert fake.commands == []


async def test_focus_workspace_goes_through_the_tree_check(fake):
    result = json.loads(await call("i3_focus", criteria={"con_mark": "m1"}, focus_workspace=True))
    assert fake.last_command == r'[con_mark="^\Qm1\E$"] focus workspace'
    assert result["target_count"] == 1


async def test_an_invalid_regex_is_reported_as_an_error(fake):
    result = json.loads(await call("i3_kill", criteria={"title": "alpha(", "match": "regex"}))
    assert result["success"] is False
    assert "title" in result["error"]
    assert fake.commands == []
