"""W2: anchor-driven budget gates."""

from __future__ import annotations

from types import SimpleNamespace

from harness.context_budget import compute_history_budget


def _budget(anchor=None, *, window=10_000):
    return compute_history_budget(
        provider="openai", model="gpt-4o", system_prompt="s",
        user_turn="u", absolute_max_turns=20, absolute_max_chars=40_000,
        window_override=window, anchor=anchor, history_chars=0,
    )


def test_anchor_pressure_and_gate():
    anchor = SimpleNamespace(
        anchored=True, model_key="openai/gpt-4o",
        prompt_tokens=6_000, estimated_used=lambda history_chars: 6_000,
    )
    budget = _budget(anchor)
    assert budget.anchor_anchored is True
    assert budget.anchor_used_tokens == 6_000
    assert budget.pressure == 0.6
    assert budget.gate == "soft"


def test_anchor_emergency_gate():
    anchor = SimpleNamespace(
        anchored=True, model_key="openai/gpt-4o",
        prompt_tokens=9_000, estimated_used=lambda history_chars: 9_000,
    )
    assert _budget(anchor).gate == "emergency"


def test_unknown_window_stays_inert():
    budget = compute_history_budget(
        provider="custom", model="totally-unknown-model", system_prompt="s",
        user_turn="u", absolute_max_turns=20, absolute_max_chars=40_000,
        window_override=None,
    )
    assert budget.effective is False
    assert budget.gate == "unknown"
    assert budget.pressure is None
