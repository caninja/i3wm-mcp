import json

from tests.conftest import call


async def test_mark_replace_is_default(fake):
    await call("i3_mark", mark="term")
    assert fake.last_command == 'mark --replace "term"'


async def test_mark_add(fake):
    await call("i3_mark", mark="important", mode="add")
    assert fake.last_command == 'mark --add "important"'


async def test_mark_toggle(fake):
    await call("i3_mark", mark="pinned", mode="toggle")
    assert fake.last_command == 'mark --toggle "pinned"'


async def test_mark_with_criteria(fake):
    result = json.loads(await call("i3_mark", criteria={"window_class": "Alpha"}, mark="browser"))
    assert fake.last_command == r'[class="^\QAlpha\E$"] mark --replace "browser"'
    assert result["targets"] == [{"con_id": 1001, "name": "alpha one", "window_class": "Alpha"}]


async def test_unmark_specific(fake):
    await call("i3_mark", unmark="term")
    assert fake.last_command == 'unmark "term"'


async def test_unmark_all(fake):
    await call("i3_mark", unmark_all=True)
    assert fake.last_command == "unmark"


async def test_mark_escapes_quotes(fake):
    await call("i3_mark", mark='say "hi"')
    assert fake.last_command == r'mark --replace "say \"hi\""'


async def test_mark_requires_an_argument(fake):
    result = json.loads(await call("i3_mark"))
    assert result["success"] is False
    assert fake.commands == []
