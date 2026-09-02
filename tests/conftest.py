import pytest

import i3mcp.tools  # noqa: F401  (registers every tool)
from i3mcp import ipc
from i3mcp.server import mcp


async def call(name: str, /, **arguments) -> str:
    """Invoke a tool the way an MCP client does and return its text payload."""
    result = await mcp.call_tool(name, arguments)
    return result.content[0].text


class FakeTransport:
    """Stands in for I3Connection. Records commands, returns canned replies."""

    def __init__(self):
        self.commands: list[str] = []
        self.command_replies: list[list[dict]] = []
        self.query_replies: dict[int, object] = {}

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
