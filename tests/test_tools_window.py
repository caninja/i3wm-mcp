import json

from tests.conftest import call


async def test_kill_focused(fake):
    await call("i3_kill")
    assert fake.last_command == "kill"


async def test_kill_by_criteria(fake):
    await call("i3_kill", criteria={"con_id": 7})
    assert fake.last_command == "[con_id=7] kill"


async def test_floating_enable(fake):
    await call("i3_window", floating="enable")
    assert fake.last_command == "floating enable"


async def test_floating_toggle_with_criteria(fake):
    await call("i3_window", criteria={"window_class": "Thunar"}, floating="toggle")
    assert fake.last_command == r'[class="^\QThunar\E$"] floating toggle'


async def test_sticky(fake):
    await call("i3_window", sticky="enable")
    assert fake.last_command == "sticky enable"


async def test_fullscreen_toggle(fake):
    await call("i3_window", fullscreen="toggle")
    assert fake.last_command == "fullscreen toggle"


async def test_fullscreen_global(fake):
    await call("i3_window", fullscreen="enable", fullscreen_global=True)
    assert fake.last_command == "fullscreen enable global"


async def test_border_pixel_with_width(fake):
    await call("i3_window", border="pixel", border_width=3)
    assert fake.last_command == "border pixel 3"


async def test_border_none_ignores_width(fake):
    await call("i3_window", border="none", border_width=3)
    assert fake.last_command == "border none"


async def test_border_toggle(fake):
    await call("i3_window", border="toggle")
    assert fake.last_command == "border toggle"


async def test_title_format(fake):
    await call("i3_window", title_format="%title (%class)")
    assert fake.last_command == 'title_format "%title (%class)"'


async def test_title_window_icon_on(fake):
    await call("i3_window", title_window_icon="on")
    assert fake.last_command == "title_window_icon on"


async def test_title_window_icon_with_padding(fake):
    await call("i3_window", title_window_icon="on", title_window_icon_padding=2)
    assert fake.last_command == "title_window_icon on padding 2 px"


async def test_multiple_properties_chain_with_commas(fake):
    await call("i3_window", floating="enable", sticky="enable")
    assert fake.last_command == "floating enable, sticky enable"


async def test_criteria_applies_once_to_a_chain(fake):
    await call("i3_window", criteria={"con_id": 5}, floating="enable", sticky="enable")
    assert fake.last_command == "[con_id=5] floating enable, sticky enable"


async def test_window_requires_a_property(fake):
    result = json.loads(await call("i3_window"))
    assert result["success"] is False
    assert fake.commands == []
