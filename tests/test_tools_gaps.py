import json

from i3mcp.tools.gaps import i3_gaps


async def test_set_inner_uses_current_not_workspace(fake):
    await i3_gaps(gap="inner", amount=10)
    assert fake.last_command == "gaps inner current set 10"


async def test_scope_all(fake):
    await i3_gaps(gap="inner", amount=10, scope="all")
    assert fake.last_command == "gaps inner all set 10"


async def test_zero_is_a_valid_amount(fake):
    result = json.loads(await i3_gaps(gap="inner", amount=0))
    assert result["success"] is True
    assert fake.last_command == "gaps inner current set 0"


async def test_plus_operation(fake):
    await i3_gaps(gap="outer", operation="plus", amount=5)
    assert fake.last_command == "gaps outer current plus 5"


async def test_minus_operation(fake):
    await i3_gaps(gap="outer", operation="minus", amount=3)
    assert fake.last_command == "gaps outer current minus 3"


async def test_toggle_operation(fake):
    await i3_gaps(gap="inner", operation="toggle", amount=10)
    assert fake.last_command == "gaps inner current toggle 10"


async def test_edge_specific_gaps(fake):
    await i3_gaps(gap="top", amount=20)
    assert fake.last_command == "gaps top current set 20"


async def test_no_attribute_error_on_literal_fields(fake):
    """Regression: the old code called .value on a Literal, which is a plain str."""
    result = json.loads(await i3_gaps(gap="inner", operation="plus", amount=5))
    assert result["success"] is True
