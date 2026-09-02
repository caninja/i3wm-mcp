"""Window criteria shared by every mutating tool.

i3 matches criteria values as PCRE. Verified on i3 4.25.1: \\Q...\\E literal
quoting works, and \\" escapes correctly inside a quoted criteria value.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import MatchMode, Urgency, WindowType


def escape_value(value: str) -> str:
    """Escape a value for inclusion in a double-quoted i3 criteria string."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def pattern_for(value: str, mode: MatchMode) -> str:
    """Build the PCRE i3 should match against."""
    if mode == MatchMode.REGEX:
        return value
    quoted = f"\\Q{value}\\E"
    if mode == MatchMode.SUBSTRING:
        return quoted
    return f"^{quoted}$"


class WindowCriteria(BaseModel):
    """Selects which window(s) a command applies to.

    Leave every field unset to act on the currently focused window.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    window_class: str | None = Field(
        default=None,
        description="X11 window class, the second part of WM_CLASS (e.g. 'firefox').",
    )
    instance: str | None = Field(
        default=None,
        description="X11 window instance, the first part of WM_CLASS (e.g. 'Navigator').",
    )
    title: str | None = Field(default=None, description="Window title.")
    window_role: str | None = Field(default=None, description="WM_WINDOW_ROLE value.")
    window_type: WindowType | None = Field(default=None, description="Window type.")
    machine: str | None = Field(default=None, description="WM_CLIENT_MACHINE hostname.")
    con_mark: str | None = Field(default=None, description="i3 mark set on the container.")
    workspace: str | None = Field(default=None, description="Name of the containing workspace.")
    con_id: int | None = Field(
        default=None,
        description="i3 container id, from i3_query. The most precise selector.",
    )
    window_id: int | None = Field(default=None, description="X11 window id.")
    urgent: Urgency | None = Field(
        default=None,
        description="Match urgent windows. i3 accepts latest/oldest/newest/last/recent/first, never 'yes'.",
    )
    floating: bool = Field(default=False, description="Match only floating windows.")
    tiling: bool = Field(default=False, description="Match only tiling windows.")
    all: bool = Field(default=False, description="Match every window.")
    match: MatchMode = Field(
        default=MatchMode.EXACT,
        description="How string values match: exact (default), substring, or regex.",
    )

    def is_empty(self) -> bool:
        return not self.to_selector()

    def to_selector(self) -> str:
        """Render as an i3 criteria selector, or '' when nothing is set."""
        parts: list[str] = []
        string_fields = [
            ("class", self.window_class),
            ("instance", self.instance),
            ("title", self.title),
            ("window_role", self.window_role),
            ("machine", self.machine),
            ("con_mark", self.con_mark),
            ("workspace", self.workspace),
        ]
        for key, value in string_fields:
            if value is not None:
                pattern = pattern_for(escape_value(value), self.match)
                parts.append(f'{key}="{pattern}"')
        if self.window_type is not None:
            parts.append(f'window_type="{self.window_type.value}"')
        if self.con_id is not None:
            parts.append(f"con_id={self.con_id}")
        if self.window_id is not None:
            parts.append(f"id={self.window_id}")
        if self.urgent is not None:
            parts.append(f"urgent={self.urgent.value}")
        if self.floating:
            parts.append("floating")
        if self.tiling:
            parts.append("tiling")
        if self.all:
            parts.append("all")
        if not parts:
            return ""
        return "[" + " ".join(parts) + "]"


def prefix_command(criteria: WindowCriteria | None, command: str) -> str:
    """Prefix a command with a criteria selector, if there is one."""
    selector = criteria.to_selector() if criteria is not None else ""
    return f"{selector} {command}" if selector else command
