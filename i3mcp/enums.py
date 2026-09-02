"""Shared argument vocabularies, plus the workspace keywords i3 treats specially.

The value sets are `Literal` aliases rather than `Enum` classes: pydantic inlines
a Literal as a plain `enum` list, where an Enum class becomes a `$defs` entry plus
a `$ref` in every schema that mentions it. The values are the strings i3 itself
accepts, so they need no `.value` unwrapping at the call site. `ResponseFormat` is
the one holdout, and goes away with `i3_query(response_format=...)`.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

Direction = Literal["left", "right", "up", "down"]

MatchMode = Literal["exact", "substring", "regex"]

Urgency = Literal["latest", "oldest", "newest", "last", "recent", "first"]

WindowType = Literal[
    "normal",
    "dialog",
    "utility",
    "toolbar",
    "splash",
    "menu",
    "dropdown_menu",
    "popup_menu",
    "tooltip",
    "notification",
]

Unit = Literal["px", "ppt"]

# Shared by move.py and workspace.py: names i3 treats as bare keywords rather
# than quoted workspace names. move.py also accepts "current", which is only
# valid for "move container to workspace current", not "workspace current".
WORKSPACE_KEYWORDS = frozenset(
    {"next", "prev", "next_on_output", "prev_on_output", "back_and_forth"}
)


class ResponseFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"
