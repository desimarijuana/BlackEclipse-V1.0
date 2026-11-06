"""The chat contract for a quantitative turn.

These are deterministic fixtures: they check what the per-run protocol REQUIRES
the model to do in chat (catalog-first reuse, the artifact line, clarification,
validation), not what a live model happens to say. No UI surface is involved.
"""

from __future__ import annotations

from types import SimpleNamespace

from harness.quant_intent import (
    classify_quant_intent,
    finalize_quant_text,
    is_deep_quant_turn,
    quant_intent_block,
)

_TOOLS = {
    "analysis_run", "model_catalog", "create_research_plan",
    "run_backtest", "run_walk_forward", "run_robustness_analysis",
    "python_chart", "eclipse_report", "clarify",
}


def _block(query: str) -> str:
    return quant_intent_block(classify_quant_intent(query), available=_TOOLS)


def test_standard_turn_requires_the_chat_artifact_line() -> None:
    block = _block("forecast gold for tomorrow")
    assert "Artifacts: <comma-separated ids>" in block
    assert "Artifacts: none —" in block
    assert "Chat is the only delivery surface" in block


def test_deep_build_requires_catalog_first_and_reuse() -> None:
    block = _block("build me a quant model for gold")
    assert "call `model_catalog` FIRST" in block
    assert "reuse it" in block
    assert "do not rebuild a duplicate" in block
    assert "Artifacts:" in block


def test_deep_build_asks_one_clarify_for_an_ambiguous_model_family() -> None:
    block = _block("build me a model for gold")
    assert "ask ONE clarify question" in block
    assert "valuation/DCF" in block
    assert "ML prediction" in block
    assert "trading strategy" in block
    assert "risk model" in block


def test_reuse_request_is_a_standard_quant_turn() -> None:
    intent = classify_quant_intent("reuse the model from last week")
    assert intent.tier == "standard"
    assert intent.kind == "model"
    assert "model_catalog" in _block("reuse the model from last week")


def test_catalog_question_is_not_treated_as_a_concept_definition() -> None:
    intent = classify_quant_intent("what models do we have")
    assert intent.tier == "standard"
    assert intent.kind == "model"


def test_deep_strategy_requires_validation_and_costs() -> None:
    block = _block("build a gold momentum strategy")
    assert "out-of-sample" in block
    assert "costs always" in block
    assert "Artifacts:" in block


def test_deep_synthesis_ladder_is_still_available() -> None:
    block = _block("build a gold momentum strategy")
    assert "reusable capability" in block
    assert "hand off new code/tools" in block
    assert "connect an external system" in block


def test_gold_basis_is_required_in_chat() -> None:
    block = _block("forecast gold for tomorrow")
    assert "spot XAUUSD" in block
    assert "GC=F futures" in block
    assert "never mix them" in block


def _message(tool: str) -> SimpleNamespace:
    return SimpleNamespace(tool_calls=[{"name": tool}], type="ai", name=None)


def test_finalize_adds_an_artifact_line_when_the_answer_omitted_it() -> None:
    text = finalize_quant_text(
        "forecast gold for tomorrow", None, [_message("analysis_run")],
        "Median 4025; a 90% band is 3980–4070.",
    )
    assert "Artifacts: none — no artifact id was named" in text
    assert text.startswith("Median 4025")


def test_finalize_names_an_artifact_that_was_mentioned_in_prose() -> None:
    text = finalize_quant_text(
        "build a gold momentum strategy", None,
        [_message("run_backtest"), _message("run_walk_forward")],
        "Experiment exp_abcd1234. Walk-forward out-of-sample Sharpe 1.2 after "
        "commission and slippage.",
    )
    assert "Artifacts: exp_abcd1234 (Eclipse check)." in text


def test_finalize_is_a_no_op_on_a_complete_answer_or_a_lookup() -> None:
    complete = (
        "Median 4025. Artifacts: none — no artifact id was named.\n\n"
        "Eclipse check: still missing a named artifact."
    )
    assert finalize_quant_text(
        "forecast gold for tomorrow", None, [_message("analysis_run")], complete
    ) == complete
    assert finalize_quant_text(
        "what is the price of gold", None, [], "4025."
    ) == "4025."


def test_deep_quant_gets_the_larger_budget_flag() -> None:
    assert is_deep_quant_turn("build a gold momentum strategy") is True
    assert is_deep_quant_turn("forecast gold for tomorrow") is False
    assert is_deep_quant_turn("what is the price of gold") is False


def test_the_offline_eval_gate_passes() -> None:
    from harness.eval_gates.quant_contract import run_gate

    run_gate()
