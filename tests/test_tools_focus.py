import json

from tests.conftest import call


async def test_focus_direction(fake):
    await call("i3_focus", direction="left")
    assert fake.last_command == "focus left"


async def test_focus_parent(fake):
    await call("i3_focus", target="parent")
    assert fake.last_command == "focus parent"


async def test_focus_floating_mode(fake):
    await call("i3_focus", target="floating")
    assert fake.last_command == "focus floating"


async def test_focus_next_sibling(fake):
    await call("i3_focus", sibling="next")
    assert fake.last_command == "focus next sibling"


async def test_focus_cycle_prev(fake):
    await call("i3_focus", cycle="prev")
    assert fake.last_command == "focus prev"


async def test_focus_output_by_name(fake):
    await call("i3_focus", output="HDMI-1")
    assert fake.last_command == "focus output HDMI-1"


async def test_focus_by_criteria(fake):
    await call("i3_focus", criteria={"window_class": "firefox"})
    assert fake.last_command == r'[class="^\Qfirefox\E$"] focus'


async def test_focus_workspace_of_matching_window(fake):
    await call("i3_focus", criteria={"con_mark": "term"}, focus_workspace=True)
    assert fake.last_command == r'[con_mark="^\Qterm\E$"] focus workspace'


async def test_focus_urgent_uses_i3_vocabulary(fake):
    await call("i3_focus", criteria={"urgent": "latest"})
    assert fake.last_command == "[urgent=latest] focus"


async def test_focus_requires_an_argument(fake):
    result = json.loads(await call("i3_focus"))
    assert result["success"] is False
    assert fake.commands == []


async def test_focus_rejects_conflicting_arguments(fake):
    result = json.loads(await call("i3_focus", direction="left", target="parent"))
    assert result["success"] is False
    assert fake.commands == []
