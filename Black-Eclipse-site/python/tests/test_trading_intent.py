"""The per-run trading directive for "analyze X and place a trade" turns.

The block is lexical and deterministic. It never grants a tool or a mandate; it
only tells the model to skip research and let `order_submit` resolve ids. A
refusal or a question must keep the directive out.
"""

from __future__ import annotations

from harness.trading_intent import (
    is_trade_turn,
    narrow_trade_surface,
    trading_intent_block as _trading_intent_block,
)


def test_analysis_plus_order_gets_the_directive():
    block = _trading_intent_block(
        "Analyze XAUUSD and place a small demo trade with a stop loss and take profit."
    )
    assert block.startswith("# Trading request")
    assert "order_preview" in block
    assert "do not ask the user for a connection id" in block.lower()
    assert "approval card" in block.lower()
    assert "do not call `order_submit`" in block.lower()


def test_explicit_order_without_a_symbol_also_gets_it():
    assert _trading_intent_block("Place a 0.01 lot order now")


def test_the_directive_names_the_approval_card_as_the_execution_path():
    """A pending card that the operator confirms fills the order (no mandate).

    The old directive said only `order_submit` fills, so a model that had just
    created the approval reported a real fill as a refusal.
    """
    block = _trading_intent_block("Place a 0.01 lot XAUUSD order")
    assert "submits this exact order" in block.lower()
    assert "needs no mandate" in block.lower()
    assert "order_ledger" in block


def test_plain_analysis_is_untouched():
    assert _trading_intent_block("Analyze XAUUSD and give me a technical read.") == ""


def test_refusal_wins_over_the_verb():
    assert _trading_intent_block(
        "Analyze XAUUSD. Do not place a trade, just give me the levels."
    ) == ""


def test_a_question_is_advice_not_execution():
    assert _trading_intent_block("Should I buy a small gold position here?") == ""


def test_empty_query_is_empty():
    assert _trading_intent_block("") == ""
    assert _trading_intent_block("   ") == ""


def test_close_request_gets_the_close_directive():
    block = _trading_intent_block("Close my gold trade, I want to step out.")
    assert block.startswith("# Close request")
    assert "position_close" in block
    assert "all: true" in block
    assert "order_submit" not in block


def test_exit_all_positions_gets_the_close_directive():
    assert _trading_intent_block("Exit all positions now").startswith("# Close request")


def test_close_refusal_is_not_directed():
    assert _trading_intent_block("Do not close my positions yet") == ""


def test_closing_an_ui_element_is_not_a_trade():
    assert _trading_intent_block("Close the settings dialog for me") == ""


def test_a_backtest_with_entry_exit_and_all_is_research_not_execution():
    """A rule's "entry"/"exit" and acceptance's "all" are not a close request.

    This misclassification narrowed the run to the 18-tool trade surface and
    hid get_historical_prices/analysis_run from a finance goal.
    """
    text = (
        "Backtest a long-only 20/10 Donchian breakout on MSFT. State the entry "
        "and exit rules precisely, apply 5 bps costs, split in-sample from "
        "out-of-sample, and report all acceptance criteria. Every number must "
        "come from a tool result."
    )
    assert _trading_intent_block(text) == ""
    assert is_trade_turn(text) is False


def test_modify_stop_gets_the_modify_directive():
    block = _trading_intent_block("Move my gold stop to breakeven")
    assert block.startswith("# Modify request")
    assert "position_modify" in block
    assert "widen" in block


def test_a_question_about_stops_is_not_directed():
    assert _trading_intent_block("Should I move my stop closer?") == ""


def test_trade_turn_detection_matches_the_directive():
    assert is_trade_turn("Analyze gold and place a small demo trade") is True
    assert is_trade_turn("Close all my trades") is True
    assert is_trade_turn("Analyze gold and give me a technical read") is False


def test_a_trade_turn_binds_only_the_trade_surface():
    allowed = {"order_submit", "order_preview", "broker_quote", "broker_bars",
               "shell_run", "code_edit", "response_block_schema"}
    narrowed = narrow_trade_surface(allowed)
    assert narrowed == {
        "order_submit", "order_preview", "broker_quote", "broker_bars",
        "response_block_schema",
    }


def test_a_non_trade_surface_is_left_untouched():
    allowed = {"broker_quote", "shell_run", "code_edit"}
    assert narrow_trade_surface(allowed) == allowed


def test_a_surface_without_an_effect_tool_is_untouched():
    allowed = {"broker_quote", "broker_bars", "response_block_schema"}
    assert narrow_trade_surface(allowed) == allowed
