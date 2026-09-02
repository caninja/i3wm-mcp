import json

from i3mcp.tools.wm import i3_wm


async def test_exec_uses_no_startup_id(fake):
    await i3_wm(action="exec", command="firefox")
    assert fake.last_command == "exec --no-startup-id firefox"


async def test_exec_on_a_workspace_switches_first(fake):
    await i3_wm(action="exec", command="firefox", workspace="web")
    assert fake.last_command == 'workspace "web"; exec --no-startup-id firefox'


async def test_reload(fake):
    await i3_wm(action="reload")
    assert fake.last_command == "reload"


async def test_restart(fake):
    await i3_wm(action="restart")
    assert fake.last_command == "restart"


async def test_mode(fake):
    await i3_wm(action="mode", mode_name="resize")
    assert fake.last_command == 'mode "resize"'


async def test_nop(fake):
    await i3_wm(action="nop", comment="marker")
    assert fake.last_command == "nop marker"


async def test_shmlog_on(fake):
    await i3_wm(action="shmlog", toggle="on")
    assert fake.last_command == "shmlog on"


async def test_debuglog_off(fake):
    await i3_wm(action="debuglog", toggle="off")
    assert fake.last_command == "debuglog off"


async def test_append_layout(fake):
    await i3_wm(action="append_layout", path="/home/u/layout.json")
    assert fake.last_command == 'append_layout "/home/u/layout.json"'


async def test_exec_requires_a_command(fake):
    result = json.loads(await i3_wm(action="exec"))
    assert result["success"] is False
    assert fake.commands == []


async def test_mode_requires_a_name(fake):
    result = json.loads(await i3_wm(action="mode"))
    assert result["success"] is False
    assert fake.commands == []


async def test_exit_is_not_an_allowed_action(fake):
    """Terminating the session must not be reachable through a tool call."""
    import inspect

    from i3mcp.tools import wm

    assert "exit" not in str(inspect.signature(wm.i3_wm))
