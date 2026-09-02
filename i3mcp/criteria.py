"""Window criteria shared by every mutating tool.

i3 matches criteria values as PCRE. Verified on i3 4.25.1: \\Q...\\E literal
quoting works, and \\" escapes correctly inside a quoted criteria value.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import MatchMode, Urgency, WindowType


def escape_value(value: str) -> str:
    """Escape a value for inclusion in a double-quoted i3 criteria string."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def pattern_for(value: str, mode: MatchMode) -> str:
    """Build the PCRE i3 should match against."""
    if mode == "regex":
        return value
    quoted = f"\\Q{value}\\E"
    if mode == "substring":
        return quoted
    return f"^{quoted}$"


def compile_pattern(pattern: str, field: str) -> re.Pattern:
    """Compile a criteria regex, naming the field it came from if it is invalid."""
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regex for criteria field '{field}': {exc}") from exc


def value_matches(pattern: str, value: Any, mode: MatchMode, field: str) -> bool:
    """Apply one criteria value to one record value, the way i3 would."""
    if value is None:
        return False
    text = str(value)
    if mode == "substring":
        return pattern in text
    if mode == "regex":
        return compile_pattern(pattern, field).search(text) is not None
    return pattern == text


class WindowCriteria(BaseModel):
    """Which window(s) to act on. Omit every field for the focused window."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    window_class: str | None = Field(
        default=None, description="WM_CLASS class, e.g. 'firefox'."
    )
    instance: str | None = Field(default=None, description="WM_CLASS instance.")
    title: str | None = Field(default=None, description="Window title.")
    window_role: str | None = Field(default=None, description="WM_WINDOW_ROLE value.")
    window_type: WindowType | None = Field(default=None, description="Window type.")
    con_mark: str | None = Field(default=None, description="i3 mark on the container.")
    workspace: str | None = Field(default=None, description="Containing workspace name.")
    con_id: int | None = Field(
        default=None, description="Container id from i3_query; the most precise selector."
    )
    window_id: int | None = Field(default=None, description="X11 window id.")
    urgent: Urgency | None = Field(
        default=None,
        description="Pick an urgent window: latest, oldest, newest, last, recent or first.",
    )
    floating: bool | None = Field(
        default=None, description="true: only floating windows; false: only tiling."
    )
    all: bool = Field(default=False, description="Match every window.")
    match: MatchMode = Field(
        default="exact", description="How strings match: exact (default), substring, regex."
    )

    def _string_fields(self) -> tuple[tuple[str, str | None], ...]:
        return (
            ("window_class", self.window_class),
            ("instance", self.instance),
            ("title", self.title),
            ("window_role", self.window_role),
            ("workspace", self.workspace),
            ("con_mark", self.con_mark),
        )

    def validate_patterns(self) -> None:
        """Reject an invalid regex up front, so the field is named whatever the tree holds."""
        if self.match != "regex":
            return
        for field, pattern in self._string_fields():
            if pattern is not None:
                compile_pattern(pattern, field)

    def matches(self, record: dict) -> bool:
        """Does a window record satisfy every field set here? Fields are ANDed."""
        self.validate_patterns()
        for field, pattern, value in (
            ("window_class", self.window_class, record.get("window_class")),
            ("instance", self.instance, record.get("instance")),
            ("title", self.title, record.get("name")),
            ("window_role", self.window_role, record.get("window_role")),
            ("workspace", self.workspace, record.get("workspace")),
        ):
            if pattern is not None and not value_matches(pattern, value, self.match, field):
                return False
        if self.con_mark is not None and not any(
            value_matches(self.con_mark, mark, self.match, "con_mark")
            for mark in record.get("marks") or []
        ):
            return False
        if self.window_type is not None and record.get("window_type") != self.window_type:
            return False
        if self.con_id is not None and record.get("con_id") != self.con_id:
            return False
        if self.window_id is not None and record.get("window_id") != self.window_id:
            return False
        if self.urgent is not None and not record.get("urgent", False):
            return False
        if self.floating is not None and record.get("floating", False) is not self.floating:
            return False
        # `all` puts no condition on a window, so it adds no clause here.
        return True

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
            ("con_mark", self.con_mark),
            ("workspace", self.workspace),
        ]
        for key, value in string_fields:
            if value is not None:
                pattern = pattern_for(escape_value(value), self.match)
                parts.append(f'{key}="{pattern}"')
        if self.window_type is not None:
            parts.append(f'window_type="{self.window_type}"')
        if self.con_id is not None:
            parts.append(f"con_id={self.con_id}")
        if self.window_id is not None:
            parts.append(f"id={self.window_id}")
        if self.urgent is not None:
            parts.append(f"urgent={self.urgent}")
        if self.floating is not None:
            parts.append("floating" if self.floating else "tiling")
        if self.all:
            parts.append("all")
        if not parts:
            return ""
        return "[" + " ".join(parts) + "]"


def prefix_command(criteria: WindowCriteria | None, command: str) -> str:
    """Prefix a command with a criteria selector, if there is one."""
    selector = criteria.to_selector() if criteria is not None else ""
    return f"{selector} {command}" if selector else command
