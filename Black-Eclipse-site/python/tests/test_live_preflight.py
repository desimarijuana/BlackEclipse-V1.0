"""The live lane refuses a dead environment instead of measuring it.

Before the preflight, a front door that was not listening produced twelve failed
trials and ~179 `ConnectError` lines, and the resulting `task_success: 0.0`
looked like a property of the agent. The lane now spends one cheap capability
first and reports a reason.
"""

from __future__ import annotations

import pytest

from harness.evaluation import live_gate


@pytest.mark.asyncio
async def test_a_dead_bridge_is_a_reason_not_a_score(monkeypatch):
    class Dead:
        async def fetch(self, capability, params):
            return {"status": "UNAVAILABLE", "error": "ConnectError: refused"}

    monkeypatch.setattr("harness.bridge.HttpDataBridge", lambda *a, **k: Dead())
    reason = await live_gate.preflight_bridge()
    assert "answered UNAVAILABLE" in reason
    assert "npm run up" in reason


@pytest.mark.asyncio
async def test_a_healthy_bridge_has_no_reason(monkeypatch):
    class Healthy:
        async def fetch(self, capability, params):
            return {"status": "OK", "price": {"price": 1.0}}

    monkeypatch.setattr("harness.bridge.HttpDataBridge", lambda *a, **k: Healthy())
    assert await live_gate.preflight_bridge() == ""


def test_a_two_sample_rate_is_not_published():
    from harness.evaluation.runner import MIN_SAMPLES_FOR_RATE

    # The rule the persistence layer applies: below this, the value becomes None.
    assert MIN_SAMPLES_FOR_RATE >= 5
