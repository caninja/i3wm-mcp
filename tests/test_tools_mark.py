import json

from i3mcp.criteria import WindowCriteria
from i3mcp.tools.mark import i3_mark


async def test_mark_replace_is_default(fake):
    await i3_mark(mark="term")
    assert fake.last_command == 'mark --replace "term"'


async def test_mark_add(fake):
    await i3_mark(mark="important", mode="add")
    assert fake.last_command == 'mark --add "important"'


async def test_mark_toggle(fake):
    await i3_mark(mark="pinned", mode="toggle")
    assert fake.last_command == 'mark --toggle "pinned"'


async def test_mark_with_criteria(fake):
    await i3_mark(criteria=WindowCriteria(window_class="firefox"), mark="browser")
    assert fake.last_command == r'[class="^\Qfirefox\E$"] mark --replace "browser"'


async def test_unmark_specific(fake):
    await i3_mark(unmark="term")
    assert fake.last_command == 'unmark "term"'


async def test_unmark_all(fake):
    await i3_mark(unmark_all=True)
    assert fake.last_command == "unmark"


async def test_mark_escapes_quotes(fake):
    await i3_mark(mark='say "hi"')
    assert fake.last_command == r'mark --replace "say \"hi\""'


async def test_mark_requires_an_argument(fake):
    result = json.loads(await i3_mark())
    assert result["success"] is False
    assert fake.commands == []
