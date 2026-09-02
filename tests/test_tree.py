from i3mcp import tree


def sample_tree():
    return {
        "type": "root",
        "name": "root",
        "nodes": [
            {
                "type": "output",
                "name": "DisplayPort-1",
                "nodes": [
                    {
                        "type": "dockarea",
                        "name": "topdock",
                        "nodes": [
                            {
                                "type": "con",
                                "id": 1,
                                "window": 111,
                                "name": "i3bar for output DisplayPort-1",
                                "floating": "auto_off",
                                "window_type": "dock",
                                "window_properties": {"class": "i3bar"},
                                "nodes": [],
                                "floating_nodes": [],
                            }
                        ],
                        "floating_nodes": [],
                    },
                    {
                        "type": "con",
                        "name": "content",
                        "nodes": [
                            {
                                "type": "workspace",
                                "name": "3",
                                "num": 3,
                                "output": "DisplayPort-1",
                                "layout": "splith",
                                "nodes": [
                                    {
                                        "type": "con",
                                        "id": 2,
                                        "window": 222,
                                        "name": "Firefox — front page",
                                        "floating": "auto_off",
                                        "focused": True,
                                        "urgent": False,
                                        "fullscreen_mode": 0,
                                        "marks": [],
                                        "layout": "splith",
                                        "rect": {"x": 0, "y": 0, "width": 800, "height": 600},
                                        "window_type": "normal",
                                        "window_properties": {
                                            "class": "firefox",
                                            "instance": "Navigator",
                                            "window_role": "browser",
                                        },
                                        "nodes": [],
                                        "floating_nodes": [],
                                    }
                                ],
                                "floating_nodes": [
                                    {
                                        "type": "floating_con",
                                        "id": 3,
                                        "nodes": [
                                            {
                                                "type": "con",
                                                "id": 4,
                                                "window": 444,
                                                "name": "Downloads - Thunar",
                                                "floating": "user_on",
                                                "focused": False,
                                                "urgent": False,
                                                "fullscreen_mode": 0,
                                                "marks": ["files"],
                                                "layout": "splith",
                                                "rect": {"x": 10, "y": 10, "width": 400, "height": 300},
                                                "window_type": "normal",
                                                "window_properties": {
                                                    "class": "Thunar",
                                                    "instance": "thunar",
                                                },
                                                "nodes": [],
                                                "floating_nodes": [],
                                            }
                                        ],
                                        "floating_nodes": [],
                                    }
                                ],
                            }
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
                                "name": "__i3_scratch",
                                "num": -1,
                                "output": "__i3",
                                "nodes": [],
                                "floating_nodes": [
                                    {
                                        "type": "floating_con",
                                        "id": 5,
                                        "nodes": [
                                            {
                                                "type": "con",
                                                "id": 6,
                                                "window": 666,
                                                "name": "scratch term",
                                                "floating": "user_on",
                                                "focused": False,
                                                "marks": ["term"],
                                                "scratchpad_state": "fresh",
                                                "rect": {"x": 0, "y": 0, "width": 10, "height": 10},
                                                "window_properties": {"class": "Alacritty"},
                                                "nodes": [],
                                                "floating_nodes": [],
                                            }
                                        ],
                                        "floating_nodes": [],
                                    }
                                ],
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


def test_walk_finds_every_window_including_docks_and_scratchpad():
    records = tree.walk_windows(sample_tree())
    assert {r["con_id"] for r in records} == {1, 2, 4, 6}


def test_records_carry_workspace_and_output_context():
    records = {r["con_id"]: r for r in tree.walk_windows(sample_tree())}
    assert records[2]["workspace"] == "3"
    assert records[2]["output"] == "DisplayPort-1"
    assert records[6]["workspace"] == "__i3_scratch"


def test_floating_read_from_floating_field_not_node_type():
    records = {r["con_id"]: r for r in tree.walk_windows(sample_tree())}
    assert records[4]["floating"] is True
    assert "floating" not in records[2]  # compact: False is omitted


def test_docks_excluded_by_default():
    records = tree.filter_windows(tree.walk_windows(sample_tree()))
    assert 1 not in {r["con_id"] for r in records}


def test_docks_included_on_request():
    records = tree.filter_windows(tree.walk_windows(sample_tree()), include_docks=True)
    assert 1 in {r["con_id"] for r in records}


def test_workspace_filter_actually_filters():
    records = tree.filter_windows(tree.walk_windows(sample_tree()), workspace="3")
    assert {r["con_id"] for r in records} == {2, 4}


def test_workspace_filter_rejects_unknown_workspace():
    assert tree.filter_windows(tree.walk_windows(sample_tree()), workspace="999") == []


def test_workspace_filter_matches_workspace_num_by_digits():
    t = sample_tree()
    workspace = t["nodes"][0]["nodes"][1]["nodes"][0]
    workspace["name"] = "3: web"
    records = tree.filter_windows(tree.walk_windows(t), workspace="3")
    assert {r["con_id"] for r in records} == {2, 4}


def test_floating_filter_matches_floating_windows():
    records = tree.filter_windows(tree.walk_windows(sample_tree()), floating=True)
    assert {r["con_id"] for r in records} == {4, 6}


def test_class_filter_is_case_insensitive_substring():
    records = tree.filter_windows(tree.walk_windows(sample_tree()), window_class="thunar")
    assert {r["con_id"] for r in records} == {4}


def test_scratchpad_filter_selects_scratchpad_workspace():
    records = tree.filter_windows(tree.walk_windows(sample_tree()), scratchpad=True)
    assert {r["con_id"] for r in records} == {6}


def test_find_focused():
    focused = tree.find_focused(tree.walk_windows(sample_tree()))
    assert focused["con_id"] == 2


def test_parent_layout_reflects_enclosing_container_or_floating():
    records = {r["con_id"]: r for r in tree.walk_windows(sample_tree())}
    assert records[2]["parent_layout"] == "splith"  # tiled directly under the workspace
    assert records[4]["parent_layout"] == "floating"  # under floating_nodes
    assert records[6]["parent_layout"] == "floating"  # scratchpad window, also floating


def test_tiled_focused_record_is_compact():
    records = {r["con_id"]: r for r in tree.walk_windows(sample_tree())}
    focused = records[2]
    assert focused["parent_layout"] == "splith"
    assert "layout" not in focused
    assert "floating" not in focused
    assert "urgent" not in focused


def test_workspace_num_included_only_when_non_negative():
    records = {r["con_id"]: r for r in tree.walk_windows(sample_tree())}
    assert records[2]["workspace_num"] == 3
    assert "workspace_num" not in records[6]  # scratchpad workspace num is -1


def test_sticky_true_adds_sticky_key():
    t = sample_tree()
    workspace = t["nodes"][0]["nodes"][1]["nodes"][0]
    workspace["nodes"][0]["sticky"] = True
    records = {r["con_id"]: r for r in tree.walk_windows(t)}
    assert records[2]["sticky"] is True


def test_sticky_absent_when_false():
    records = {r["con_id"]: r for r in tree.walk_windows(sample_tree())}
    assert "sticky" not in records[2]


def test_rect_is_a_four_element_list():
    records = {r["con_id"]: r for r in tree.walk_windows(sample_tree())}
    assert records[2]["rect"] == [0, 0, 800, 600]


def test_parent_layout_is_floating_even_when_floating_con_carries_its_own_layout():
    # i3 4.25.1 puts a real "layout": "splith" on the floating_con wrapper itself
    # (verified live); that value must not leak out as the window's parent_layout.
    t = sample_tree()
    workspace = t["nodes"][0]["nodes"][1]["nodes"][0]
    workspace["floating_nodes"][0]["layout"] = "splith"
    records = {r["con_id"]: r for r in tree.walk_windows(t)}
    assert records[4]["parent_layout"] == "floating"
