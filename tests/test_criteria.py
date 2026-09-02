import pytest

from i3mcp.criteria import WindowCriteria, escape_value, pattern_for, prefix_command
from i3mcp.enums import MatchMode


def test_escape_order():
    # A backslash must be doubled, and a quote escaped, without double-escaping.
    assert escape_value('say "hi"') == r'say \"hi\"'
    assert escape_value("back\\slash") == "back\\\\slash"


def test_exact_mode_anchors_and_quotes_literally():
    assert pattern_for("Firefox", MatchMode.EXACT) == r"^\QFirefox\E$"


def test_substring_mode_quotes_without_anchors():
    assert pattern_for("fire", MatchMode.SUBSTRING) == r"\Qfire\E"


def test_regex_mode_passes_through():
    assert pattern_for("(?i)^fire", MatchMode.REGEX) == "(?i)^fire"


def test_empty_criteria_is_empty_selector():
    assert WindowCriteria().to_selector() == ""


def test_class_criteria_is_exact_by_default():
    got = WindowCriteria(window_class="Firefox").to_selector()
    assert got == r'[class="^\QFirefox\E$"]'


def test_multiple_criteria_are_anded():
    got = WindowCriteria(window_class="Firefox", con_mark="browser").to_selector()
    assert got == r'[class="^\QFirefox\E$" con_mark="^\Qbrowser\E$"]'


def test_con_id_is_numeric_and_unquoted():
    assert WindowCriteria(con_id=12345).to_selector() == "[con_id=12345]"


def test_window_id_is_numeric_and_unquoted():
    assert WindowCriteria(window_id=98765).to_selector() == "[id=98765]"


def test_valueless_criteria_emit_bare_keys():
    assert WindowCriteria(floating=True).to_selector() == "[floating]"
    assert WindowCriteria(tiling=True).to_selector() == "[tiling]"
    assert WindowCriteria(all=True).to_selector() == "[all]"


def test_urgent_uses_i3_vocabulary_not_yes():
    got = WindowCriteria(urgent="latest").to_selector()
    assert got == "[urgent=latest]"


def test_urgent_rejects_boolean_style_values():
    with pytest.raises(ValueError):
        WindowCriteria(urgent="yes")


def test_regex_mode_applies_to_string_fields():
    got = WindowCriteria(title="term.*", match=MatchMode.REGEX).to_selector()
    assert got == '[title="term.*"]'


def test_prefix_command_without_criteria_is_bare():
    assert prefix_command(None, "kill") == "kill"
    assert prefix_command(WindowCriteria(), "kill") == "kill"


def test_prefix_command_with_criteria():
    got = prefix_command(WindowCriteria(con_mark="term"), "kill")
    assert got == r'[con_mark="^\Qterm\E$"] kill'
