import pytest

import i3mcp.tools  # noqa: F401  (registers every tool)
from i3mcp import ipc
from i3mcp.server import mcp


async def call(name: str, /, **arguments) -> str:
    """Invoke a tool the way an MCP client does and return its text payload."""
    result = await mcp.call_tool(name, arguments)
    return result.content[0].text


def _window(con_id: int, window_id: int, name: str, cls: str, **extra) -> dict:
    node = {
        "type": "con",
        "id": con_id,
        "window": window_id,
        "name": name,
        "floating": "auto_off",
        "focused": False,
        "urgent": False,
        "fullscreen_mode": 0,
        "marks": [],
        "layout": "splith",
        "rect": {"x": 0, "y": 0, "width": 800, "height": 600},
        "window_type": "normal",
        "window_properties": {"class": cls, "instance": cls.lower(), "window_role": "main"},
        "nodes": [],
        "floating_nodes": [],
    }
    node.update(extra)
    return node


def fixture_tree() -> dict:
    """Default tree behind GET_TREE: Alpha focused, Beta floating beside it, Gamma elsewhere."""
    alpha = _window(1001, 2001, "alpha one", "Alpha", focused=True, marks=["m1"])
    beta = _window(1002, 2002, "beta two", "Beta", floating="user_on")
    gamma = _window(1003, 2003, "gamma three", "Gamma", urgent=True)
    return {
        "type": "root",
        "name": "root",
        "nodes": [
            {
                "type": "output",
                "name": "OUT-1",
                "nodes": [
                    {
                        "type": "con",
                        "name": "content",
                        "nodes": [
                            {
                                "type": "workspace",
                                "name": "1",
                                "num": 1,
                                "output": "OUT-1",
                                "layout": "splith",
                                "nodes": [alpha],
                                "floating_nodes": [
                                    {
                                        "type": "floating_con",
                                        "id": 1102,
                                        "nodes": [beta],
                                        "floating_nodes": [],
                                    }
                                ],
                            },
                            {
                                "type": "workspace",
                                "name": "2",
                                "num": 2,
                                "output": "OUT-1",
                                "layout": "splith",
                                "nodes": [gamma],
                                "floating_nodes": [],
                            },
                        ],
                        "floating_nodes": [],
                    }
                ],
                "floating_nodes": [],
            }
        ],
        "floating_nodes": [],
    }


class FakeTransport:
    """Stands in for I3Connection. Records commands, returns canned replies."""

    def __init__(self):
        self.commands: list[str] = []
        self.command_replies: list[list[dict]] = []
        self.query_replies: dict[int, object] = {ipc.GET_TREE: fixture_tree()}

    def command(self, cmd: str) -> list[dict]:
        self.commands.append(cmd)
        if self.command_replies:
            reply = self.command_replies.pop(0)
        else:
            reply = [{"success": True}]
        failed = [r for r in reply if not r.get("success")]
        if failed:
            raise ipc.I3Error(failed[0].get("error", "command failed"), replies=reply)
        return reply

    def query(self, msg_type: int, payload: str = ""):
        return self.query_replies[msg_type]

    @property
    def last_command(self) -> str:
        return self.commands[-1]


@pytest.fixture
def fake(monkeypatch):
    transport = FakeTransport()
    ipc.set_connection(transport)
    yield transport
    ipc.set_connection(None)
