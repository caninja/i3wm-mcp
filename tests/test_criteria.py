import pytest

from i3mcp.criteria import WindowCriteria, escape_value, pattern_for, prefix_command


def test_escape_order():
    # A backslash must be doubled, and a quote escaped, without double-escaping.
    assert escape_value('say "hi"') == r'say \"hi\"'
    assert escape_value("back\\slash") == "back\\\\slash"


def test_exact_mode_anchors_and_quotes_literally():
    assert pattern_for("Firefox", "exact") == r"^\QFirefox\E$"


def test_substring_mode_quotes_without_anchors():
    assert pattern_for("fire", "substring") == r"\Qfire\E"


def test_regex_mode_passes_through():
    assert pattern_for("(?i)^fire", "regex") == "(?i)^fire"


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
    assert WindowCriteria(all=True).to_selector() == "[all]"


def test_floating_is_tri_state():
    assert WindowCriteria(floating=True).to_selector() == "[floating]"
    assert WindowCriteria(floating=False).to_selector() == "[tiling]"
    assert WindowCriteria().to_selector() == ""


def test_machine_is_no_longer_a_criterion():
    with pytest.raises(ValueError):
        WindowCriteria(machine="localhost")


def test_urgent_uses_i3_vocabulary_not_yes():
    got = WindowCriteria(urgent="latest").to_selector()
    assert got == "[urgent=latest]"


def test_urgent_rejects_boolean_style_values():
    with pytest.raises(ValueError):
        WindowCriteria(urgent="yes")


def test_regex_mode_applies_to_string_fields():
    got = WindowCriteria(title="term.*", match="regex").to_selector()
    assert got == '[title="term.*"]'


def test_prefix_command_without_criteria_is_bare():
    assert prefix_command(None, "kill") == "kill"
    assert prefix_command(WindowCriteria(), "kill") == "kill"


def test_prefix_command_with_criteria():
    got = prefix_command(WindowCriteria(con_mark="term"), "kill")
    assert got == r'[con_mark="^\Qterm\E$"] kill'


def test_literal_backslash_e_does_not_end_the_quoting():
    # PCRE cannot quote \E inside \Q...\E: close, match a literal backslash and
    # E, reopen. Backslashes the PCRE needs are doubled for i3's string parser.
    assert pattern_for(r"a\Eb", "exact") == r"^\Qa\E\\\\E\Qb\E$"


def test_quote_and_backslash_in_a_value_are_escaped_for_i3():
    assert pattern_for('say "hi" \\ bye', "substring") == r'\Qsay \"hi\" \\ bye\E'


def test_regex_values_are_escaped_for_i3_only():
    assert pattern_for(r'\d "x"', "regex") == r'\\d \"x\"'


def test_window_type_is_a_plain_string_and_is_escaped():
    got = WindowCriteria(window_type='dia"log').to_selector()
    assert got == r'[window_type="dia\"log"]'


def test_urgent_takes_only_latest_or_oldest():
    import pydantic
    import pytest

    assert WindowCriteria(urgent="oldest").to_selector() == "[urgent=oldest]"
    with pytest.raises(pydantic.ValidationError):
        WindowCriteria(urgent="newest")
