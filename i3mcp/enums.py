"""Shared enumerations. All are (str, Enum) so pydantic renders them as strings."""

from __future__ import annotations

from enum import Enum


class Direction(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


class MatchMode(str, Enum):
    EXACT = "exact"
    SUBSTRING = "substring"
    REGEX = "regex"


class Urgency(str, Enum):
    LATEST = "latest"
    OLDEST = "oldest"
    NEWEST = "newest"
    LAST = "last"
    RECENT = "recent"
    FIRST = "first"


class WindowType(str, Enum):
    NORMAL = "normal"
    DIALOG = "dialog"
    UTILITY = "utility"
    TOOLBAR = "toolbar"
    SPLASH = "splash"
    MENU = "menu"
    DROPDOWN_MENU = "dropdown_menu"
    POPUP_MENU = "popup_menu"
    TOOLTIP = "tooltip"
    NOTIFICATION = "notification"


class Unit(str, Enum):
    PX = "px"
    PPT = "ppt"


class ResponseFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"
