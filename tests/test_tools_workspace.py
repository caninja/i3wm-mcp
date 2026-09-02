import json

from i3mcp import ipc
from tests.conftest import call


async def test_switch_by_name(fake):
    await call("i3_workspace", action="switch", name="web")
    assert fake.last_command == 'workspace "web"'


async def test_switch_by_number(fake):
    await call("i3_workspace", action="switch", name="3", by_number=True)
    assert fake.last_command == "workspace number 3"


async def test_switch_no_auto_back_and_forth(fake):
    await call("i3_workspace", action="switch", name="web", no_auto_back_and_forth=True)
    assert fake.last_command == 'workspace --no-auto-back-and-forth "web"'


async def test_switch_navigation_keyword_unquoted(fake):
    await call("i3_workspace", action="switch", name="next")
    assert fake.last_command == "workspace next"


async def test_navigate_next(fake):
    await call("i3_workspace", action="navigate", direction="next")
    assert fake.last_command == "workspace next"


async def test_navigate_back_and_forth(fake):
    await call("i3_workspace", action="navigate", direction="back_and_forth")
    assert fake.last_command == "workspace back_and_forth"


async def test_rename_focused(fake):
    await call("i3_workspace", action="rename", new_name="work")
    assert fake.last_command == 'rename workspace to "work"'


async def test_rename_specific(fake):
    await call("i3_workspace", action="rename", name="1", new_name="browser")
    assert fake.last_command == 'rename workspace "1" to "browser"'


async def test_move_to_output(fake):
    await call("i3_workspace", action="move_to_output", output="HDMI-1")
    assert fake.last_command == 'move workspace to output "HDMI-1"'


async def test_move_named_workspace_to_output_switches_first(fake):
    await call("i3_workspace", action="move_to_output", name="3", output="HDMI-1")
    assert fake.last_command == 'workspace "3"; move workspace to output "HDMI-1"'


async def test_bulk_move_skips_unknown_workspaces(fake):
    fake.query_replies[ipc.GET_WORKSPACES] = [
        {"name": "1", "output": "OUT-2"},
        {"name": "2", "output": "OUT-2"},
    ]
    result = json.loads(
        await call("i3_workspace", action="bulk_move", names=["1", "2", "99"], output="HDMI-1")
    )
    assert result["moved"] == ["1", "2"]
    assert result["skipped"][0]["name"] == "99"
    assert len(fake.commands) == 2


async def test_bulk_move_preserves_one_workspace(fake):
    fake.query_replies[ipc.GET_WORKSPACES] = [
        {"name": "1", "output": "OUT-2"},
        {"name": "2", "output": "OUT-2"},
    ]
    result = json.loads(
        await call("i3_workspace", action="bulk_move", names=["1", "2"], output="HDMI-1", preserve="2")
    )
    assert result["moved"] == ["1"]


async def test_switch_requires_a_name(fake):
    result = json.loads(await call("i3_workspace", action="switch"))
    assert result["success"] is False
    assert fake.commands == []


async def test_move_to_output_quotes_a_name_with_a_semicolon(fake):
    await call("i3_workspace", action="move_to_output", output="OUT-1; nop injected")
    assert fake.last_command == 'move workspace to output "OUT-1; nop injected"'


async def test_bulk_move_quotes_the_output(fake):
    fake.query_replies[ipc.GET_WORKSPACES] = [{"name": "1", "output": "OUT-2"}]
    await call("i3_workspace", action="bulk_move", names=["1"], output="Some Output")
    assert fake.last_command == 'workspace "1"; move workspace to output "Some Output"'
