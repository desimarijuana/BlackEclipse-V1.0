"""The Intelligent Response Orchestrator — the deterministic response-mode planner.

The planner decides HOW a turn should be presented, so a wrong mode is the risky
piece and the labelled cases come first. The bias is explicit: an ambiguous or
simple turn is `text`, because a forced widget is a worse failure than plain
prose. Pure and model-free — every case below is deterministic.
"""

from __future__ import annotations

import asyncio
import dataclasses
import types

import pytest

from harness import models, response_mode_llm
from harness.response_mode import (
    ResponsePlan,
    classify_response_mode,
    parse_mode_reply,
    plan_for_mode,
    response_mode_prompt_block,
)
from harness.response_mode_llm import orchestrate_response_mode, refine_with_model
from harness.schemas import ModelSettings


def _settings() -> ModelSettings:
    return ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1")


class _FakeModel:
    """A minimal chat model whose only method is `ainvoke`."""

    def __init__(self, reply: str) -> None:
        self._reply = reply

    async def ainvoke(self, _messages):  # noqa: ANN001
        return types.SimpleNamespace(content=self._reply)


# ── the labelled set from the blueprint's decision table ────────────────────


@pytest.mark.parametrize(
    ("query", "mode"),
    [
        ("Explain RSI", "explanation"),
        ("How does RSI work", "explanation"),
        ("Teach me Python", "explanation"),
        ("Compare BTC and ETH", "visualization"),
        ("Chart the 90-day returns of NVDA", "visualization"),
        ("Backtest my strategy", "simulation"),
        ("What if I change the stop loss to 2%", "simulation"),
        ("Why did my agent fail?", "workflow"),
        ("Show the workflow for this research plan", "workflow"),
        ("Hi Eclipse", "text"),
        ("Thanks!", "text"),
        ("what is the price of AAPL", "text"),
    ],
)
def test_labelled_modes(query: str, mode: str) -> None:
    plan = classify_response_mode(query)
    assert plan.mode == mode, (query, plan)


# ── composite: two rich modes genuinely co-occur ───────────────────────────


def test_explain_and_show_is_composite() -> None:
    plan = classify_response_mode("Compare BTC and ETH and explain the difference")
    assert plan.mode == "composite"
    assert "mode:visualization" in plan.signals
    assert "mode:explanation" in plan.signals


def test_explain_and_simulate_is_composite() -> None:
    plan = classify_response_mode(
        "Explain my EMA strategy and show how it changes if I change the stop loss"
    )
    assert plan.mode == "composite"


def test_a_single_data_mode_is_not_composite() -> None:
    assert classify_response_mode("Compare BTC and ETH").mode == "visualization"


# ── text is the safe default ────────────────────────────────────────────────


@pytest.mark.parametrize("query", ["", "   ", "ok", "hey there", "cool"])
def test_trivial_turns_are_text(query: str) -> None:
    plan = classify_response_mode(query)
    assert plan.mode == "text"
    assert plan.confidence == "certain"


def test_ambiguous_turn_defaults_to_text_with_low_confidence() -> None:
    plan = classify_response_mode("tell me something interesting about the market")
    assert plan.mode == "text"
    assert plan.confidence == "unsure"


def test_plain_mode_carries_no_suggested_blocks() -> None:
    assert classify_response_mode("hi").suggested_blocks == ()


# ── learning refinement ─────────────────────────────────────────────────────


def test_learning_explanation_suggests_a_learning_map() -> None:
    plan = classify_response_mode("teach me Python")
    assert plan.mode == "explanation"
    assert plan.learning is True
    assert "learning_map" in plan.suggested_blocks


def test_a_plain_explanation_is_not_learning() -> None:
    plan = classify_response_mode("explain RSI")
    assert plan.learning is False
    assert "learning_map" not in plan.suggested_blocks


# ── follow-up inheritance ───────────────────────────────────────────────────


def test_follow_up_inherits_the_previous_mode() -> None:
    history = [
        {"role": "user", "content": "compare BTC and ETH"},
        {"role": "assistant", "content": "Here is the comparison..."},
    ]
    plan = classify_response_mode("do it", history=history)
    assert plan.mode == "visualization"
    assert "follow_up" in plan.signals


def test_follow_up_after_a_plain_turn_stays_text() -> None:
    history = [{"role": "user", "content": "what is the price of AAPL"}]
    plan = classify_response_mode("do it", history=history)
    assert plan.mode == "text"


def test_follow_up_chain_is_bounded() -> None:
    # An all-follow-up history must terminate, not recurse forever.
    history = [{"role": "user", "content": "do it"}]
    plan = classify_response_mode("continue", history=history)
    assert plan.mode == "text"


# ── history may be objects (schemas.ConversationTurn), not only dicts ───────


def test_history_accepts_object_turns() -> None:
    @dataclasses.dataclass
    class Turn:
        role: str
        content: str

    history = [Turn("user", "backtest my strategy")]
    plan = classify_response_mode("do it", history=history)
    assert plan.mode == "simulation"


# ── the prompt directive ────────────────────────────────────────────────────


def test_prompt_block_names_the_mode_and_stays_bounded() -> None:
    block = response_mode_prompt_block(classify_response_mode("Explain RSI"))
    assert "Mode: explanation" in block
    assert "not a mandate" in block
    assert "never fabricate" in block.lower()


def test_prompt_block_lists_suggested_blocks_for_rich_modes() -> None:
    block = response_mode_prompt_block(classify_response_mode("Backtest my strategy"))
    assert "Suggested blocks:" in block
    assert "controls" in block


def test_plan_is_json_safe() -> None:
    payload = classify_response_mode("compare BTC and ETH").to_dict()
    assert set(payload) == {
        "mode", "confidence", "reason", "signals", "suggestedBlocks", "learning",
    }
    assert isinstance(payload["signals"], list)
    assert isinstance(payload["suggestedBlocks"], list)


def test_classifier_is_total_on_odd_input() -> None:
    plan: ResponsePlan = classify_response_mode("```json\n{{{\n```")
    assert plan.mode == "text"


# ── the model-assisted fallback (pure parts) ────────────────────────────────


@pytest.mark.parametrize(
    ("reply", "mode"),
    [
        ("visualization", "visualization"),
        ("  VISUALIZATION.  ", "visualization"),
        ("I would choose explanation", "explanation"),
        ("chart", "visualization"),
        ("a simulated scenario", "simulation"),
        ("composite", "composite"),
        ("", None),
        ("no idea", None),
    ],
)
def test_parse_mode_reply(reply: str, mode: str | None) -> None:
    assert parse_mode_reply(reply) == mode


def test_orchestrator_is_deterministic_when_disabled(monkeypatch) -> None:
    monkeypatch.delenv("HARNESS_RESPONSE_MODE_MODEL", raising=False)
    plan = asyncio.run(
        orchestrate_response_mode("tell me something interesting", None, _settings())
    )
    assert plan.mode == "text"
    assert plan.confidence == "unsure"
    assert "mode:model" not in plan.signals


def test_orchestrator_skips_the_model_for_a_confident_plan(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_RESPONSE_MODE_MODEL", "1")

    async def _boom(*_a, **_k):  # pragma: no cover - must not be called
        raise AssertionError("refine must not run for a confident plan")

    monkeypatch.setattr(response_mode_llm, "refine_with_model", _boom)
    plan = asyncio.run(orchestrate_response_mode("compare BTC and ETH", None, _settings()))
    assert plan.mode == "visualization"


def test_orchestrator_uses_the_model_on_unsure(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_RESPONSE_MODE_MODEL", "1")
    calls: list[str] = []

    async def _refine(query, base, settings, **_k):
        calls.append(query)
        return plan_for_mode("visualization", "likely", "model", ("mode:model",))

    monkeypatch.setattr(response_mode_llm, "refine_with_model", _refine)
    plan = asyncio.run(
        orchestrate_response_mode("tell me something interesting", None, _settings())
    )
    assert calls == ["tell me something interesting"]
    assert plan.mode == "visualization"
    assert "mode:model" in plan.signals


def test_refine_with_model_parses_the_reply(monkeypatch) -> None:
    monkeypatch.setattr(
        models, "build_chat_model", lambda _s: _FakeModel("explanation")
    )
    base = classify_response_mode("tell me something interesting")
    plan = asyncio.run(refine_with_model("tell me something interesting", base, _settings()))
    assert plan.mode == "explanation"
    assert plan.confidence == "likely"


def test_refine_with_model_returns_base_on_failure(monkeypatch) -> None:
    def _explode(_s):
        raise RuntimeError("no credentials")

    monkeypatch.setattr(models, "build_chat_model", _explode)
    base = classify_response_mode("tell me something interesting")
    plan = asyncio.run(refine_with_model("tell me something interesting", base, _settings()))
    assert plan is base
