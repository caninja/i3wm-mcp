"""Assemble i3 commands from user input without letting it become code.

i3's exec action launches a shell command. The value sits inside double
quotes, where a shell still expands `$var`, `$(...)` and backticks, so
escaping only a backslash and a double quote -- what `criteria.escape_value`
does for i3's own syntax -- leaves a command-injection path open.
`escape_shell` closes it.
"""

from __future__ import annotations

import re

from .criteria import escape_value

MAX_COMMAND_LENGTH = 500

# C0 controls and DEL. A newline would split the i3 command; the rest have no
# legitimate place in a launched command line.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def escape_shell(value: str) -> str:
    """Make a value literal inside the double-quoted exec argument.

    Backslash, double quote, dollar and backtick are the characters a shell
    still treats specially inside double quotes. Escaping them keeps
    command substitution and variable expansion inert. Raises ValueError for
    control characters rather than trying to encode them.
    """
    if _CONTROL_CHARS.search(value):
        raise ValueError("Command contains control characters; refusing to run it.")
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )


def exec_command(command: str, workspace: str | None = None) -> str:
    """Build `exec --no-startup-id "<command>"`, switching workspace first if asked."""
    if len(command) > MAX_COMMAND_LENGTH:
        raise ValueError(f"Command is longer than {MAX_COMMAND_LENGTH} characters.")
    cmd = f'exec --no-startup-id "{escape_shell(command)}"'
    if workspace:
        cmd = f'workspace "{escape_value(workspace)}"; {cmd}'
    return cmd
