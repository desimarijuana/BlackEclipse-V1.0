"""Per-run cost: priced from the one registry, honestly unknown otherwise."""

from __future__ import annotations

from harness.run_cost import estimate_run_cost, with_cost
from harness.model_runtime.store import ModelRuntimeStore
from harness.persistence import AgentMemoryStore
import os
import tempfile


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


def test_attempt_cost_sums_failures_and_fallbacks():
    directory = tempfile.mkdtemp(prefix="be-run-cost-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        model_store = ModelRuntimeStore(store)
        model_store.record_model_request({
            "requestId": "m1", "runId": "run_attempts", "provider": "openai",
            "model": "gpt-4o-mini", "success": True, "inputTokens": 100,
            "outputTokens": 50, "totalTokens": 150,
            "cost": {"totalCost": 0.25, "currency": "USD", "kind": "per_token"},
        })
        model_store.record_model_request({
            "requestId": "m2", "runId": "run_attempts", "provider": "openai",
            "model": "gpt-4o-mini", "success": True, "fallback": True,
            "inputTokens": 100, "outputTokens": 50, "totalTokens": 150,
            "cost": {"totalCost": 0.75, "currency": "USD", "kind": "per_token"},
        })
        cost = with_cost({"id": "run_attempts"}, store)["cost"]
        assert cost["source"] == "model_attempts"
        assert cost["attempts"] == 2
        assert cost["priced"] is True
        assert cost["costUsd"] == 1.0
        assert cost["totalTokens"] == 300
    finally:
        store.close()


def test_attempt_cost_is_unpriced_when_any_attempt_is_unpriced():
    directory = tempfile.mkdtemp(prefix="be-run-cost-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        model_store = ModelRuntimeStore(store)
        model_store.record_model_request({
            "requestId": "m1", "runId": "run_unpriced", "provider": "custom",
            "model": "unknown", "success": True, "totalTokens": 150,
        })
        cost = with_cost({"id": "run_unpriced"}, store)["cost"]
        assert cost["priced"] is False
        assert cost["costUsd"] is None
        assert cost["pricedAttempts"] == 0
    finally:
        store.close()
