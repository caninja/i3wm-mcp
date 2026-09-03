from i3mcp import tree


def sample_tree():
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
                        "layout": "dockarea",
                        "nodes": [
                            {
                                "type": "con",
                                "id": 1,
                                "window": 111,
                                "name": "bar for output OUT-1",
                                "floating": "auto_off",
                                "layout": "splith",
                                "window_type": "unknown",
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
                                "output": "OUT-1",
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
                                        "scratchpad_state": "none",
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
                                                "name": "Downloads - Files",
                                                "floating": "user_on",
                                                "focused": False,
                                                "urgent": False,
                                                "fullscreen_mode": 0,
                                                "marks": ["files"],
                                                "layout": "splith",
                                                "rect": {"x": 10, "y": 10, "width": 400, "height": 300},
                                                "window_type": "normal",
                                                "scratchpad_state": "none",
                                                "window_properties": {
                                                    "class": "Files",
                                                    "instance": "files",
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
                                        "scratchpad_state": "fresh",
                                        "nodes": [
                                            {
                                                "type": "con",
                                                "id": 6,
                                                "window": 666,
                                                "name": "scratch term",
                                                "floating": "user_on",
                                                "focused": False,
                                                "marks": ["term"],
                                                "scratchpad_state": "none",
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
    assert records[2]["output"] == "OUT-1"
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
    records = tree.filter_windows(tree.walk_windows(sample_tree()), window_class="files")
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


def test_outline_by_workspace_name_lists_leaf_and_floating_windows():
    result = tree.outline(sample_tree(), "3")
    assert result["workspace"] == "3"
    assert result["workspace_num"] == 3
    assert len(result["nodes"]) == 1
    leaf = result["nodes"][0]
    assert leaf["con_id"] == 2
    assert leaf["window_class"] == "firefox"
    assert leaf["focused"] is True
    assert "layout" not in leaf  # leaves have no layout of their own
    assert result["floating"] == [
        {"con_id": 4, "name": "Downloads - Files", "window_class": "Files", "marks": ["files"]}
    ]


def test_outline_unknown_workspace_returns_none():
    assert tree.outline(sample_tree(), "no-such-workspace") is None


def test_outline_none_workspace_finds_the_focused_leafs_workspace():
    result = tree.outline(sample_tree(), None)
    assert result["workspace"] == "3"


def test_outline_none_workspace_returns_none_when_nothing_focused():
    t = sample_tree()
    firefox = t["nodes"][0]["nodes"][1]["nodes"][0]["nodes"][0]
    firefox["focused"] = False
    assert tree.outline(t, None) is None


def test_outline_skips_dock_windows():
    result = tree.outline(sample_tree(), "3")
    dumped_ids = {node["con_id"] for node in result["nodes"]} | {node["con_id"] for node in result["floating"]}
    assert 1 not in dumped_ids  # the i3bar dock window's con_id never appears


def test_scratchpad_state_comes_from_the_floating_con_wrapper():
    # i3 4.25.1 stores scratchpad_state on the enclosing floating_con; the
    # window con below it always reads "none" (verified live).
    records = {r["con_id"]: r for r in tree.walk_windows(sample_tree())}
    assert records[6]["scratchpad_state"] == "fresh"


def test_scratchpad_state_is_omitted_when_the_window_is_not_a_scratchpad():
    records = {r["con_id"]: r for r in tree.walk_windows(sample_tree())}
    assert "scratchpad_state" not in records[2]  # tiled, "none" in the tree
    assert "scratchpad_state" not in records[4]  # floating, wrapper has no state


def test_dock_is_recognised_by_its_dockarea_parent():
    # On i3 4.25.1 the i3bar window reports window_type "unknown"; what marks
    # it is the enclosing dockarea node (verified live).
    records = {r["con_id"]: r for r in tree.walk_windows(sample_tree())}
    assert records[1]["parent_layout"] == "dockarea"
    assert records[1]["window_type"] == "unknown"
    assert tree.is_dock(records[1]) is True


def _empty_focused_workspace_tree():
    t = sample_tree()
    workspace = t["nodes"][0]["nodes"][1]["nodes"][0]
    workspace["nodes"] = []
    workspace["floating_nodes"] = []
    workspace["focused"] = True
    return t


def test_outline_none_workspace_finds_an_empty_focused_workspace():
    result = tree.outline(_empty_focused_workspace_tree(), None)
    assert result["workspace"] == "3"
    assert result["nodes"] == []
