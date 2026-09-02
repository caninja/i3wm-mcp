import json

from tests.conftest import call


async def test_move_direction_default_amount(fake):
    await call("i3_move", direction="left")
    assert fake.last_command == "move left"


async def test_move_direction_with_px(fake):
    await call("i3_move", direction="right", amount=30)
    assert fake.last_command == "move right 30 px"


async def test_move_direction_with_ppt(fake):
    await call("i3_move", direction="up", amount=10, unit="ppt")
    assert fake.last_command == "move up 10 ppt"


async def test_move_to_workspace_by_name(fake):
    await call("i3_move", workspace="web")
    assert fake.last_command == 'move container to workspace "web"'


async def test_move_to_workspace_by_number(fake):
    await call("i3_move", workspace="3", by_number=True)
    assert fake.last_command == 'move container to workspace number "3"'


async def test_move_to_relative_workspace(fake):
    await call("i3_move", workspace="next")
    assert fake.last_command == "move container to workspace next"


async def test_move_to_back_and_forth_workspace(fake):
    await call("i3_move", workspace="back_and_forth")
    assert fake.last_command == "move container to workspace back_and_forth"


async def test_move_and_follow_emits_two_commands(fake):
    await call("i3_move", workspace="web", follow=True)
    assert fake.last_command == 'move container to workspace "web"; workspace "web"'


async def test_move_to_output(fake):
    await call("i3_move", output="HDMI-1")
    assert fake.last_command == 'move container to output "HDMI-1"'


async def test_move_workspace_to_output(fake):
    await call("i3_move", output="HDMI-1", move_workspace=True)
    assert fake.last_command == 'move workspace to output "HDMI-1"'


async def test_move_position(fake):
    await call("i3_move", position_x=100, position_y=200)
    assert fake.last_command == "move position 100 px 200 px"


async def test_move_absolute_position(fake):
    await call("i3_move", position_x=100, position_y=200, absolute=True)
    assert fake.last_command == "move absolute position 100 px 200 px"


async def test_move_center(fake):
    await call("i3_move", center=True)
    assert fake.last_command == "move position center"


async def test_move_center_absolute(fake):
    await call("i3_move", center=True, absolute=True)
    assert fake.last_command == "move absolute position center"


async def test_move_to_mouse(fake):
    await call("i3_move", to_mouse=True)
    assert fake.last_command == "move position mouse"


async def test_move_to_mark(fake):
    await call("i3_move", to_mark="anchor")
    assert fake.last_command == 'move container to mark "anchor"'


async def test_move_to_scratchpad(fake):
    await call("i3_move", to_scratchpad=True)
    assert fake.last_command == "move scratchpad"


async def test_move_with_criteria_prefixes(fake):
    result = json.loads(await call("i3_move", criteria={"con_id": 1002}, workspace="web"))
    assert fake.last_command == '[con_id=1002] move container to workspace "web"'
    assert result["targets"] == [{"con_id": 1002, "name": "beta two", "window_class": "Beta"}]


async def test_swap_with_mark(fake):
    await call("i3_move", swap_with_mark="other")
    assert fake.last_command == 'swap container with mark "other"'


async def test_swap_with_con_id(fake):
    await call("i3_move", swap_with_con_id=99)
    assert fake.last_command == "swap container with con_id 99"


async def test_move_requires_a_destination(fake):
    result = json.loads(await call("i3_move"))
    assert result["success"] is False
    assert fake.commands == []


async def test_move_rejects_two_destinations(fake):
    result = json.loads(await call("i3_move", workspace="web", center=True))
    assert result["success"] is False
    assert fake.commands == []


async def test_move_rejects_half_a_position(fake):
    result = json.loads(await call("i3_move", position_x=100))
    assert result["success"] is False
    assert fake.commands == []


async def test_move_to_output_quotes_a_name_with_a_semicolon(fake):
    """An unquoted output name would end the command and inject a second one."""
    await call("i3_move", output="OUT-1; nop injected")
    assert fake.last_command == 'move container to output "OUT-1; nop injected"'


async def test_move_to_output_quotes_a_relative_keyword(fake):
    # Verified live on i3 4.25.1: quoted keywords resolve exactly as bare ones.
    await call("i3_move", output="right")
    assert fake.last_command == 'move container to output "right"'


async def test_move_by_number_and_follow_quotes_both_halves(fake):
    await call("i3_move", workspace="3", by_number=True, follow=True)
    assert fake.last_command == (
        'move container to workspace number "3"; workspace number "3"'
    )


async def test_move_by_number_quotes_a_value_with_a_semicolon(fake):
    """by_number takes a free-form string; unquoted it would inject a command."""
    await call("i3_move", workspace="3; nop injected", by_number=True)
    assert fake.last_command == 'move container to workspace number "3; nop injected"'


async def test_move_by_number_quotes_a_named_workspace(fake):
    # Verified live on i3 4.25.1: `workspace number "3: web"` parses.
    await call("i3_move", workspace="3: web", by_number=True)
    assert fake.last_command == 'move container to workspace number "3: web"'
