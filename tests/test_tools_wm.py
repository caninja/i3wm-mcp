import json

from tests.conftest import call


async def test_exec_uses_no_startup_id(fake):
    await call("i3_wm", action="exec", command="firefox")
    assert fake.last_command == 'exec --no-startup-id "firefox"'


async def test_exec_on_a_workspace_switches_first(fake):
    await call("i3_wm", action="exec", command="firefox", workspace="web")
    assert fake.last_command == 'workspace "web"; exec --no-startup-id "firefox"'


async def test_exec_quotes_a_command_with_semicolons(fake):
    await call("i3_wm", action="exec", command='sh -c "echo a; echo b"')
    assert fake.last_command == 'exec --no-startup-id "sh -c \\"echo a; echo b\\""'


async def test_exec_quotes_a_command_with_a_comma(fake):
    await call("i3_wm", action="exec", command="true, true")
    assert fake.last_command == 'exec --no-startup-id "true, true"'


async def test_reload(fake):
    await call("i3_wm", action="reload")
    assert fake.last_command == "reload"


async def test_restart(fake):
    await call("i3_wm", action="restart")
    assert fake.last_command == "restart"


async def test_mode(fake):
    await call("i3_wm", action="mode", mode_name="resize")
    assert fake.last_command == 'mode "resize"'


async def test_nop(fake):
    await call("i3_wm", action="nop", comment="marker")
    assert fake.last_command == "nop marker"


async def test_shmlog_on(fake):
    await call("i3_wm", action="shmlog", toggle="on")
    assert fake.last_command == "shmlog on"


async def test_debuglog_off(fake):
    await call("i3_wm", action="debuglog", toggle="off")
    assert fake.last_command == "debuglog off"


async def test_debuglog_toggle(fake):
    await call("i3_wm", action="debuglog", toggle="toggle")
    assert fake.last_command == "debuglog toggle"


async def test_append_layout(fake):
    await call("i3_wm", action="append_layout", path="/home/u/layout.json")
    assert fake.last_command == 'append_layout "/home/u/layout.json"'


async def test_exec_requires_a_command(fake):
    result = json.loads(await call("i3_wm", action="exec"))
    assert result["success"] is False
    assert fake.commands == []


async def test_mode_requires_a_name(fake):
    result = json.loads(await call("i3_wm", action="mode"))
    assert result["success"] is False
    assert fake.commands == []


async def test_exit_is_not_an_allowed_action(fake):
    """Terminating the session must not be reachable through a tool call."""
    import inspect

    from i3mcp.tools import wm

    assert "exit" not in str(inspect.signature(wm.i3_wm))
