"""Per-run cost: priced from the one registry, honestly unknown otherwise."""

from __future__ import annotations

from harness.run_cost import estimate_run_cost, with_cost


def test_known_model_cost_is_exact():
    cost = estimate_run_cost("openai", "gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost["priced"] is True
    assert cost["costUsd"] == 0.75  # 0.15 input + 0.60 output per 1M
    assert cost["currency"] == "USD"


def test_unknown_model_is_unknown_not_zero():
    cost = estimate_run_cost("custom", "totally-unknown-model", 1000, 1000)
    assert cost["priced"] is False
    assert cost["costUsd"] is None


def test_with_cost_does_not_mutate_the_run():
    run = {
        "provider": "openai", "model": "gpt-4o-mini",
        "promptTokens": 1_000_000, "completionTokens": 0,
    }
    out = with_cost(run)
    assert "cost" not in run
    assert out["cost"]["costUsd"] == 0.15
