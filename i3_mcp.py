#!/usr/bin/env python3
"""
i3wm MCP Server

Model Context Protocol server for controlling i3 window manager.
Provides tools for window management, scratchpad control (including named scratchpads),
workspace management, layout control, and window tree querying.
"""

import json
import subprocess
from typing import Optional, List, Dict, Any, Literal
from enum import Enum

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator, ConfigDict

# Constants
CHARACTER_LIMIT = 25000

# Initialize FastMCP server
mcp = FastMCP("i3_mcp")


# ============================================================================
# Enums and Models
# ============================================================================

class Direction(str, Enum):
    """Direction for window movement and focus."""
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


class Layout(str, Enum):
    """Container layout types."""
    STACKING = "stacking"
    TABBED = "tabbed"
    SPLIT_H = "splith"
    SPLIT_V = "splitv"
    TOGGLE_SPLIT = "toggle split"


class SplitOrientation(str, Enum):
    """Split orientation."""
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    TOGGLE = "toggle"


class BorderStyle(str, Enum):
    """Window border styles."""
    NORMAL = "normal"
    PIXEL = "pixel"
    NONE = "none"
    TOGGLE = "toggle"


class FocusTarget(str, Enum):
    """Special focus targets."""
    FLOATING = "floating"
    TILING = "tiling"
    MODE_TOGGLE = "mode_toggle"


class WorkspaceNavigation(str, Enum):
    """Workspace navigation directions."""
    NEXT = "next"
    PREV = "prev"
    NEXT_ON_OUTPUT = "next_on_output"
    PREV_ON_OUTPUT = "prev_on_output"
    BACK_AND_FORTH = "back_and_forth"


class BarMode(str, Enum):
    """i3bar display modes."""
    DOCK = "dock"
    HIDE = "hide"
    INVISIBLE = "invisible"


class BarHiddenState(str, Enum):
    """i3bar hidden state."""
    HIDE = "hide"
    SHOW = "show"


class ResponseFormat(str, Enum):
    """Output format for responses."""
    JSON = "json"
    MARKDOWN = "markdown"


# ============================================================================
# Helper Functions
# ============================================================================

def run_i3_msg(command: str) -> Dict[str, Any]:
    """
    Execute an i3-msg command and return the result.
    
    Args:
        command: i3-msg command to execute
        
    Returns:
        Dictionary containing command output or error information
        
    Raises:
        subprocess.CalledProcessError: If command execution fails
    """
    try:
        result = subprocess.run(
            ["i3-msg", "-t", "command", command],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        # Parse JSON response
        output = json.loads(result.stdout)
        return {
            "success": True,
            "output": output,
            "command": command
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": e.stderr or str(e),
            "command": command
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Failed to parse i3-msg output: {str(e)}",
            "command": command,
            "raw_output": result.stdout
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command timed out after 5 seconds",
            "command": command
        }


def run_i3_msg_get_type(msg_type: str) -> Dict[str, Any]:
    """
    Execute an i3-msg get command (like get_tree, get_workspaces).
    
    Args:
        msg_type: Type of get command (e.g., 'tree', 'workspaces')
        
    Returns:
        Dictionary containing query results or error information
    """
    try:
        result = subprocess.run(
            ["i3-msg", "-t", f"get_{msg_type}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        output = json.loads(result.stdout)
        return {
            "success": True,
            "data": output
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": e.stderr or str(e)
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Failed to parse i3-msg output: {str(e)}",
            "raw_output": result.stdout
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Query timed out after 5 seconds"
        }


def find_windows_recursive(node: Dict[str, Any], criteria: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Recursively search the i3 tree for windows matching criteria.

    Args:
        node: Current node in the tree
        criteria: Optional dictionary with keys like 'class', 'title', 'instance', 'floating', 'urgent', etc.

    Returns:
        List of matching window nodes
    """
    windows = []

    # Check if current node is a window (has window property)
    if node.get("window") and node.get("window") != 0:
        # If no criteria, include all windows
        if not criteria:
            windows.append(node)
        else:
            # Check if window matches all criteria
            matches = True
            window_props = node.get("window_properties", {})

            for key, value in criteria.items():
                if key == "class":
                    if window_props.get("class", "").lower() != value.lower():
                        matches = False
                elif key == "title":
                    if value.lower() not in node.get("name", "").lower():
                        matches = False
                elif key == "instance":
                    if window_props.get("instance", "").lower() != value.lower():
                        matches = False
                elif key == "role":
                    if window_props.get("window_role", "").lower() != value.lower():
                        matches = False
                elif key == "type":
                    if node.get("window_type", "").lower() != value.lower():
                        matches = False
                elif key == "floating":
                    is_floating = node.get("type") == "floating_con"
                    if is_floating != value:
                        matches = False
                elif key == "urgent":
                    if node.get("urgent", False) != value:
                        matches = False
                elif key == "workspace":
                    # Get workspace name by traversing up the tree
                    # For now, we'll skip this complex check
                    pass

            if matches:
                windows.append(node)

    # Recursively search child nodes
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        windows.extend(find_windows_recursive(child, criteria))

    return windows


def format_window_info(window: Dict[str, Any], format_type: ResponseFormat) -> str:
    """
    Format window information in the specified format.
    
    Args:
        window: Window node from i3 tree
        format_type: Output format (JSON or Markdown)
        
    Returns:
        Formatted string representation of window info
    """
    if format_type == ResponseFormat.JSON:
        return json.dumps(window, indent=2)
    
    # Markdown format
    props = window.get("window_properties", {})
    geometry = window.get("rect", {})
    
    output = f"### Window: {window.get('name', 'Untitled')}\n\n"
    output += f"- **ID**: {window.get('window', 'N/A')}\n"
    output += f"- **Class**: {props.get('class', 'N/A')}\n"
    output += f"- **Instance**: {props.get('instance', 'N/A')}\n"
    output += f"- **Type**: {window.get('window_type', 'N/A')}\n"
    output += f"- **Focused**: {window.get('focused', False)}\n"
    output += f"- **Floating**: {'Yes' if window.get('type') == 'floating_con' else 'No'}\n"
    output += f"- **Geometry**: {geometry.get('width', 0)}x{geometry.get('height', 0)} "
    output += f"at ({geometry.get('x', 0)}, {geometry.get('y', 0)})\n"
    
    return output


def truncate_response(content: str, limit: int = CHARACTER_LIMIT) -> str:
    """
    Truncate response if it exceeds character limit.
    
    Args:
        content: Content to potentially truncate
        limit: Maximum character limit
        
    Returns:
        Original or truncated content with truncation notice
    """
    if len(content) <= limit:
        return content
    
    truncated = content[:limit]
    notice = (
        f"\n\n---\n**Response truncated** (exceeded {limit} characters). "
        f"Use more specific filters or criteria to narrow results."
    )
    return truncated + notice


# ============================================================================
# Window Management Tools
# ============================================================================

class FocusWindowInput(BaseModel):
    """Input for focusing windows."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    direction: Optional[Direction] = Field(
        default=None,
        description="Direction to focus: 'left', 'right', 'up', 'down'"
    )
    target: Optional[Literal["parent", "child"]] = Field(
        default=None,
        description="Special focus target: 'parent' or 'child'"
    )


@mcp.tool(
    name="i3_focus_window",
    annotations={
        "title": "Focus i3 Window",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_focus_window(params: FocusWindowInput) -> str:
    """
    Focus a window in i3wm by direction or target.
    
    This tool changes which window has keyboard focus. You can focus windows
    in a specific direction (left, right, up, down) or focus parent/child containers.
    
    Args:
        params (FocusWindowInput): Focus parameters containing:
            - direction (Optional[Direction]): Direction to focus
            - target (Optional[Literal["parent", "child"]]): Special focus target
    
    Returns:
        str: JSON-formatted result indicating success or failure
    
    Examples:
        - Focus window to the left: direction="left"
        - Focus parent container: target="parent"
    """
    if params.direction and params.target:
        return json.dumps({
            "success": False,
            "error": "Cannot specify both 'direction' and 'target'. Choose one."
        }, indent=2)
    
    if not params.direction and not params.target:
        return json.dumps({
            "success": False,
            "error": "Must specify either 'direction' or 'target'."
        }, indent=2)
    
    if params.direction:
        command = f"focus {params.direction.value}"
    else:
        command = f"focus {params.target}"
    
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class MoveWindowInput(BaseModel):
    """Input for moving windows."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    direction: Optional[Direction] = Field(
        default=None,
        description="Direction to move window: 'left', 'right', 'up', 'down'"
    )
    position_x: Optional[int] = Field(
        default=None,
        description="Absolute X position in pixels (for floating windows)"
    )
    position_y: Optional[int] = Field(
        default=None,
        description="Absolute Y position in pixels (for floating windows)"
    )
    center: bool = Field(
        default=False,
        description="Move window to center of screen (for floating windows)"
    )
    to_mouse: bool = Field(
        default=False,
        description="Move window to mouse cursor position (for floating windows)"
    )
    to_mark: Optional[str] = Field(
        default=None,
        description="Move window to position of marked window"
    )
    workspace: Optional[str] = Field(
        default=None,
        description="Move window to specified workspace (e.g., '1', '2', 'web')"
    )


@mcp.tool(
    name="i3_move_window",
    annotations={
        "title": "Move i3 Window",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_move_window(params: MoveWindowInput) -> str:
    """
    Move a window in i3wm by direction, to absolute position, or to a workspace.

    This tool moves the focused window. For tiled windows, you can move in directions.
    For floating windows, you can also move to absolute positions, center, mouse cursor,
    or to a marked window's location.

    Args:
        params (MoveWindowInput): Move parameters containing:
            - direction (Optional[Direction]): Direction to move (left/right/up/down)
            - position_x (Optional[int]): Absolute X position for floating windows
            - position_y (Optional[int]): Absolute Y position for floating windows
            - center (bool): Move to center of screen
            - to_mouse (bool): Move to mouse cursor position
            - to_mark (Optional[str]): Move to marked window's position
            - workspace (Optional[str]): Move to specified workspace

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Move window left: direction="left"
        - Move to absolute position: position_x=100, position_y=200
        - Center window: center=true
        - Move to mouse: to_mouse=true
        - Move to mark: to_mark="browser"
        - Move to workspace 2: workspace="2"
    """
    commands = []

    if params.workspace:
        commands.append(f"move container to workspace {params.workspace}")

    if params.direction:
        commands.append(f"move {params.direction.value}")

    # Handle positioning options (mutually exclusive)
    position_options = sum([
        params.center,
        params.to_mouse,
        params.to_mark is not None,
        params.position_x is not None or params.position_y is not None
    ])

    if position_options > 1:
        return json.dumps({
            "success": False,
            "error": "Can only specify one positioning option: center, to_mouse, to_mark, or absolute position (position_x/position_y)"
        }, indent=2)

    if params.center:
        commands.append("move position center")
    elif params.to_mouse:
        commands.append("move position mouse")
    elif params.to_mark:
        commands.append(f'move window to mark "{params.to_mark}"')
    elif params.position_x is not None and params.position_y is not None:
        commands.append(f"move position {params.position_x} px {params.position_y} px")
    elif params.position_x is not None or params.position_y is not None:
        return json.dumps({
            "success": False,
            "error": "Both position_x and position_y must be specified together."
        }, indent=2)

    if not commands:
        return json.dumps({
            "success": False,
            "error": "Must specify at least one move operation (direction, position, center, to_mouse, to_mark, or workspace)."
        }, indent=2)

    # Execute commands
    command = ", ".join(commands)
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class ResizeWindowInput(BaseModel):
    """Input for resizing windows."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    grow_shrink: Literal["grow", "shrink"] = Field(
        description="Whether to grow or shrink the window"
    )
    dimension: Literal["width", "height"] = Field(
        description="Which dimension to resize: 'width' or 'height'"
    )
    amount: int = Field(
        description="Amount in pixels to resize",
        ge=1,
        le=2000
    )
    absolute_width: Optional[int] = Field(
        default=None,
        description="Set absolute width in pixels (for floating windows)",
        ge=50,
        le=5000
    )
    absolute_height: Optional[int] = Field(
        default=None,
        description="Set absolute height in pixels (for floating windows)",
        ge=50,
        le=5000
    )


@mcp.tool(
    name="i3_resize_window",
    annotations={
        "title": "Resize i3 Window",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_resize_window(params: ResizeWindowInput) -> str:
    """
    Resize the focused window in i3wm.
    
    This tool can resize windows incrementally (grow/shrink by pixels) or set
    absolute dimensions for floating windows.
    
    Args:
        params (ResizeWindowInput): Resize parameters containing:
            - grow_shrink (Literal["grow", "shrink"]): Direction of resize
            - dimension (Literal["width", "height"]): Which dimension to resize
            - amount (int): Amount in pixels (1-2000)
            - absolute_width (Optional[int]): Set absolute width (50-5000px)
            - absolute_height (Optional[int]): Set absolute height (50-5000px)
    
    Returns:
        str: JSON-formatted result indicating success or failure
    
    Examples:
        - Grow width by 100px: grow_shrink="grow", dimension="width", amount=100
        - Set absolute size: absolute_width=800, absolute_height=600
    """
    if params.absolute_width or params.absolute_height:
        # Set absolute size (for floating windows)
        if not (params.absolute_width and params.absolute_height):
            return json.dumps({
                "success": False,
                "error": "Both absolute_width and absolute_height must be specified together."
            }, indent=2)
        
        command = f"floating enable, resize set {params.absolute_width} {params.absolute_height}"
    else:
        # Incremental resize
        command = f"resize {params.grow_shrink} {params.dimension} {params.amount} px"
    
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


@mcp.tool(
    name="i3_kill_window",
    annotations={
        "title": "Close i3 Window",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_kill_window() -> str:
    """
    Close the focused window in i3wm.
    
    This tool sends a close request to the focused window. The window may prompt
    to save changes before closing.
    
    Returns:
        str: JSON-formatted result indicating success or failure
    
    Warning:
        This is a destructive operation. Make sure the correct window is focused.
    """
    result = run_i3_msg("kill")
    return json.dumps(result, indent=2)


class ExecApplicationInput(BaseModel):
    """Input for executing applications."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    command: str = Field(
        description="Command to execute (e.g., 'kitty', 'firefox', 'terminator --class=scratchpad-term')",
        min_length=1,
        max_length=500
    )
    workspace: Optional[str] = Field(
        default=None,
        description="Workspace to launch application on (e.g., '1', '2', 'web', 'code')"
    )
    move_to_scratchpad: bool = Field(
        default=False,
        description="Move launched application to scratchpad after launching"
    )
    mark_as: Optional[str] = Field(
        default=None,
        description="Mark to assign to window (for named scratchpads). Requires move_to_scratchpad=true"
    )
    floating: bool = Field(
        default=False,
        description="Launch application as floating window"
    )
    fullscreen: bool = Field(
        default=False,
        description="Launch application in fullscreen mode"
    )


@mcp.tool(
    name="i3_exec",
    annotations={
        "title": "Execute Application in i3",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True  # Executes external commands
    }
)
async def i3_exec(params: ExecApplicationInput) -> str:
    """
    Execute an application in i3wm with optional workspace and scratchpad management.
    
    This tool launches applications using i3's exec command. You can specify where
    the application should be launched (workspace), whether it should be moved to
    scratchpad, and whether it should be floating or fullscreen.
    
    Args:
        params (ExecApplicationInput): Execution parameters containing:
            - command (str): Command to execute (e.g., 'kitty', 'firefox')
            - workspace (Optional[str]): Target workspace
            - move_to_scratchpad (bool): Move to scratchpad after launch
            - mark_as (Optional[str]): Mark for named scratchpad
            - floating (bool): Launch as floating window
            - fullscreen (bool): Launch in fullscreen mode
    
    Returns:
        str: JSON-formatted result indicating success or failure
    
    Examples:
        - Launch kitty on workspace 3: command="kitty", workspace="3"
        - Launch terminal in scratchpad: command="terminator", move_to_scratchpad=true, mark_as="terminal"
        - Launch firefox fullscreen: command="firefox", fullscreen=true
        - Launch floating calculator: command="gnome-calculator", floating=true
    
    Notes:
        - The command is executed asynchronously (--no-startup-id)
        - Use mark_as only with move_to_scratchpad=true
        - Workspace switching happens before execution
        - Floating and fullscreen modes require window criteria (may need delay)
    """
    # Validation
    if params.mark_as and not params.move_to_scratchpad:
        return json.dumps({
            "success": False,
            "error": "mark_as can only be used with move_to_scratchpad=true"
        }, indent=2)
    
    result_data = []

    # CRITICAL FIX: Switch to workspace FIRST as a separate synchronous command
    # This ensures the workspace is focused BEFORE launching the app
    if params.workspace:
        ws_result = run_i3_msg(f"workspace {params.workspace}")
        if not ws_result["success"]:
            return json.dumps(ws_result, indent=2)
        result_data.append(ws_result)

    # Now execute the application (it will appear on the currently focused workspace)
    exec_cmd = f"exec --no-startup-id {params.command}"
    exec_result = run_i3_msg(exec_cmd)
    result_data.append(exec_result)

    # Build the combined result
    result = {
        "success": exec_result["success"],
        "output": [r["output"] for r in result_data] if result_data else exec_result.get("output", []),
        "command": f"workspace {params.workspace}; {exec_cmd}" if params.workspace else exec_cmd
    }

    if not result["success"]:
        result["error"] = exec_result.get("error", "Unknown error")

    # Note: For floating, fullscreen, and scratchpad moves, we need to use for_window
    # rules or wait for the window to appear. Since we can't reliably wait in this
    # synchronous context, we'll provide instructions in the response.
    
    # Add helpful information to the response
    if result["success"]:
        notes = []
        
        if params.floating or params.fullscreen or params.move_to_scratchpad:
            notes.append("Application launched. To apply floating/fullscreen/scratchpad settings:")
            
            if params.floating:
                notes.append("  - Use i3_move_window or manually float the window once it appears")
            
            if params.fullscreen:
                notes.append("  - Run 'i3-msg fullscreen toggle' once window appears, or ask to make it fullscreen")
            
            if params.move_to_scratchpad:
                mark_instruction = f" and mark it as '{params.mark_as}'" if params.mark_as else ""
                notes.append(f"  - Use i3_scratchpad_move to move the window to scratchpad{mark_instruction}")
        
        if notes:
            result["notes"] = notes
            result["suggestion"] = (
                "For automatic window management on launch, consider adding rules to your i3 config:\n"
                f"  for_window [class=\"{params.command.split()[0]}\"] "
            )
            if params.floating:
                result["suggestion"] += "floating enable, "
            if params.fullscreen:
                result["suggestion"] += "fullscreen enable, "
            if params.move_to_scratchpad:
                mark_str = f', mark "{params.mark_as}"' if params.mark_as else ""
                result["suggestion"] += f"move scratchpad{mark_str}"
    
    return json.dumps(result, indent=2)


class MoveToOutputInput(BaseModel):
    """Input for moving containers to outputs."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    output: Optional[str] = Field(
        default=None,
        description="Output name (e.g., 'eDP-1', 'HDMI-1') or 'primary'"
    )
    direction: Optional[Direction] = Field(
        default=None,
        description="Direction to move: 'left', 'right', 'up', 'down'"
    )


@mcp.tool(
    name="i3_move_to_output",
    annotations={
        "title": "Move i3 Container to Output",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_move_to_output(params: MoveToOutputInput) -> str:
    """
    Move the focused container to a different output (monitor) in i3wm.

    This tool moves the focused window to another monitor either by name,
    direction, or to the primary output. Useful for multi-monitor setups.

    Args:
        params (MoveToOutputInput): Parameters containing:
            - output (Optional[str]): Output name or 'primary'
            - direction (Optional[Direction]): Direction to move

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Move to primary monitor: output="primary"
        - Move to specific output: output="HDMI-1"
        - Move to output on right: direction="right"

    Notes:
        - Specify either output name or direction, not both
        - Use i3_get_outputs to discover output names
        - Direction is relative to current output position
        - Window follows to the target output
    """
    if not params.output and not params.direction:
        return json.dumps({
            "success": False,
            "error": "Must specify either 'output' or 'direction'"
        }, indent=2)

    if params.output and params.direction:
        return json.dumps({
            "success": False,
            "error": "Cannot specify both 'output' and 'direction'. Choose one."
        }, indent=2)

    if params.output:
        command = f"move container to output {params.output}"
    else:
        command = f"move container to output {params.direction.value}"

    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


# ============================================================================
# Phase 1: Essential Window Controls
# ============================================================================

class FloatingToggleInput(BaseModel):
    """Input for toggling floating mode."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    enable: Optional[bool] = Field(
        default=None,
        description="Explicitly enable (true) or disable (false) floating mode. If not specified, toggles current state."
    )


@mcp.tool(
    name="i3_floating_toggle",
    annotations={
        "title": "Toggle i3 Window Floating Mode",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_floating_toggle(params: FloatingToggleInput) -> str:
    """
    Toggle floating mode for the focused window in i3wm.

    This tool can toggle floating mode, or explicitly enable/disable it.
    Floating windows can be moved freely and positioned anywhere on screen.

    Args:
        params (FloatingToggleInput): Parameters containing:
            - enable (Optional[bool]): Explicitly enable/disable (None to toggle)

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Toggle floating: (no parameters)
        - Enable floating: enable=true
        - Disable floating (tile window): enable=false
    """
    if params.enable is None:
        command = "floating toggle"
    else:
        state = "enable" if params.enable else "disable"
        command = f"floating {state}"

    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class BorderInput(BaseModel):
    """Input for setting border style."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    style: BorderStyle = Field(
        description="Border style: 'normal', 'pixel', 'none', or 'toggle'"
    )
    width: Optional[int] = Field(
        default=None,
        description="Border width in pixels (only for 'normal' and 'pixel' styles)",
        ge=0,
        le=50
    )


@mcp.tool(
    name="i3_border_set",
    annotations={
        "title": "Set i3 Window Border Style",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_border_set(params: BorderInput) -> str:
    """
    Set the border style for the focused window in i3wm.

    This tool controls window borders and title bars. Options include normal
    (with title bar), pixel (border only), none (no decoration), or toggle
    to cycle through styles.

    Args:
        params (BorderInput): Parameters containing:
            - style (BorderStyle): Border style to apply
            - width (Optional[int]): Border width in pixels (0-50)

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Remove borders: style="none"
        - Set pixel border: style="pixel", width=2
        - Normal with title: style="normal", width=1
        - Toggle borders: style="toggle"

    Notes:
        - 'normal' includes title bar and border
        - 'pixel' is border only (no title bar)
        - 'none' removes all decorations
        - Width only applies to 'normal' and 'pixel' styles
    """
    if params.style == BorderStyle.TOGGLE:
        command = "border toggle"
    elif params.width is not None:
        command = f"border {params.style.value} {params.width}"
    else:
        command = f"border {params.style.value}"

    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class StickyToggleInput(BaseModel):
    """Input for toggling sticky mode."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    enable: Optional[bool] = Field(
        default=None,
        description="Explicitly enable (true) or disable (false) sticky mode. If not specified, toggles current state."
    )


@mcp.tool(
    name="i3_sticky_toggle",
    annotations={
        "title": "Toggle i3 Window Sticky Mode",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_sticky_toggle(params: StickyToggleInput) -> str:
    """
    Toggle sticky mode for the focused window in i3wm.

    Sticky windows stay visible on all workspaces. This is useful for keeping
    important windows (music players, monitoring tools, chat apps) always visible
    while you switch between workspaces.

    Args:
        params (StickyToggleInput): Parameters containing:
            - enable (Optional[bool]): Explicitly enable/disable (None to toggle)

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Toggle sticky: (no parameters)
        - Make window sticky: enable=true
        - Remove sticky: enable=false

    Notes:
        - Sticky windows must be floating
        - Sticky windows follow you across all workspaces
        - Useful for: music players, chat apps, monitoring dashboards
    """
    if params.enable is None:
        command = "sticky toggle"
    else:
        state = "enable" if params.enable else "disable"
        command = f"sticky {state}"

    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class SwapContainerInput(BaseModel):
    """Input for swapping containers."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    target_id: Optional[int] = Field(
        default=None,
        description="X11 window ID of target container (to swap with focused window OR with source_id)"
    )
    target_con_id: Optional[int] = Field(
        default=None,
        description="i3 container ID of target container (to swap with focused window OR with source_con_id)"
    )
    target_mark: Optional[str] = Field(
        default=None,
        description="Mark identifier of target container (to swap with focused window OR with source_mark)"
    )
    source_id: Optional[int] = Field(
        default=None,
        description="X11 window ID of source container (if not specified, uses focused window)"
    )
    source_con_id: Optional[int] = Field(
        default=None,
        description="i3 container ID of source container (if not specified, uses focused window)"
    )
    source_mark: Optional[str] = Field(
        default=None,
        description="Mark identifier of source container (if not specified, uses focused window)"
    )


@mcp.tool(
    name="i3_swap_containers",
    annotations={
        "title": "Swap i3 Containers",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_swap_containers(params: SwapContainerInput) -> str:
    """
    Swap two containers in i3wm.

    This tool exchanges the positions of two containers. You can either:
    1. Swap the focused window with a target window (legacy behavior)
    2. Swap two specific windows by specifying both source and target

    Args:
        params (SwapContainerInput): Parameters containing:
            - target_id (Optional[int]): X11 window ID of target
            - target_con_id (Optional[int]): i3 container ID of target
            - target_mark (Optional[str]): Mark identifier of target
            - source_id (Optional[int]): X11 window ID of source (optional)
            - source_con_id (Optional[int]): i3 container ID of source (optional)
            - source_mark (Optional[str]): Mark identifier of source (optional)

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Swap focused window with target: target_id=94557854
        - Swap two specific windows: source_id=12345, target_id=67890
        - Swap using marks: source_mark="window1", target_mark="window2"

    Notes:
        - If no source is specified, swaps focused window with target (legacy behavior)
        - If source is specified, swaps the two specified windows regardless of focus
        - Only one source parameter and one target parameter should be specified
        - Use i3_get_tree or i3_get_focused to find IDs
        - Use marks for easier identification
    """
    # Validate target parameters
    if not params.target_id and not params.target_con_id and not params.target_mark:
        return json.dumps({
            "success": False,
            "error": "Must specify one of: target_id, target_con_id, or target_mark"
        }, indent=2)

    target_count = sum([params.target_id is not None, params.target_con_id is not None, params.target_mark is not None])
    if target_count > 1:
        return json.dumps({
            "success": False,
            "error": "Only specify one target parameter (target_id, target_con_id, or target_mark)"
        }, indent=2)

    # Validate source parameters
    source_count = sum([params.source_id is not None, params.source_con_id is not None, params.source_mark is not None])
    if source_count > 1:
        return json.dumps({
            "success": False,
            "error": "Only specify one source parameter (source_id, source_con_id, or source_mark)"
        }, indent=2)

    # Build the swap command
    if params.target_id:
        target_criteria = f"id {params.target_id}"
    elif params.target_con_id:
        target_criteria = f"con_id {params.target_con_id}"
    else:
        target_criteria = f'mark "{params.target_mark}"'

    # If source is specified, we need to focus it first, then swap
    if source_count > 0:
        if params.source_id:
            source_criteria = f"[id={params.source_id}]"
        elif params.source_con_id:
            source_criteria = f"[con_id={params.source_con_id}]"
        else:
            source_criteria = f'[con_mark="{params.source_mark}"]'

        # Focus the source window first, then swap with target
        focus_command = f"{source_criteria} focus"
        focus_result = run_i3_msg(focus_command)

        if not focus_result["success"]:
            return json.dumps({
                "success": False,
                "error": f"Failed to focus source window: {focus_result.get('error', 'Unknown error')}",
                "focus_result": focus_result
            }, indent=2)

        # Now swap with target
        swap_command = f"swap container with {target_criteria}"
        swap_result = run_i3_msg(swap_command)

        return json.dumps({
            "success": swap_result["success"],
            "output": swap_result.get("output", []),
            "command": f"{focus_command}; {swap_command}",
            "note": "Focused source window then swapped with target"
        }, indent=2)
    else:
        # Legacy behavior: swap focused window with target
        command = f"swap container with {target_criteria}"
        result = run_i3_msg(command)
        return json.dumps(result, indent=2)


class WorkspaceNavigateInput(BaseModel):
    """Input for workspace navigation."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    direction: WorkspaceNavigation = Field(
        description="Navigation direction: 'next', 'prev', 'next_on_output', 'prev_on_output', or 'back_and_forth'"
    )


@mcp.tool(
    name="i3_workspace_navigate",
    annotations={
        "title": "Navigate i3 Workspaces",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_workspace_navigate(params: WorkspaceNavigateInput) -> str:
    """
    Navigate between workspaces in i3wm.

    This tool provides directional workspace navigation without needing to know
    workspace names or numbers. Navigate forward/backward, restrict to current
    output, or toggle between last two workspaces.

    Args:
        params (WorkspaceNavigateInput): Parameters containing:
            - direction (WorkspaceNavigation): Navigation direction

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Next workspace: direction="next"
        - Previous workspace: direction="prev"
        - Next on current monitor: direction="next_on_output"
        - Toggle last two workspaces: direction="back_and_forth"

    Notes:
        - 'next_on_output' and 'prev_on_output' only cycle workspaces on current monitor
        - 'back_and_forth' toggles between current and previously focused workspace
        - Useful for keyboard-driven workflows
    """
    command = f"workspace {params.direction.value}"
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


# ============================================================================
# Scratchpad Management Tools (with Named Scratchpad Support)
# ============================================================================

class ScratchpadShowInput(BaseModel):
    """Input for showing scratchpad windows."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    scratchpad_name: Optional[str] = Field(
        default=None,
        description="Name of scratchpad to show (uses criteria matching). If not specified, shows default scratchpad."
    )


@mcp.tool(
    name="i3_scratchpad_show",
    annotations={
        "title": "Show i3 Scratchpad",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_scratchpad_show(params: ScratchpadShowInput) -> str:
    """
    Show/toggle a scratchpad window in i3wm.
    
    This tool shows the scratchpad window. If it's already visible, it hides it.
    Supports named scratchpads by specifying a scratchpad_name.
    
    Named scratchpads work by using i3 criteria. For example, if you have a terminal
    with class "scratchpad-term", you can show it specifically by name.
    
    Args:
        params (ScratchpadShowInput): Parameters containing:
            - scratchpad_name (Optional[str]): Name/identifier for named scratchpad
    
    Returns:
        str: JSON-formatted result indicating success or failure
    
    Examples:
        - Show default scratchpad: (no parameters)
        - Show named scratchpad: scratchpad_name="terminal"
    
    Note:
        Named scratchpads require windows to be marked (e.g., with title, class, or mark).
        Use i3 config to assign windows to named scratchpads, like:
        for_window [class="scratchpad-term"] move scratchpad
    """
    if params.scratchpad_name:
        # Show named scratchpad using criteria
        command = f'[title="{params.scratchpad_name}"] scratchpad show'
    else:
        # Show default scratchpad
        command = "scratchpad show"
    
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class ScratchpadMoveInput(BaseModel):
    """Input for moving windows to scratchpad."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    mark_as: Optional[str] = Field(
        default=None,
        description="Mark/name to assign to window when moving to scratchpad (for named scratchpads)"
    )


@mcp.tool(
    name="i3_scratchpad_move",
    annotations={
        "title": "Move Window to i3 Scratchpad",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_scratchpad_move(params: ScratchpadMoveInput) -> str:
    """
    Move the focused window to scratchpad in i3wm.
    
    This tool moves the focused window to the scratchpad. Optionally, you can
    mark the window with a name to create a named scratchpad.
    
    Args:
        params (ScratchpadMoveInput): Parameters containing:
            - mark_as (Optional[str]): Mark/name for the window (creates named scratchpad)
    
    Returns:
        str: JSON-formatted result indicating success or failure
    
    Examples:
        - Move to default scratchpad: (no parameters)
        - Move and mark as named scratchpad: mark_as="my-terminal"
    
    Note:
        Marked windows can be retrieved using i3_scratchpad_show with criteria.
    """
    commands = []
    
    if params.mark_as:
        commands.append(f'mark "{params.mark_as}"')
    
    commands.append("move scratchpad")
    
    command = ", ".join(commands)
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class ScratchpadListInput(BaseModel):
    """Input for listing scratchpad windows."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'json' for raw data or 'markdown' for human-readable"
    )


class ScratchpadHideAllInput(BaseModel):
    """Input for hiding all visible scratchpad windows."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    response_format: ResponseFormat = Field(
        default=ResponseFormat.JSON,
        description="Output format: 'json' for detailed results or 'markdown' for human-readable summary"
    )


@mcp.tool(
    name="i3_scratchpad_list",
    annotations={
        "title": "List i3 Scratchpad Windows",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_scratchpad_list(params: ScratchpadListInput) -> str:
    """
    List all windows in the scratchpad in i3wm.
    
    This tool queries the i3 tree and finds all windows currently in the scratchpad.
    
    Args:
        params (ScratchpadListInput): Parameters containing:
            - response_format (ResponseFormat): Output format (json or markdown)
    
    Returns:
        str: List of scratchpad windows in specified format
    
    Example output (markdown):
        ### Scratchpad Windows
        
        - Terminal (ID: 12345678)
        - Calculator (ID: 87654321)
    """
    result = run_i3_msg_get_type("tree")
    
    if not result["success"]:
        return json.dumps(result, indent=2)
    
    # Find scratchpad workspace
    def find_scratchpad(node):
        if node.get("name") == "__i3_scratch":
            return node
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            found = find_scratchpad(child)
            if found:
                return found
        return None
    
    scratchpad = find_scratchpad(result["data"])
    
    if not scratchpad:
        return json.dumps({
            "success": True,
            "scratchpad_windows": [],
            "message": "No scratchpad found or scratchpad is empty"
        }, indent=2)
    
    # Get all windows from scratchpad
    windows = find_windows_recursive(scratchpad)
    
    if params.response_format == ResponseFormat.JSON:
        return json.dumps({
            "success": True,
            "scratchpad_windows": windows,
            "count": len(windows)
        }, indent=2)
    
    # Markdown format
    output = "### Scratchpad Windows\n\n"
    
    if not windows:
        output += "No windows in scratchpad.\n"
    else:
        for window in windows:
            props = window.get("window_properties", {})
            marks = window.get("marks", [])
            mark_str = f" [{', '.join(marks)}]" if marks else ""
            output += f"- **{window.get('name', 'Untitled')}**{mark_str}\n"
            output += f"  - Class: {props.get('class', 'N/A')}\n"
            output += f"  - ID: {window.get('window', 'N/A')}\n\n"
    
    output += f"\nTotal: {len(windows)} window(s)\n"

    return truncate_response(output)


@mcp.tool(
    name="i3_scratchpad_hide_all",
    annotations={
        "title": "Hide All Visible i3 Scratchpads",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_scratchpad_hide_all(params: ScratchpadHideAllInput) -> str:
    """
    Hide all visible scratchpad windows in i3wm.

    This tool finds all scratchpad windows that are currently visible on any workspace
    and hides them by moving them back to the scratchpad. It uses the `output` field
    in the i3 tree to reliably detect visibility:
    - output == "__i3" → window is hidden
    - output == monitor name → window is visible

    Args:
        params (ScratchpadHideAllInput): Parameters containing:
            - response_format (ResponseFormat): Output format (json or markdown)

    Returns:
        str: Result summary with count of hidden windows

    Example output:
        {
          "success": true,
          "hidden_count": 3,
          "total_found": 3,
          "windows_hidden": [
            {"id": 12345, "name": "Obsidian", "class": "obsidian"},
            {"id": 67890, "name": "Terminal", "class": "Terminator"}
          ]
        }

    Note:
        This function uses `move scratchpad` instead of `scratchpad show` toggle
        because it's more reliable and idempotent. It's safe to call even if all
        scratchpads are already hidden.
    """
    result = run_i3_msg_get_type("tree")

    if not result["success"]:
        return json.dumps(result, indent=2)

    # Find all visible scratchpad windows
    def find_visible_scratchpads(node):
        """
        Recursively find all visible scratchpad windows.
        A scratchpad is visible if:
        1. scratchpad_state != "none"
        2. output != "__i3"
        """
        windows = []

        # Check if this is a visible scratchpad container
        scratchpad_state = node.get('scratchpad_state')
        output = node.get('output')

        if (scratchpad_state and
            scratchpad_state != 'none' and
            output != '__i3'):

            # Get window info from child con node
            for child in node.get('nodes', []):
                if child.get('window'):
                    windows.append({
                        'window_id': child.get('window'),
                        'name': child.get('name', 'Untitled'),
                        'class': child.get('window_properties', {}).get('class', 'N/A'),
                        'output': output,
                        'scratchpad_state': scratchpad_state
                    })
                    break

        # Recurse through tree
        for child in node.get('nodes', []) + node.get('floating_nodes', []):
            windows.extend(find_visible_scratchpads(child))

        return windows

    tree = result["data"]
    visible_windows = find_visible_scratchpads(tree)

    if not visible_windows:
        result_data = {
            "success": True,
            "message": "No visible scratchpad windows found",
            "hidden_count": 0,
            "total_found": 0
        }

        if params.response_format == ResponseFormat.MARKDOWN:
            return "### Hide All Scratchpads\n\n✓ No visible scratchpad windows found. All scratchpads are already hidden.\n"

        return json.dumps(result_data, indent=2)

    # Hide each visible window
    hidden_count = 0
    errors = []
    windows_hidden = []

    for window in visible_windows:
        window_id = window['window_id']
        hide_result = run_i3_msg(f'[id={window_id}] move scratchpad')

        if hide_result["success"]:
            hidden_count += 1
            windows_hidden.append({
                'id': window_id,
                'name': window['name'],
                'class': window['class']
            })
        else:
            errors.append({
                'window_id': window_id,
                'name': window['name'],
                'error': hide_result.get("error", "Unknown error")
            })

    # Build result
    result_data = {
        "success": True,
        "hidden_count": hidden_count,
        "total_found": len(visible_windows),
        "windows_hidden": windows_hidden
    }

    if errors:
        result_data["errors"] = errors
        result_data["success"] = hidden_count > 0  # Partial success if some worked

    if params.response_format == ResponseFormat.MARKDOWN:
        output = "### Hide All Scratchpads\n\n"

        if hidden_count > 0:
            output += f"✓ Successfully hidden {hidden_count} scratchpad window(s):\n\n"
            for win in windows_hidden:
                output += f"- **{win['name']}** (class: {win['class']}, ID: {win['id']})\n"

        if errors:
            output += f"\n✗ Failed to hide {len(errors)} window(s):\n\n"
            for err in errors:
                output += f"- **{err['name']}** (ID: {err['window_id']}): {err['error']}\n"

        if hidden_count == 0:
            output += "\n⚠ No windows were hidden.\n"

        return output

    return json.dumps(result_data, indent=2)


# ============================================================================
# Workspace Management Tools
# ============================================================================

class WorkspaceSwitchInput(BaseModel):
    """Input for switching workspaces."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    workspace: str = Field(
        description="Workspace name or number to switch to (e.g., '1', '2', 'web', 'code')"
    )


@mcp.tool(
    name="i3_workspace_switch",
    annotations={
        "title": "Switch i3 Workspace",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_workspace_switch(params: WorkspaceSwitchInput) -> str:
    """
    Switch to a workspace in i3wm.
    
    This tool changes the currently visible workspace. If the workspace doesn't
    exist, i3 will create it.
    
    Args:
        params (WorkspaceSwitchInput): Parameters containing:
            - workspace (str): Workspace name or number
    
    Returns:
        str: JSON-formatted result indicating success or failure
    
    Examples:
        - Switch to workspace 1: workspace="1"
        - Switch to named workspace: workspace="web"
    """
    command = f"workspace {params.workspace}"
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class WorkspaceMoveInput(BaseModel):
    """Input for moving containers to workspaces."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    workspace: str = Field(
        description="Target workspace name or number (e.g., '1', '2', 'web')"
    )
    follow: bool = Field(
        default=False,
        description="Whether to switch to the workspace after moving the container"
    )


@mcp.tool(
    name="i3_workspace_move",
    annotations={
        "title": "Move Container to i3 Workspace",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_workspace_move(params: WorkspaceMoveInput) -> str:
    """
    Move the focused container to a workspace in i3wm.
    
    This tool moves the focused window or container to the specified workspace.
    Optionally, you can follow the container to that workspace.
    
    Args:
        params (WorkspaceMoveInput): Parameters containing:
            - workspace (str): Target workspace name or number
            - follow (bool): Whether to switch to workspace after moving
    
    Returns:
        str: JSON-formatted result indicating success or failure
    
    Examples:
        - Move to workspace 2: workspace="2"
        - Move and follow: workspace="2", follow=true
    """
    commands = [f"move container to workspace {params.workspace}"]
    
    if params.follow:
        commands.append(f"workspace {params.workspace}")
    
    command = ", ".join(commands)
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class BulkWorkspaceMoveInput(BaseModel):
    """Input for bulk moving workspaces between outputs."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    workspaces: List[str] = Field(
        description="List of workspace names/numbers to move"
    )
    target_output: str = Field(
        description="Target output name (e.g., 'eDP-1', 'DP-1', 'HDMI-1')"
    )
    preserve_workspace: Optional[str] = Field(
        default=None,
        description="Workspace to keep on the source output (won't be moved)"
    )
    placeholder_workspace: Optional[str] = Field(
        default=None,
        description="Placeholder workspace to create on source output (if all workspaces will be moved)"
    )


@mcp.tool(
    name="i3_workspace_bulk_move",
    annotations={
        "title": "Bulk Move Workspaces Between Outputs",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_workspace_bulk_move(params: BulkWorkspaceMoveInput) -> str:
    """
    Move multiple workspaces between outputs with proper handling.

    This tool safely moves multiple workspaces from one output to another,
    ensuring that at least one workspace remains on each active output.
    This prevents i3 from automatically creating unwanted workspaces or
    moving workspaces unexpectedly.

    Args:
        params (BulkWorkspaceMoveInput): Parameters containing:
            - workspaces (List[str]): List of workspace names to move
            - target_output (str): Target output name
            - preserve_workspace (Optional[str]): Workspace to keep on source
            - placeholder_workspace (Optional[str]): Workspace to create on source

    Returns:
        str: JSON-formatted result with details of moved workspaces

    Examples:
        - Move workspaces 1-5 to DP-1: workspaces=["1","2","3","4","5"], target_output="DP-1"
        - Move all except workspace 10: preserve_workspace="10"
        - Create placeholder workspace 1: placeholder_workspace="1"

    Strategy:
        1. If preserve_workspace is specified, skip moving it
        2. If placeholder_workspace is specified, create it on source output first
        3. Move workspaces sequentially to avoid race conditions
        4. Return summary of moved workspaces
    """
    moved_workspaces = []
    failed_workspaces = []

    # Step 1: Get current workspace layout
    ws_result = run_i3_msg_get_type("workspaces")
    if not ws_result["success"]:
        return json.dumps({
            "success": False,
            "error": "Failed to get workspace list",
            "details": ws_result
        }, indent=2)

    current_workspaces = ws_result["data"]
    workspace_map = {ws["name"]: ws for ws in current_workspaces}

    # Step 2: If placeholder_workspace specified, create it on source output first
    if params.placeholder_workspace:
        # Find which output will lose workspaces
        source_outputs = set()
        for ws_name in params.workspaces:
            if ws_name in workspace_map:
                source_outputs.add(workspace_map[ws_name]["output"])

        # Create placeholder on each source output
        for source_output in source_outputs:
            # Focus the output and create workspace
            focus_result = run_i3_msg(f"focus output {source_output}")
            if not focus_result["success"]:
                continue

            create_result = run_i3_msg(f"workspace {params.placeholder_workspace}")
            if not create_result["success"]:
                failed_workspaces.append({
                    "workspace": params.placeholder_workspace,
                    "reason": "Failed to create placeholder workspace"
                })

    # Step 3: Move workspaces sequentially
    for ws_name in params.workspaces:
        # Skip if this is the preserve_workspace
        if params.preserve_workspace and ws_name == params.preserve_workspace:
            continue

        # Skip if workspace doesn't exist
        if ws_name not in workspace_map:
            failed_workspaces.append({
                "workspace": ws_name,
                "reason": "Workspace does not exist"
            })
            continue

        # Move the workspace
        command = f"workspace {ws_name}; move workspace to output {params.target_output}"
        result = run_i3_msg(command)

        if result["success"]:
            moved_workspaces.append({
                "workspace": ws_name,
                "from_output": workspace_map[ws_name]["output"],
                "to_output": params.target_output
            })
        else:
            failed_workspaces.append({
                "workspace": ws_name,
                "reason": "Move command failed",
                "details": result
            })

    return json.dumps({
        "success": True,
        "moved_count": len(moved_workspaces),
        "failed_count": len(failed_workspaces),
        "moved_workspaces": moved_workspaces,
        "failed_workspaces": failed_workspaces,
        "preserved_workspace": params.preserve_workspace,
        "placeholder_workspace": params.placeholder_workspace
    }, indent=2)


class WorkspaceListInput(BaseModel):
    """Input for listing workspaces."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'json' for raw data or 'markdown' for human-readable"
    )


@mcp.tool(
    name="i3_workspace_list",
    annotations={
        "title": "List i3 Workspaces",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_workspace_list(params: WorkspaceListInput) -> str:
    """
    List all workspaces in i3wm.
    
    This tool queries i3 for all workspaces and their current state (focused, visible, urgent).
    
    Args:
        params (WorkspaceListInput): Parameters containing:
            - response_format (ResponseFormat): Output format (json or markdown)
    
    Returns:
        str: List of workspaces in specified format
    
    Example output (markdown):
        ### i3 Workspaces
        
        1. Workspace 1 [FOCUSED] (output: eDP-1)
        2. Workspace 2 [VISIBLE] (output: HDMI-1)
        3. Workspace 3 (output: eDP-1)
    """
    result = run_i3_msg_get_type("workspaces")
    
    if not result["success"]:
        return json.dumps(result, indent=2)
    
    workspaces = result["data"]
    
    if params.response_format == ResponseFormat.JSON:
        return json.dumps({
            "success": True,
            "workspaces": workspaces
        }, indent=2)
    
    # Markdown format
    output = "### i3 Workspaces\n\n"
    
    for ws in workspaces:
        name = ws.get("name", "Unknown")
        num = ws.get("num", "?")
        output_name = ws.get("output", "Unknown")
        
        flags = []
        if ws.get("focused"):
            flags.append("FOCUSED")
        if ws.get("visible"):
            flags.append("VISIBLE")
        if ws.get("urgent"):
            flags.append("URGENT")
        
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        
        output += f"{num}. **{name}**{flag_str}\n"
        output += f"   - Output: {output_name}\n\n"
    
    return truncate_response(output)


# ============================================================================
# Phase 2: Power User Tools
# ============================================================================

class BarModeInput(BaseModel):
    """Input for setting bar mode."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    mode: BarMode = Field(
        description="Bar display mode: 'dock', 'hide', or 'invisible'"
    )
    bar_id: Optional[str] = Field(
        default=None,
        description="Specific bar ID (optional, applies to all bars if not specified)"
    )


@mcp.tool(
    name="i3_bar_mode",
    annotations={
        "title": "Set i3 Bar Mode",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_bar_mode(params: BarModeInput) -> str:
    """
    Set the display mode for i3bar.

    This tool controls i3bar visibility. Modes include 'dock' (always visible),
    'hide' (hidden until modifier pressed), and 'invisible' (never shown).

    Args:
        params (BarModeInput): Parameters containing:
            - mode (BarMode): Display mode to set
            - bar_id (Optional[str]): Specific bar ID (optional)

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Always show bar: mode="dock"
        - Hide bar: mode="hide"
        - Make bar invisible: mode="invisible"
        - Set specific bar: mode="dock", bar_id="bar-0"

    Notes:
        - 'dock' is the default, permanently visible
        - 'hide' shows bar when modifier key is pressed
        - 'invisible' completely hides the bar
        - Useful for presentations, screenshots, or focus modes
    """
    if params.bar_id:
        command = f"bar mode {params.mode.value} {params.bar_id}"
    else:
        command = f"bar mode {params.mode.value}"

    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class BarHiddenStateInput(BaseModel):
    """Input for setting bar hidden state."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    state: BarHiddenState = Field(
        description="Bar hidden state: 'hide' or 'show'"
    )
    bar_id: Optional[str] = Field(
        default=None,
        description="Specific bar ID (optional, applies to all bars if not specified)"
    )


@mcp.tool(
    name="i3_bar_hidden_state",
    annotations={
        "title": "Set i3 Bar Hidden State",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_bar_hidden_state(params: BarHiddenStateInput) -> str:
    """
    Set the hidden state for i3bar (when in hide mode).

    This tool controls whether the bar is currently shown or hidden when
    bar mode is set to 'hide'. This is useful for temporarily showing/hiding
    the bar.

    Args:
        params (BarHiddenStateInput): Parameters containing:
            - state (BarHiddenState): Hidden state ('hide' or 'show')
            - bar_id (Optional[str]): Specific bar ID (optional)

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Show hidden bar: state="show"
        - Hide bar: state="hide"
        - Toggle specific bar: state="show", bar_id="bar-0"

    Notes:
        - Only works when bar mode is set to 'hide'
        - Use i3_bar_mode to set the bar mode first
        - Useful for quick bar toggling
    """
    if params.bar_id:
        command = f"bar hidden_state {params.state.value} {params.bar_id}"
    else:
        command = f"bar hidden_state {params.state.value}"

    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class GetOutputsInput(BaseModel):
    """Input for getting outputs."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'json' for raw data or 'markdown' for human-readable"
    )


@mcp.tool(
    name="i3_get_outputs",
    annotations={
        "title": "Get i3 Outputs (Monitors)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_get_outputs(params: GetOutputsInput) -> str:
    """
    List all display outputs (monitors) in i3wm.

    This tool queries i3 for all connected displays and their properties,
    including active status, current workspace, and position.

    Args:
        params (GetOutputsInput): Parameters containing:
            - response_format (ResponseFormat): Output format (json or markdown)

    Returns:
        str: List of outputs in specified format

    Example output (markdown):
        ### i3 Outputs (Monitors)

        1. eDP-1 [ACTIVE] [PRIMARY]
           - Current workspace: 1
           - Position: 0x0
           - Resolution: 1920x1080

        2. HDMI-1 [ACTIVE]
           - Current workspace: 3
           - Position: 1920x0
           - Resolution: 2560x1440
    """
    result = run_i3_msg_get_type("outputs")

    if not result["success"]:
        return json.dumps(result, indent=2)

    outputs = result["data"]

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({
            "success": True,
            "outputs": outputs
        }, indent=2)

    # Markdown format
    output = "### i3 Outputs (Monitors)\n\n"

    for idx, out in enumerate(outputs, 1):
        name = out.get("name", "Unknown")
        active = out.get("active", False)
        primary = out.get("primary", False)
        current_workspace = out.get("current_workspace", "None")

        flags = []
        if active:
            flags.append("ACTIVE")
        if primary:
            flags.append("PRIMARY")

        flag_str = f" [{', '.join(flags)}]" if flags else ""

        output += f"{idx}. **{name}**{flag_str}\n"
        output += f"   - Current workspace: {current_workspace}\n"

        rect = out.get("rect", {})
        if rect:
            output += f"   - Position: {rect.get('x', 0)}x{rect.get('y', 0)}\n"
            output += f"   - Resolution: {rect.get('width', 0)}x{rect.get('height', 0)}\n"

        output += "\n"

    return truncate_response(output)


class MarkSetInput(BaseModel):
    """Input for setting marks."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    mark: str = Field(
        description="Mark identifier to set on the focused window",
        min_length=1,
        max_length=100
    )
    mode: Literal["replace", "add", "toggle"] = Field(
        default="replace",
        description="Mark mode: 'replace' (default), 'add', or 'toggle'"
    )


@mcp.tool(
    name="i3_mark_set",
    annotations={
        "title": "Set i3 Window Mark",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_mark_set(params: MarkSetInput) -> str:
    """
    Set a mark on the focused window in i3wm.

    Marks are persistent labels for windows that make them easy to identify
    and reference. Use marks with swap, focus, and scratchpad operations.

    Args:
        params (MarkSetInput): Parameters containing:
            - mark (str): Mark identifier
            - mode (Literal): 'replace' (default), 'add', or 'toggle'

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Set mark (replace existing): mark="terminal"
        - Add additional mark: mark="important", mode="add"
        - Toggle mark: mark="sticky", mode="toggle"

    Notes:
        - 'replace' removes existing marks and sets new one (default)
        - 'add' allows multiple marks on same window
        - 'toggle' removes mark if it exists, adds if it doesn't
        - Marks persist until explicitly removed
        - Useful for window organization and automation
    """
    if params.mode == "replace":
        command = f'mark --replace "{params.mark}"'
    elif params.mode == "add":
        command = f'mark --add "{params.mark}"'
    else:  # toggle
        command = f'mark --toggle "{params.mark}"'

    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class MarkUnmarkInput(BaseModel):
    """Input for unmarking windows."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    mark: Optional[str] = Field(
        default=None,
        description="Mark identifier to remove (removes all marks if not specified)"
    )


@mcp.tool(
    name="i3_mark_unmark",
    annotations={
        "title": "Remove i3 Window Mark",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_mark_unmark(params: MarkUnmarkInput) -> str:
    """
    Remove mark(s) from the focused window in i3wm.

    This tool removes either a specific mark or all marks from the focused window.

    Args:
        params (MarkUnmarkInput): Parameters containing:
            - mark (Optional[str]): Specific mark to remove (removes all if not specified)

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Remove specific mark: mark="terminal"
        - Remove all marks: (no parameters)

    Notes:
        - If mark is specified, only that mark is removed
        - If mark is not specified, all marks are removed from the window
        - Safe to call even if mark doesn't exist
    """
    if params.mark:
        command = f'unmark "{params.mark}"'
    else:
        command = "unmark"

    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class GetMarksInput(BaseModel):
    """Input for getting marks."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'json' for raw data or 'markdown' for human-readable"
    )


@mcp.tool(
    name="i3_get_marks",
    annotations={
        "title": "Get All i3 Marks",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_get_marks(params: GetMarksInput) -> str:
    """
    List all marks currently set in i3wm.

    This tool queries i3 for all marks that have been set on windows.
    Useful for discovering what marks are available for reference.

    Args:
        params (GetMarksInput): Parameters containing:
            - response_format (ResponseFormat): Output format (json or markdown)

    Returns:
        str: List of marks in specified format

    Example output (markdown):
        ### i3 Marks

        - terminal
        - browser
        - editor
        - sticky_notes

        Total: 4 mark(s)
    """
    result = run_i3_msg_get_type("marks")

    if not result["success"]:
        return json.dumps(result, indent=2)

    marks = result["data"]

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({
            "success": True,
            "marks": marks,
            "count": len(marks)
        }, indent=2)

    # Markdown format
    output = "### i3 Marks\n\n"

    if not marks:
        output += "No marks currently set.\n"
    else:
        for mark in marks:
            output += f"- {mark}\n"

        output += f"\nTotal: {len(marks)} mark(s)\n"

    return output


class FocusModeInput(BaseModel):
    """Input for focus mode."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    target: FocusTarget = Field(
        description="Focus target: 'floating', 'tiling', or 'mode_toggle'"
    )


@mcp.tool(
    name="i3_focus_mode",
    annotations={
        "title": "Focus i3 Window by Mode",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_focus_mode(params: FocusModeInput) -> str:
    """
    Focus windows by their mode (floating or tiling) in i3wm.

    This tool allows you to switch focus between floating and tiling windows,
    or toggle between the two modes.

    Args:
        params (FocusModeInput): Parameters containing:
            - target (FocusTarget): Focus target mode

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Focus floating windows: target="floating"
        - Focus tiling windows: target="tiling"
        - Toggle between modes: target="mode_toggle"

    Notes:
        - 'floating' focuses the next floating window
        - 'tiling' focuses the next tiling window
        - 'mode_toggle' toggles between floating and tiling windows
        - Useful for keyboard-driven window navigation
    """
    command = f"focus {params.target.value}"
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class FocusOutputInput(BaseModel):
    """Input for focusing outputs."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    output: Optional[str] = Field(
        default=None,
        description="Output name (e.g., 'eDP-1', 'HDMI-1')"
    )
    direction: Optional[Direction] = Field(
        default=None,
        description="Direction to focus: 'left', 'right', 'up', 'down'"
    )


@mcp.tool(
    name="i3_focus_output",
    annotations={
        "title": "Focus i3 Output (Monitor)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_focus_output(params: FocusOutputInput) -> str:
    """
    Focus a specific output (monitor) in i3wm.

    This tool switches focus to a different monitor either by name or direction.
    Useful for multi-monitor setups.

    Args:
        params (FocusOutputInput): Parameters containing:
            - output (Optional[str]): Output name
            - direction (Optional[Direction]): Direction to focus

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Focus by name: output="HDMI-1"
        - Focus by direction: direction="right"

    Notes:
        - Specify either output name or direction, not both
        - Use i3_get_outputs to discover output names
        - Direction is relative to current output position
        - Focus follows to the focused output
    """
    if not params.output and not params.direction:
        return json.dumps({
            "success": False,
            "error": "Must specify either 'output' or 'direction'"
        }, indent=2)

    if params.output and params.direction:
        return json.dumps({
            "success": False,
            "error": "Cannot specify both 'output' and 'direction'. Choose one."
        }, indent=2)

    if params.output:
        command = f"focus output {params.output}"
    else:
        command = f"focus output {params.direction.value}"

    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class WorkspaceRenameInput(BaseModel):
    """Input for renaming workspaces."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    old_name: Optional[str] = Field(
        default=None,
        description="Current workspace name (renames focused workspace if not specified)"
    )
    new_name: str = Field(
        description="New workspace name",
        min_length=1,
        max_length=100
    )


@mcp.tool(
    name="i3_workspace_rename",
    annotations={
        "title": "Rename i3 Workspace",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_workspace_rename(params: WorkspaceRenameInput) -> str:
    """
    Rename a workspace in i3wm.

    This tool renames either the currently focused workspace or a specific
    workspace by name. Useful for dynamic workspace organization.

    Args:
        params (WorkspaceRenameInput): Parameters containing:
            - old_name (Optional[str]): Current workspace name (optional)
            - new_name (str): New workspace name

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Rename focused workspace: new_name="work"
        - Rename specific workspace: old_name="1", new_name="browser"

    Notes:
        - If old_name not specified, renames the focused workspace
        - New name can include spaces
        - Useful for semantic workspace naming
        - Workspace numbers can be preserved with format "1: name"
    """
    if params.old_name:
        command = f'rename workspace "{params.old_name}" to "{params.new_name}"'
    else:
        command = f'rename workspace to "{params.new_name}"'

    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


# ============================================================================
# Layout Control Tools
# ============================================================================

class LayoutChangeInput(BaseModel):
    """Input for changing container layout."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    layout: Layout = Field(
        description="Layout type: 'stacking', 'tabbed', 'splith', 'splitv', or 'toggle split'"
    )


@mcp.tool(
    name="i3_layout_change",
    annotations={
        "title": "Change i3 Container Layout",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_layout_change(params: LayoutChangeInput) -> str:
    """
    Change the layout of the focused container in i3wm.
    
    This tool changes how windows are arranged within a container. Options include
    stacking, tabbed, split horizontal, split vertical, or toggle between splits.
    
    Args:
        params (LayoutChangeInput): Parameters containing:
            - layout (Layout): Layout type to apply
    
    Returns:
        str: JSON-formatted result indicating success or failure
    
    Examples:
        - Switch to tabbed layout: layout="tabbed"
        - Toggle split direction: layout="toggle split"
    """
    command = f"layout {params.layout.value}"
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class SplitOrientationInput(BaseModel):
    """Input for setting split orientation."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    orientation: SplitOrientation = Field(
        description="Split orientation: 'horizontal', 'vertical', or 'toggle'"
    )


@mcp.tool(
    name="i3_split_orientation",
    annotations={
        "title": "Set i3 Split Orientation",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_split_orientation(params: SplitOrientationInput) -> str:
    """
    Set the split orientation for the next window in i3wm.
    
    This tool determines whether the next window opened in the focused container
    will split horizontally or vertically.
    
    Args:
        params (SplitOrientationInput): Parameters containing:
            - orientation (SplitOrientation): Split orientation to set
    
    Returns:
        str: JSON-formatted result indicating success or failure
    
    Examples:
        - Set horizontal split: orientation="horizontal"
        - Toggle split: orientation="toggle"
    """
    if params.orientation == SplitOrientation.HORIZONTAL:
        command = "split h"
    elif params.orientation == SplitOrientation.VERTICAL:
        command = "split v"
    else:
        command = "split toggle"
    
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class FullscreenToggleInput(BaseModel):
    """Input for toggling fullscreen mode."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    enable: Optional[bool] = Field(
        default=None,
        description="Explicitly enable (true) or disable (false) fullscreen. If not specified, toggles current state."
    )
    mode: Literal["normal", "global"] = Field(
        default="normal",
        description="Fullscreen mode: 'normal' (default) or 'global' (fullscreen across all outputs)"
    )


@mcp.tool(
    name="i3_fullscreen_toggle",
    annotations={
        "title": "Toggle i3 Window Fullscreen",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_fullscreen_toggle(params: FullscreenToggleInput) -> str:
    """
    Toggle fullscreen mode for the focused window in i3wm.
    
    This tool can toggle fullscreen mode, explicitly enable/disable it, or use
    global fullscreen mode (across all outputs).
    
    Args:
        params (FullscreenToggleInput): Parameters containing:
            - enable (Optional[bool]): Explicitly enable/disable (None to toggle)
            - mode (Literal["normal", "global"]): Fullscreen mode type
    
    Returns:
        str: JSON-formatted result indicating success or failure
    
    Examples:
        - Toggle fullscreen: (no parameters)
        - Enable fullscreen: enable=true
        - Disable fullscreen: enable=false
        - Global fullscreen: mode="global"
    
    Notes:
        - Normal fullscreen: Window fills current output
        - Global fullscreen: Window fills all outputs (useful for presentations)
    """
    if params.enable is None:
        # Toggle
        if params.mode == "global":
            command = "fullscreen toggle global"
        else:
            command = "fullscreen toggle"
    else:
        # Explicitly enable or disable
        state = "enable" if params.enable else "disable"
        if params.mode == "global":
            command = f"fullscreen {state} global"
        else:
            command = f"fullscreen {state}"
    
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


# ============================================================================
# Query Tools
# ============================================================================

class GetTreeInput(BaseModel):
    """Input for getting window tree."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    window_class: Optional[str] = Field(
        default=None,
        description="Filter windows by class name (e.g., 'Firefox', 'Terminator')"
    )
    window_title: Optional[str] = Field(
        default=None,
        description="Filter windows by title (partial match, case-insensitive)"
    )
    window_instance: Optional[str] = Field(
        default=None,
        description="Filter windows by instance name"
    )
    window_role: Optional[str] = Field(
        default=None,
        description="Filter windows by window role"
    )
    window_type: Optional[str] = Field(
        default=None,
        description="Filter windows by window type (e.g., 'normal', 'dialog', 'utility')"
    )
    floating: Optional[bool] = Field(
        default=None,
        description="Filter by floating status (true for floating windows, false for tiling)"
    )
    urgent: Optional[bool] = Field(
        default=None,
        description="Filter by urgent status (true for urgent windows only)"
    )
    workspace: Optional[str] = Field(
        default=None,
        description="Filter windows by workspace name or number"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'json' for raw tree or 'markdown' for readable format"
    )


@mcp.tool(
    name="i3_get_tree",
    annotations={
        "title": "Get i3 Window Tree",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_get_tree(params: GetTreeInput) -> str:
    """
    Get the i3 window tree with optional filtering.

    This tool retrieves the complete i3 window tree structure. You can filter
    by various window properties to find specific windows.

    Args:
        params (GetTreeInput): Parameters containing:
            - window_class (Optional[str]): Filter by window class
            - window_title (Optional[str]): Filter by window title
            - window_instance (Optional[str]): Filter by window instance
            - window_role (Optional[str]): Filter by window role
            - window_type (Optional[str]): Filter by window type
            - floating (Optional[bool]): Filter by floating status
            - urgent (Optional[bool]): Filter by urgent status
            - workspace (Optional[str]): Filter by workspace
            - response_format (ResponseFormat): Output format (json or markdown)

    Returns:
        str: Window tree or filtered windows in specified format

    Examples:
        - Get all windows: (no filters)
        - Find Firefox windows: window_class="Firefox"
        - Find terminal windows: window_title="terminal"
        - Find floating windows: floating=true
        - Find urgent windows: urgent=true
        - Find dialog windows: window_type="dialog"
    """
    result = run_i3_msg_get_type("tree")

    if not result["success"]:
        return json.dumps(result, indent=2)

    tree = result["data"]

    # Apply filters if specified
    criteria = {}
    if params.window_class:
        criteria["class"] = params.window_class
    if params.window_title:
        criteria["title"] = params.window_title
    if params.window_instance:
        criteria["instance"] = params.window_instance
    if params.window_role:
        criteria["role"] = params.window_role
    if params.window_type:
        criteria["type"] = params.window_type
    if params.floating is not None:
        criteria["floating"] = params.floating
    if params.urgent is not None:
        criteria["urgent"] = params.urgent
    if params.workspace:
        criteria["workspace"] = params.workspace
    
    if criteria:
        windows = find_windows_recursive(tree, criteria)
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "success": True,
                "windows": windows,
                "count": len(windows)
            }, indent=2)
        
        # Markdown format
        output = f"### Matching Windows ({len(windows)} found)\n\n"
        
        if not windows:
            output += "No windows match the specified criteria.\n"
        else:
            for window in windows:
                output += format_window_info(window, ResponseFormat.MARKDOWN)
                output += "\n---\n\n"
        
        return truncate_response(output)
    
    # No filters - return full tree
    if params.response_format == ResponseFormat.JSON:
        return truncate_response(json.dumps(tree, indent=2))
    
    # For markdown without filters, just return a summary
    all_windows = find_windows_recursive(tree)
    output = f"### i3 Window Tree Summary\n\n"
    output += f"Total windows: {len(all_windows)}\n\n"
    output += "Use window_class or window_title parameters to filter specific windows.\n"
    
    return output


@mcp.tool(
    name="i3_get_focused",
    annotations={
        "title": "Get Focused i3 Window",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_get_focused() -> str:
    """
    Get information about the currently focused window in i3wm.
    
    This tool retrieves detailed information about whichever window currently
    has keyboard focus.
    
    Returns:
        str: JSON-formatted information about the focused window
    
    Example output:
        {
          "success": true,
          "focused_window": {
            "name": "Terminal - user@host",
            "class": "Terminator",
            "id": 12345678,
            "geometry": "1920x1080+0+0"
          }
        }
    """
    result = run_i3_msg_get_type("tree")
    
    if not result["success"]:
        return json.dumps(result, indent=2)
    
    tree = result["data"]
    
    # Find focused window
    def find_focused(node):
        if node.get("focused"):
            return node
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            found = find_focused(child)
            if found:
                return found
        return None
    
    focused = find_focused(tree)
    
    if not focused:
        return json.dumps({
            "success": True,
            "focused_window": None,
            "message": "No window is currently focused"
        }, indent=2)
    
    # Extract relevant info
    props = focused.get("window_properties", {})
    geometry = focused.get("rect", {})
    
    window_info = {
        "name": focused.get("name", "Untitled"),
        "class": props.get("class", "N/A"),
        "instance": props.get("instance", "N/A"),
        "id": focused.get("window", 0),
        "type": focused.get("window_type", "N/A"),
        "geometry": f"{geometry.get('width', 0)}x{geometry.get('height', 0)}+{geometry.get('x', 0)}+{geometry.get('y', 0)}",
        "floating": focused.get("type") == "floating_con",
        "marks": focused.get("marks", [])
    }
    
    return json.dumps({
        "success": True,
        "focused_window": window_info
    }, indent=2)


# ============================================================================
# Phase 3: Gaps Control (i3-gaps)
# ============================================================================

class GapsInput(BaseModel):
    """Input for setting gaps."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    inner: Optional[int] = Field(
        default=None,
        description="Inner gaps between windows (pixels)",
        ge=0,
        le=500
    )
    outer: Optional[int] = Field(
        default=None,
        description="Outer gaps around workspace edges (pixels)",
        ge=0,
        le=500
    )
    scope: Literal["current", "all"] = Field(
        default="current",
        description="Apply to current workspace or all workspaces"
    )


@mcp.tool(
    name="i3_gaps_set",
    annotations={
        "title": "Set i3 Gaps",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_gaps_set(params: GapsInput) -> str:
    """
    Set inner and/or outer gaps for i3-gaps.

    Controls spacing between windows (inner) and around workspace edges (outer).
    Modern i3 includes gaps support by default.

    Args:
        params (GapsInput): Parameters containing:
            - inner (Optional[int]): Inner gaps in pixels (0-500)
            - outer (Optional[int]): Outer gaps in pixels (0-500)
            - scope (Literal["current", "all"]): Apply to current or all workspaces

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Set inner gaps: inner=10
        - Set both gaps: inner=10, outer=5
        - Apply to all workspaces: scope="all"

    Notes:
        - Inner gaps: space between adjacent windows
        - Outer gaps: space between windows and screen edges
        - Set to 0 to disable gaps
    """
    if not params.inner and not params.outer:
        return json.dumps({
            "success": False,
            "error": "Must specify at least one of: inner, outer"
        }, indent=2)

    commands = []
    scope_prefix = "workspace" if params.scope == "current" else "global"

    if params.inner is not None:
        commands.append(f"gaps inner {scope_prefix} set {params.inner}")

    if params.outer is not None:
        commands.append(f"gaps outer {scope_prefix} set {params.outer}")

    command = ", ".join(commands)
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class GapsAdjustInput(BaseModel):
    """Input for adjusting gaps."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    gap_type: Literal["inner", "outer"] = Field(
        description="Type of gap to adjust: 'inner' or 'outer'"
    )
    operation: Literal["plus", "minus", "set"] = Field(
        description="Operation: 'plus' (increase), 'minus' (decrease), or 'set' (absolute)"
    )
    amount: int = Field(
        description="Amount in pixels",
        ge=0,
        le=500
    )
    scope: Literal["current", "all"] = Field(
        default="current",
        description="Apply to current workspace or all workspaces"
    )


@mcp.tool(
    name="i3_gaps_adjust",
    annotations={
        "title": "Adjust i3 Gaps",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_gaps_adjust(params: GapsAdjustInput) -> str:
    """
    Adjust gaps incrementally or set to specific value.

    This tool allows fine-grained gap control with relative or absolute adjustments.

    Args:
        params (GapsAdjustInput): Parameters containing:
            - gap_type (Literal["inner", "outer"]): Which gap to adjust
            - operation (Literal["plus", "minus", "set"]): How to adjust
            - amount (int): Amount in pixels (0-500)
            - scope (Literal["current", "all"]): Workspace scope

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Increase inner gaps by 5: gap_type="inner", operation="plus", amount=5
        - Decrease outer gaps by 3: gap_type="outer", operation="minus", amount=3
        - Set inner gaps to 15: gap_type="inner", operation="set", amount=15
    """
    scope_prefix = "workspace" if params.scope == "current" else "global"
    command = f"gaps {params.gap_type.value} {scope_prefix} {params.operation.value} {params.amount}"

    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


class GapsToggleInput(BaseModel):
    """Input for toggling gaps."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    scope: Literal["current", "all"] = Field(
        default="current",
        description="Apply to current workspace or all workspaces"
    )


@mcp.tool(
    name="i3_gaps_toggle",
    annotations={
        "title": "Toggle i3 Gaps",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_gaps_toggle(params: GapsToggleInput) -> str:
    """
    Toggle gaps on/off (smart gaps).

    Quickly enable or disable all gaps. Useful for maximizing screen space
    when needed.

    Args:
        params (GapsToggleInput): Parameters containing:
            - scope (Literal["current", "all"]): Workspace scope

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Toggle current workspace gaps: (no parameters)
        - Toggle all workspace gaps: scope="all"

    Notes:
        - This toggles between current gap values and zero
        - Previous gap values are remembered when re-enabling
    """
    scope_prefix = "workspace" if params.scope == "current" else "global"
    command = f"gaps {scope_prefix} toggle"

    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


# ============================================================================
# Phase 4: Focus by Criteria
# ============================================================================

class FocusByCriteriaInput(BaseModel):
    """Input for focusing by window criteria."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    window_class: Optional[str] = Field(
        default=None,
        description="Window class to focus (e.g., 'Firefox')"
    )
    window_title: Optional[str] = Field(
        default=None,
        description="Window title to match (partial)"
    )
    window_instance: Optional[str] = Field(
        default=None,
        description="Window instance to focus"
    )
    con_mark: Optional[str] = Field(
        default=None,
        description="Container mark to focus"
    )
    urgent: Optional[bool] = Field(
        default=None,
        description="Focus urgent window (true) or non-urgent (false)"
    )


@mcp.tool(
    name="i3_focus_by_criteria",
    annotations={
        "title": "Focus Window by Criteria",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_focus_by_criteria(params: FocusByCriteriaInput) -> str:
    """
    Focus a window matching specific criteria.

    This tool allows quick focusing of windows by properties without needing
    to query the tree and extract IDs first.

    Args:
        params (FocusByCriteriaInput): Parameters containing:
            - window_class (Optional[str]): Window class
            - window_title (Optional[str]): Window title (partial match)
            - window_instance (Optional[str]): Window instance
            - con_mark (Optional[str]): Container mark
            - urgent (Optional[bool]): Urgent state

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Focus Firefox: window_class="Firefox"
        - Focus by title: window_title="Terminal"
        - Focus marked window: con_mark="browser"
        - Focus urgent window: urgent=true

    Notes:
        - At least one criterion must be specified
        - Multiple criteria create AND conditions
        - Uses i3's native criteria syntax for efficiency
    """
    criteria_parts = []

    if params.window_class:
        criteria_parts.append(f'class="{params.window_class}"')
    if params.window_title:
        criteria_parts.append(f'title="{params.window_title}"')
    if params.window_instance:
        criteria_parts.append(f'instance="{params.window_instance}"')
    if params.con_mark:
        criteria_parts.append(f'con_mark="{params.con_mark}"')
    if params.urgent is not None:
        criteria_parts.append(f'urgent={"yes" if params.urgent else "no"}')

    if not criteria_parts:
        return json.dumps({
            "success": False,
            "error": "Must specify at least one criterion"
        }, indent=2)

    criteria = " ".join(criteria_parts)
    command = f"[{criteria}] focus"

    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


# ============================================================================
# Phase 5: Binding Modes
# ============================================================================

class BindingModeInput(BaseModel):
    """Input for binding mode operations."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'json' for raw data or 'markdown' for human-readable"
    )


@mcp.tool(
    name="i3_get_binding_modes",
    annotations={
        "title": "Get i3 Binding Modes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_get_binding_modes(params: BindingModeInput) -> str:
    """
    Get all defined binding modes in i3.

    Binding modes are custom keyboard contexts defined in your i3 config
    (e.g., "resize", "system", "launcher"). This tool lists all available modes.

    Args:
        params (BindingModeInput): Parameters containing:
            - response_format (ResponseFormat): Output format

    Returns:
        str: List of binding modes in specified format

    Example output (markdown):
        ### i3 Binding Modes

        - default
        - resize
        - system
        - launcher

        Total: 4 mode(s)

    Notes:
        - "default" is always present
        - Custom modes are defined in i3 config via `mode "name" { ... }`
        - Use i3_get_binding_state to see current active mode
    """
    result = run_i3_msg_get_type("binding_modes")

    if not result["success"]:
        return json.dumps(result, indent=2)

    modes = result["data"]

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({
            "success": True,
            "binding_modes": modes,
            "count": len(modes)
        }, indent=2)

    # Markdown format
    output = "### i3 Binding Modes\n\n"

    if not modes:
        output += "No binding modes found.\n"
    else:
        for mode in modes:
            output += f"- {mode}\n"
        output += f"\nTotal: {len(modes)} mode(s)\n"

    return output


@mcp.tool(
    name="i3_get_binding_state",
    annotations={
        "title": "Get Current Binding State",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_get_binding_state() -> str:
    """
    Get the currently active binding mode.

    Returns which binding mode is currently active (usually "default"
    unless you've entered a custom mode like "resize").

    Returns:
        str: JSON-formatted current binding mode

    Example output:
        {
          "success": true,
          "binding_state": {
            "name": "resize"
          }
        }

    Notes:
        - "default" means normal key bindings are active
        - Other modes indicate custom binding contexts
        - Use i3_mode_activate to switch modes programmatically
    """
    result = run_i3_msg_get_type("binding_state")

    if not result["success"]:
        return json.dumps(result, indent=2)

    return json.dumps({
        "success": True,
        "binding_state": result["data"]
    }, indent=2)


class ModeActivateInput(BaseModel):
    """Input for activating binding modes."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    mode_name: str = Field(
        description="Name of binding mode to activate",
        min_length=1,
        max_length=100
    )


@mcp.tool(
    name="i3_mode_activate",
    annotations={
        "title": "Activate Binding Mode",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def i3_mode_activate(params: ModeActivateInput) -> str:
    """
    Activate a specific binding mode.

    Switch to a named binding mode, changing the active key bindings.

    Args:
        params (ModeActivateInput): Parameters containing:
            - mode_name (str): Name of mode to activate

    Returns:
        str: JSON-formatted result indicating success or failure

    Examples:
        - Enter resize mode: mode_name="resize"
        - Return to default: mode_name="default"

    Notes:
        - Mode must be defined in your i3 config
        - Use i3_get_binding_modes to see available modes
        - Bindings change immediately upon mode activation
    """
    command = f'mode "{params.mode_name}"'
    result = run_i3_msg(command)
    return json.dumps(result, indent=2)


# ============================================================================
# Phase 6: Configuration Inspection
# ============================================================================

@mcp.tool(
    name="i3_get_version",
    annotations={
        "title": "Get i3 Version",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_get_version() -> str:
    """
    Get i3 version information.

    Returns detailed version information about the running i3 instance,
    including version number, build date, and variant (i3/i3-gaps).

    Returns:
        str: JSON-formatted version information

    Example output:
        {
          "success": true,
          "version": {
            "major": 4,
            "minor": 23,
            "patch": 0,
            "human_readable": "4.23 (2023-10-29)",
            "loaded_config_file_name": "/home/user/.config/i3/config"
          }
        }

    Notes:
        - Useful for feature compatibility checks
        - Shows active config file path
        - Includes git commit if built from source
    """
    result = run_i3_msg_get_type("version")

    if not result["success"]:
        return json.dumps(result, indent=2)

    return json.dumps({
        "success": True,
        "version": result["data"]
    }, indent=2)


class GetConfigInput(BaseModel):
    """Input for getting config."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    include_content: bool = Field(
        default=False,
        description="Include full config file content (can be large)"
    )


@mcp.tool(
    name="i3_get_config",
    annotations={
        "title": "Get i3 Configuration",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_get_config(params: GetConfigInput) -> str:
    """
    Get the current i3 configuration.

    Returns information about the loaded i3 config, including the config
    content and which files were included.

    Args:
        params (GetConfigInput): Parameters containing:
            - include_content (bool): Include full config text (default: false)

    Returns:
        str: JSON-formatted configuration information

    Example output:
        {
          "success": true,
          "config": {
            "config": "... full config content ...",
            "included_files": [...]
          }
        }

    Notes:
        - Config content can be very large (set include_content=false for metadata only)
        - Shows all included files from include directives
        - Config is read-only; changes require editing config file and reload

    Warning:
        - Response may be truncated if config is very large
        - Use include_content=false for just metadata
    """
    result = run_i3_msg_get_type("config")

    if not result["success"]:
        return json.dumps(result, indent=2)

    config_data = result["data"]

    if not params.include_content and "config" in config_data:
        # Provide summary instead of full content
        config_preview = config_data["config"][:500] + "..." if len(config_data["config"]) > 500 else config_data["config"]
        return json.dumps({
            "success": True,
            "config_summary": {
                "config_length": len(config_data["config"]),
                "config_preview": config_preview,
                "included_files": config_data.get("included_files", [])
            },
            "note": "Use include_content=true to get full config"
        }, indent=2)

    return truncate_response(json.dumps({
        "success": True,
        "config": config_data
    }, indent=2))


class GetBarConfigInput(BaseModel):
    """Input for getting bar config."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    bar_id: Optional[str] = Field(
        default=None,
        description="Specific bar ID (omit to list all bars)"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'json' for raw data or 'markdown' for human-readable"
    )


@mcp.tool(
    name="i3_get_bar_config",
    annotations={
        "title": "Get i3bar Configuration",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def i3_get_bar_config(params: GetBarConfigInput) -> str:
    """
    Get i3bar configuration.

    Returns configuration for i3bar(s), including colors, position,
    status command, and other bar settings.

    Args:
        params (GetBarConfigInput): Parameters containing:
            - bar_id (Optional[str]): Specific bar ID (None for all)
            - response_format (ResponseFormat): Output format

    Returns:
        str: Bar configuration in specified format

    Examples:
        - List all bars: (no parameters)
        - Get specific bar: bar_id="bar-0"

    Notes:
        - Without bar_id, returns list of bar IDs
        - With bar_id, returns full configuration for that bar
        - Includes colors, fonts, tray settings, workspace buttons, etc.
    """
    if not params.bar_id:
        # List all bar IDs
        result = run_i3_msg_get_type("bar_config")

        if not result["success"]:
            return json.dumps(result, indent=2)

        bar_ids = result["data"]

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "success": True,
                "bar_ids": bar_ids,
                "count": len(bar_ids)
            }, indent=2)

        output = "### i3bar IDs\n\n"
        if not bar_ids:
            output += "No bars found.\n"
        else:
            for bar_id in bar_ids:
                output += f"- {bar_id}\n"
            output += f"\nTotal: {len(bar_ids)} bar(s)\n"
            output += "\nUse bar_id parameter to get detailed config for a specific bar.\n"

        return output

    # Get specific bar config
    try:
        result_cmd = subprocess.run(
            ["i3-msg", "-t", "get_bar_config", params.bar_id],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        bar_config = json.loads(result_cmd.stdout)

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "success": True,
                "bar_config": bar_config
            }, indent=2)

        # Markdown format
        output = f"### i3bar Configuration: {params.bar_id}\n\n"
        output += f"- **Position:** {bar_config.get('position', 'N/A')}\n"
        output += f"- **Mode:** {bar_config.get('mode', 'N/A')}\n"
        output += f"- **Status Command:** {bar_config.get('status_command', 'N/A')}\n"
        output += f"- **Font:** {bar_config.get('font', 'N/A')}\n"
        output += f"- **Workspace Buttons:** {bar_config.get('workspace_buttons', False)}\n"
        output += f"- **Tray Output:** {bar_config.get('tray_output', 'N/A')}\n"

        return truncate_response(output)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Failed to get bar config: {str(e)}"
        }, indent=2)


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    # Run the MCP server with stdio transport
    mcp.run()
