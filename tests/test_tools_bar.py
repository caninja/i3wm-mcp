import json

from i3mcp.tools.bar import i3_bar


async def test_bar_mode(fake):
    await i3_bar(mode="hide")
    assert fake.last_command == "bar mode hide"


async def test_bar_mode_with_id(fake):
    await i3_bar(mode="dock", bar_id="bar-0")
    assert fake.last_command == "bar mode dock bar-0"


async def test_bar_hidden_state(fake):
    await i3_bar(hidden_state="show")
    assert fake.last_command == "bar hidden_state show"


async def test_bar_requires_an_argument(fake):
    result = json.loads(await i3_bar())
    assert result["success"] is False
    assert fake.commands == []
