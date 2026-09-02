import json

from tests.conftest import call


async def test_resize_grow_width_px(fake):
    await call("i3_resize", mode="grow", direction="right", amount=50)
    assert fake.last_command == "resize grow right 50 px"


async def test_resize_shrink_ppt(fake):
    # i3 4.25.1 rejects a bare ppt amount for resize grow/shrink -- verified
    # live: "Expected one of these tokens: 'px', 'or', <end>". ppt is only
    # valid there as a fallback "or" clause after a px amount.
    await call("i3_resize", mode="shrink", direction="up", amount=5, unit="ppt")
    assert fake.last_command == "resize shrink up 5 px or 5 ppt"


async def test_resize_grow_width(fake):
    await call("i3_resize", mode="grow", direction="width", amount=10)
    assert fake.last_command == "resize grow width 10 px"


async def test_resize_grow_width_ppt(fake):
    await call("i3_resize", mode="grow", direction="width", amount=10, unit="ppt")
    assert fake.last_command == "resize grow width 10 px or 10 ppt"


async def test_resize_set_both_dimensions_px(fake):
    await call("i3_resize", mode="set", width=800, height=600)
    assert fake.last_command == "resize set width 800 px height 600 px"


async def test_resize_set_width_only_ppt(fake):
    await call("i3_resize", mode="set", width=60, unit="ppt")
    assert fake.last_command == "resize set width 60 ppt"


async def test_resize_set_does_not_force_floating(fake):
    await call("i3_resize", mode="set", width=800, height=600)
    assert "floating enable" not in fake.last_command


async def test_resize_with_criteria(fake):
    result = json.loads(
        await call("i3_resize", criteria={"con_mark": "m1"}, mode="grow", direction="right", amount=10)
    )
    assert fake.last_command == r'[con_mark="^\Qm1\E$"] resize grow right 10 px'
    assert result["targets"] == [{"con_id": 1001, "name": "alpha one", "window_class": "Alpha"}]


async def test_resize_grow_requires_direction(fake):
    result = json.loads(await call("i3_resize", mode="grow", amount=10))
    assert result["success"] is False
    assert fake.commands == []


async def test_resize_set_requires_a_dimension(fake):
    result = json.loads(await call("i3_resize", mode="set"))
    assert result["success"] is False
    assert fake.commands == []
