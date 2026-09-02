import json

from i3mcp.criteria import WindowCriteria
from i3mcp.tools.layout import i3_layout


async def test_layout_tabbed(fake):
    await i3_layout(layout="tabbed")
    assert fake.last_command == "layout tabbed"


async def test_layout_toggle_split(fake):
    await i3_layout(layout="toggle split")
    assert fake.last_command == "layout toggle split"


async def test_split_horizontal(fake):
    await i3_layout(split="horizontal")
    assert fake.last_command == "split horizontal"


async def test_split_toggle(fake):
    await i3_layout(split="toggle")
    assert fake.last_command == "split toggle"


async def test_layout_with_criteria(fake):
    await i3_layout(criteria=WindowCriteria(con_id=3), layout="stacking")
    assert fake.last_command == "[con_id=3] layout stacking"


async def test_layout_requires_an_argument(fake):
    result = json.loads(await i3_layout())
    assert result["success"] is False
    assert fake.commands == []
