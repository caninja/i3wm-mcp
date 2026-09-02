import json

from tests.conftest import call


async def test_bar_mode(fake):
    await call("i3_bar", mode="hide")
    assert fake.last_command == "bar mode hide"


async def test_bar_mode_with_id(fake):
    await call("i3_bar", mode="dock", bar_id="bar-0")
    assert fake.last_command == 'bar mode dock "bar-0"'


async def test_bar_hidden_state(fake):
    await call("i3_bar", hidden_state="show")
    assert fake.last_command == "bar hidden_state show"


async def test_bar_requires_an_argument(fake):
    result = json.loads(await call("i3_bar"))
    assert result["success"] is False
    assert fake.commands == []


async def test_bar_hidden_state_with_id(fake):
    # Verified live on i3 4.25.1: `bar hidden_state show "bar-0"` parses.
    await call("i3_bar", hidden_state="show", bar_id="bar-0")
    assert fake.last_command == 'bar hidden_state show "bar-0"'


async def test_bar_id_with_a_semicolon_is_quoted(fake):
    await call("i3_bar", mode="hide", bar_id="bar-0; nop injected")
    assert fake.last_command == 'bar mode hide "bar-0; nop injected"'
