import json

from i3mcp.criteria import WindowCriteria
from i3mcp.tools.move import i3_move


async def test_move_direction_default_amount(fake):
    await i3_move(direction="left")
    assert fake.last_command == "move left"


async def test_move_direction_with_px(fake):
    await i3_move(direction="right", amount=30)
    assert fake.last_command == "move right 30 px"


async def test_move_direction_with_ppt(fake):
    await i3_move(direction="up", amount=10, unit="ppt")
    assert fake.last_command == "move up 10 ppt"


async def test_move_to_workspace_by_name(fake):
    await i3_move(workspace="web")
    assert fake.last_command == 'move container to workspace "web"'


async def test_move_to_workspace_by_number(fake):
    await i3_move(workspace="3", by_number=True)
    assert fake.last_command == "move container to workspace number 3"


async def test_move_to_relative_workspace(fake):
    await i3_move(workspace="next")
    assert fake.last_command == "move container to workspace next"


async def test_move_and_follow_emits_two_commands(fake):
    await i3_move(workspace="web", follow=True)
    assert fake.last_command == 'move container to workspace "web"; workspace "web"'


async def test_move_to_output(fake):
    await i3_move(output="HDMI-1")
    assert fake.last_command == "move container to output HDMI-1"


async def test_move_workspace_to_output(fake):
    await i3_move(output="HDMI-1", move_workspace=True)
    assert fake.last_command == "move workspace to output HDMI-1"


async def test_move_absolute_position(fake):
    await i3_move(position_x=100, position_y=200)
    assert fake.last_command == "move absolute position 100 px 200 px"


async def test_move_center(fake):
    await i3_move(center=True)
    assert fake.last_command == "move absolute position center"


async def test_move_to_mouse(fake):
    await i3_move(to_mouse=True)
    assert fake.last_command == "move position mouse"


async def test_move_to_mark(fake):
    await i3_move(to_mark="anchor")
    assert fake.last_command == 'move container to mark "anchor"'


async def test_move_to_scratchpad(fake):
    await i3_move(to_scratchpad=True)
    assert fake.last_command == "move scratchpad"


async def test_move_with_criteria_prefixes(fake):
    await i3_move(criteria=WindowCriteria(con_id=42), workspace="web")
    assert fake.last_command == '[con_id=42] move container to workspace "web"'


async def test_swap_with_mark(fake):
    await i3_move(swap_with_mark="other")
    assert fake.last_command == 'swap container with mark "other"'


async def test_swap_with_con_id(fake):
    await i3_move(swap_with_con_id=99)
    assert fake.last_command == "swap container with con_id 99"


async def test_move_requires_a_destination(fake):
    result = json.loads(await i3_move())
    assert result["success"] is False
    assert fake.commands == []


async def test_move_rejects_two_destinations(fake):
    result = json.loads(await i3_move(workspace="web", center=True))
    assert result["success"] is False
    assert fake.commands == []


async def test_move_rejects_half_a_position(fake):
    result = json.loads(await i3_move(position_x=100))
    assert result["success"] is False
    assert fake.commands == []
