import json

from tests.conftest import call


async def test_layout_tabbed(fake):
    await call("i3_layout", layout="tabbed")
    assert fake.last_command == "layout tabbed"


async def test_layout_toggle_split(fake):
    await call("i3_layout", layout="toggle split")
    assert fake.last_command == "layout toggle split"


async def test_split_horizontal(fake):
    await call("i3_layout", split="horizontal")
    assert fake.last_command == "split horizontal"


async def test_split_toggle(fake):
    await call("i3_layout", split="toggle")
    assert fake.last_command == "split toggle"


async def test_layout_with_criteria(fake):
    result = json.loads(await call("i3_layout", criteria={"con_id": 1003}, layout="stacking"))
    assert fake.last_command == "[con_id=1003] layout stacking"
    assert result["targets"] == [{"con_id": 1003, "name": "gamma three", "window_class": "Gamma"}]


async def test_layout_requires_an_argument(fake):
    result = json.loads(await call("i3_layout"))
    assert result["success"] is False
    assert fake.commands == []
