"""The Bookkeeper preset: a closed ledger-only surface and a disciplined prompt.

The preset is the delivery half of the ledger work: an agent that can DO the
bookkeeping has to be one whose tool surface is the ledger and nothing else, and
whose instructions refuse to invent a number, a category or a tax rate.
"""

from __future__ import annotations

from harness.agents import AGENT_PRESETS, BOOKKEEPER, get_agent
from harness.ledger.tools import LEDGER_READ_TOOLS, LEDGER_TOOLS


def test_the_bookkeeper_is_registered_and_resolvable():
    assert "bookkeeper" in AGENT_PRESETS
    assert get_agent("bookkeeper").id == "bookkeeper"
    assert BOOKKEEPER.name == "Bookkeeper"


def test_the_allowlist_is_the_ledger_family_and_nothing_else():
    assert set(BOOKKEEPER.tools) == set(LEDGER_TOOLS)
    # Every read tool is present; a closed allowlist that dropped one would make
    # the preset unable to answer its own questions.
    assert set(LEDGER_READ_TOOLS).issubset(set(BOOKKEEPER.tools))
    # It must not inherit the operator's MCP reach, and it names no finance tool.
    assert getattr(BOOKKEEPER, "allowMcpTools", False) is False
    assert not any(name.startswith(("portfolio_", "market_", "get_quote"))
                   for name in BOOKKEEPER.tools)


def test_the_prompt_states_the_non_negotiables():
    prompt = BOOKKEEPER.systemPrompt
    for phrase in (
        "NEVER invent a number",
        "balances exactly",
        "suspense",
        "tax rate",
        "RECONCILED",
        "reversing entries",
    ):
        assert phrase in prompt, phrase


def test_the_prompt_does_not_promise_tools_it_lacks():
    prompt = BOOKKEEPER.systemPrompt.lower()
    # It explicitly says it has no market/coding/browser/MCP tools.
    assert "no market-data" in prompt
    assert "mcp" in prompt


def test_the_step_bound_is_small_enough_to_be_predictable():
    assert 1 <= BOOKKEEPER.maxSteps <= 20
