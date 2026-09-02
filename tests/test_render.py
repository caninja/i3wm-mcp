import json

import pytest

from i3mcp import render
from i3mcp.ipc import I3Error


def test_ok_is_valid_json_with_success_true():
    parsed = json.loads(render.ok(command="nop"))
    assert parsed["success"] is True
    assert parsed["command"] == "nop"


def test_err_carries_the_message():
    parsed = json.loads(render.err("boom", command="bad"))
    assert parsed["success"] is False
    assert parsed["error"] == "boom"


def test_run_sends_command_and_reports_success(fake):
    result = json.loads(render.run("nop hello"))
    assert fake.last_command == "nop hello"
    assert result["success"] is True


def test_run_success_payload_has_no_replies_list(fake):
    result = json.loads(render.run("nop hello"))
    assert "replies" not in result
    assert result["command"] == "nop hello"


def test_run_surfaces_i3_error_text(fake):
    fake.command_replies = [[{"success": False, "error": "Expected 'current', 'all'"}]]
    result = json.loads(render.run("gaps inner workspace set 10"))
    assert result["success"] is False
    assert "current" in result["error"]


def test_json_list_stays_valid_json_when_truncated():
    items = [{"name": "x" * 100, "index": i} for i in range(500)]
    out = render.json_list("windows", items, limit=2000)
    parsed = json.loads(out)  # must not raise
    assert parsed["success"] is True
    assert len(parsed["windows"]) < 500
    assert parsed["truncated"] is True
    assert parsed["omitted"] == 500 - len(parsed["windows"])


def test_json_list_untruncated_has_no_truncation_keys():
    parsed = json.loads(render.json_list("windows", [{"a": 1}]))
    assert "truncated" not in parsed
    assert parsed["count"] == 1
