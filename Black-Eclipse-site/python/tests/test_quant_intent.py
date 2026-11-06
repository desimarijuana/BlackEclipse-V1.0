"""The deterministic quant-intent classifier and per-turn protocol.

The classifier is intentionally conservative: a plain quote/news/filing lookup
and a concept explanation must stay `none`, while a forecast, backtest, model or
factor request gets the right tier. A trade turn always keeps the trade surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from harness.quant_intent import (
    apply_intent_surfaces,
    apply_quant_context,
    apply_quant_surface,
    classify_quant_intent,
    evaluate_quant_outcome,
    quant_intent_block,
)


@pytest.mark.parametrize(
    ("query", "tier", "kind"),
    [
        ("forecast gold for tomorrow", "standard", "forecast"),
        ("will gold rise tomorrow", "standard", "forecast"),
        ("what will gold do next week", "standard", "forecast"),
        ("calculate gold's 20-day volatility", "light", "risk"),
        ("compute the drawdown of my portfolio", "light", "risk"),
        ("run a monte carlo on my portfolio", "standard", "analysis"),
        ("backtest my 20/50 moving average strategy", "deep", "strategy"),
        ("design a momentum strategy for gold", "deep", "strategy"),
        ("build me a quant model", "deep", "model"),
        ("train a model to predict gold", "deep", "model"),
        ("create a factor model for the market", "deep", "factor"),
        ("build a DCF for Newmont", "deep", "financial_model"),
        ("run a walk-forward test on my strategy", "deep", "strategy"),
        ("optimize my strategy parameters", "deep", "strategy"),
    ],
)
def test_quant_tiers(query: str, tier: str, kind: str) -> None:
    intent = classify_quant_intent(query)
    assert intent.tier == tier, (query, intent.to_dict())
    assert intent.kind == kind, (query, intent.to_dict())


@pytest.mark.parametrize(
    "query",
    [
        "what is the price of gold",
        "gold quote",
        "gold news today",
        "summarize this 10-K",
        "explain the sharpe ratio",
        "what is a moving average",
        "how does a backtest work",
        "show me the latest AAPL earnings",
        "write alpha.py that prints ALPHA_OK",
        "Build a small package: write alpha.py and beta.py, run both, then write report.txt",
        "create model.py with a helper function",
    ],
)
def test_lookups_and_explanations_stay_none(query: str) -> None:
    assert classify_quant_intent(query).tier == "none", query


@pytest.mark.parametrize(
    "query",
    ["act as a quant trader", "be quantitative about this", "use quantitative methods"],
)
def test_explicit_quant_framing_gets_the_protocol(query: str) -> None:
    intent = classify_quant_intent(query)
    assert intent.tier == "standard", query
    assert "explicit quantitative framing" in intent.reasons


def test_trade_execution_wins() -> None:
    intent = classify_quant_intent("buy 0.01 lot XAUUSD")
    assert intent.tier == "none"
    assert intent.kind == "trade"
    assert "trade-intent" in intent.signals


def test_explicit_off_wins() -> None:
    intent = classify_quant_intent("build me a quant model", mode="off")
    assert intent.tier == "none"


def test_explicit_on_forces_standard_for_a_plain_ask() -> None:
    intent = classify_quant_intent("look at gold", mode="on")
    assert intent.tier == "standard"


def test_short_follow_up_inherits_the_prior_quant_tier() -> None:
    history = [
        {"role": "user", "content": "forecast gold for tomorrow"},
        {"role": "assistant", "content": "Here is a distribution."},
    ]
    intent = classify_quant_intent("do it", history)
    assert intent.tier == "standard"
    assert intent.kind == "forecast"
    assert "follow-up" in intent.signals


def test_follow_up_does_not_inherit_from_a_lookup() -> None:
    history = [
        {"role": "user", "content": "what is the price of gold"},
        {"role": "assistant", "content": "4025."},
    ]
    assert classify_quant_intent("do it", history).tier == "none"


def test_missing_inputs_are_named_for_a_vague_forecast() -> None:
    intent = classify_quant_intent("make a forecast")
    assert intent.tier == "standard"
    assert "instrument or universe" in intent.missing
    assert "horizon" in intent.missing


def test_block_is_empty_for_none() -> None:
    assert quant_intent_block(classify_quant_intent("gold price")) == ""


def test_standard_block_has_the_research_steps() -> None:
    block = quant_intent_block(classify_quant_intent("forecast gold for tomorrow"))
    assert "Quant protocol" in block
    assert "out-of-sample" in block
    assert "Never invent a metric" in block
    assert "No guaranteed return" in block


def test_deep_block_names_the_synthesis_ladder() -> None:
    block = quant_intent_block(classify_quant_intent("build me a quant model"))
    assert "Model synthesis" in block
    assert "not a closed list" in block
    assert "reusable capability" in block
    assert "Never " in block and "self-enable" in block


def test_block_omits_a_tool_line_when_the_tool_is_not_bound() -> None:
    intent = classify_quant_intent("build me a quant model")
    without = quant_intent_block(intent, available={"analysis_run"})
    with_plan = quant_intent_block(
        intent, available={"analysis_run", "create_research_plan"}
    )
    assert "research plan" not in without
    assert "research plan" in with_plan


def test_plan_record_is_json_safe() -> None:
    record = classify_quant_intent("forecast gold for tomorrow").to_dict()
    assert record["tier"] == "standard"
    assert record["kind"] == "forecast"
    assert isinstance(record["signals"], list)
    assert isinstance(record["missing"], list)


class _Emitter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def emit(self, name: str, payload: dict) -> None:
        self.events.append((name, payload))


def _request(query: str, *, mode: str | None = None):
    context = {"quantMode": mode} if mode is not None else None
    return SimpleNamespace(
        input=SimpleNamespace(query=query, context=context, history=None)
    )


@pytest.mark.asyncio
async def test_apply_quant_context_appends_the_block_and_emits_the_plan() -> None:
    emitter = _Emitter()
    out = await apply_quant_context(
        _request("forecast gold for tomorrow"), {"analysis_run"}, "base", emitter
    )
    assert "Quant protocol" in out
    assert out.startswith("base")
    assert emitter.events[0][0] == "quant.plan"
    assert emitter.events[0][1]["kind"] == "forecast"


@pytest.mark.asyncio
async def test_apply_quant_context_respects_off_and_never_raises() -> None:
    emitter = _Emitter()
    out = await apply_quant_context(
        _request("forecast gold for tomorrow", mode="off"), {"analysis_run"}, "base", emitter
    )
    assert out == "base"
    assert emitter.events == []

    broken = SimpleNamespace(input=SimpleNamespace(query="x", context=None))
    assert await apply_quant_context(broken, None, "base", emitter) == "base"


@dataclass(frozen=True)
class _Resolution:
    allowed: frozenset[str]
    boundTools: int


def _resolution(allowed: set[str]) -> _Resolution:
    return _Resolution(frozenset(allowed), len(allowed))


def test_quant_surface_keeps_data_compute_and_artifacts() -> None:
    allowed = {
        "get_historical_prices", "analysis_run", "run_backtest",
        "create_strategy", "market_get_quote", "broker_bars", "python_chart",
        "eclipse_report", "clarify", "ui_get_application_map", "video_render",
        "shell_run", "order_submit",
    }
    kept, resolution = apply_quant_surface(
        "forecast gold for tomorrow", allowed, _resolution(allowed)
    )
    assert "get_historical_prices" in kept
    assert "analysis_run" in kept
    assert "run_backtest" in kept
    assert "broker_bars" in kept
    assert "python_chart" in kept
    assert "ui_get_application_map" not in kept
    assert "video_render" not in kept
    assert "shell_run" not in kept
    assert "order_submit" not in kept
    assert len(kept) < len(allowed)
    assert resolution.boundTools == len(kept)


def test_quant_surface_leaves_a_lookup_untouched() -> None:
    allowed = {"get_historical_prices", "analysis_run", "ui_get_application_map"}
    kept, resolution = apply_quant_surface(
        "what is the price of gold", allowed, _resolution(allowed)
    )
    assert kept == allowed
    assert resolution.boundTools == len(allowed)


def test_quant_surface_never_widens_and_skips_a_tiny_surface() -> None:
    allowed = {"ui_get_application_map", "video_render"}
    kept, resolution = apply_quant_surface(
        "build me a quant model", allowed, _resolution(allowed)
    )
    assert kept == allowed
    assert resolution.boundTools == len(allowed)


def test_trade_precedence_precedes_the_quant_surface() -> None:
    allowed = {
        "order_submit", "broker_bars", "broker_quote", "analysis_run",
        "ui_get_application_map", "video_render",
    }
    request = SimpleNamespace(
        input=SimpleNamespace(
            query="buy 0.01 lot XAUUSD", history=None, context=None,
        )
    )
    kept, _ = apply_intent_surfaces(request, allowed, _resolution(allowed))
    assert "order_submit" in kept
    assert "ui_get_application_map" not in kept
    assert "video_render" not in kept


def test_quant_outcome_light_requires_a_computation() -> None:
    plan = {"tier": "light", "kind": "risk"}
    complete = evaluate_quant_outcome(plan, ["analysis_run"], "Volatility 18.2%")
    assert complete is not None and complete["complete"]
    incomplete = evaluate_quant_outcome(plan, ["get_historical_prices"], "18.2%")
    assert incomplete is not None and not incomplete["complete"]
    assert "a tool-backed computation" in incomplete["missing"]


def test_quant_outcome_standard_requires_a_named_artifact() -> None:
    plan = {"tier": "standard", "kind": "forecast"}
    result = evaluate_quant_outcome(plan, ["analysis_run"], "median 4025")
    assert result is not None and not result["complete"]
    assert "a named artifact" in result["missing"]

    complete = evaluate_quant_outcome(
        plan, ["analysis_run"], "Chart and experiment exp_abcd1234 attached."
    )
    assert complete is not None and complete["complete"]


def test_quant_outcome_deep_requires_validation_and_costs() -> None:
    plan = {"tier": "deep", "kind": "strategy"}
    tools = ["run_backtest", "run_walk_forward", "run_robustness_analysis"]
    missing = evaluate_quant_outcome(plan, tools, "Experiment exp_abcd1234.")
    assert missing is not None and not missing["complete"]
    assert "out-of-sample evidence" in missing["missing"]
    assert "cost evidence" in missing["missing"]

    complete = evaluate_quant_outcome(
        plan, tools,
        "Experiment exp_abcd1234. Walk-forward out-of-sample Sharpe 1.2 after "
        "commission and slippage.",
    )
    assert complete is not None and complete["complete"]
