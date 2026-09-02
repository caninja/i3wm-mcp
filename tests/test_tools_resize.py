import json

from i3mcp.criteria import WindowCriteria
from i3mcp.tools.resize import i3_resize


async def test_resize_grow_width_px(fake):
    await i3_resize(mode="grow", direction="right", amount=50)
    assert fake.last_command == "resize grow right 50 px"


async def test_resize_shrink_ppt(fake):
    await i3_resize(mode="shrink", direction="up", amount=5, unit="ppt")
    assert fake.last_command == "resize shrink up 5 ppt"


async def test_resize_set_both_dimensions_px(fake):
    await i3_resize(mode="set", width=800, height=600)
    assert fake.last_command == "resize set width 800 px height 600 px"


async def test_resize_set_width_only_ppt(fake):
    await i3_resize(mode="set", width=60, unit="ppt")
    assert fake.last_command == "resize set width 60 ppt"


async def test_resize_set_does_not_force_floating(fake):
    await i3_resize(mode="set", width=800, height=600)
    assert "floating enable" not in fake.last_command


async def test_resize_with_criteria(fake):
    await i3_resize(criteria=WindowCriteria(con_mark="term"), mode="grow", direction="right", amount=10)
    assert fake.last_command == r'[con_mark="^\Qterm\E$"] resize grow right 10 px'


async def test_resize_grow_requires_direction(fake):
    result = json.loads(await i3_resize(mode="grow", amount=10))
    assert result["success"] is False
    assert fake.commands == []


async def test_resize_set_requires_a_dimension(fake):
    result = json.loads(await i3_resize(mode="set"))
    assert result["success"] is False
    assert fake.commands == []
