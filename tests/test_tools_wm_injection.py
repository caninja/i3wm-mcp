"""Injection tests for i3_wm's exec action.

Each payload would run an extra command if the shell expanded it. The
assertions describe the safe emission: the payload must reach i3 with `$`,
backticks and quotes neutralised. Against the original pipeline (plain
`escape_value`) these tests fail -- that failure is the vulnerability they
were written to catch. Against the fixed pipeline they pass.
"""

import json

from tests.conftest import call


async def test_command_substitution_is_escaped(fake):
    await call("i3_wm", action="exec", command="echo pwned $(touch /tmp/pwned)")
    assert fake.last_command == 'exec --no-startup-id "echo pwned \\$(touch /tmp/pwned)"'


async def test_backtick_substitution_is_escaped(fake):
    await call("i3_wm", action="exec", command="xterm `touch /tmp/pwned`")
    assert fake.last_command == 'exec --no-startup-id "xterm \\`touch /tmp/pwned\\`"'


async def test_variable_expansion_is_escaped(fake):
    await call("i3_wm", action="exec", command="notify-send $HOME")
    assert fake.last_command == 'exec --no-startup-id "notify-send \\$HOME"'


async def test_control_characters_are_refused(fake):
    result = json.loads(await call("i3_wm", action="exec", command="xterm\nkill"))
    assert result["success"] is False
    assert "control characters" in result["error"].lower()
    assert fake.commands == []


async def test_quotes_stay_inside_the_exec_argument(fake):
    await call("i3_wm", action="exec", command='xterm -T "probe"')
    assert fake.last_command == 'exec --no-startup-id "xterm -T \\"probe\\""'


async def test_workspace_prefix_is_unchanged(fake):
    await call("i3_wm", action="exec", command="firefox", workspace="web")
    assert fake.last_command == 'workspace "web"; exec --no-startup-id "firefox"'
