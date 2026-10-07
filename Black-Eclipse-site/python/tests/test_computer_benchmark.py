"""Eclipse CUA Benchmark — deterministic, offline capability measurement.

Measures the dimensions the design calls for over the SAME fake driver the tool
tests use, so it is fast, deterministic and CI-safe:

  * task completion rate (a read → find → act → verify flow)
  * action accuracy / element grounding accuracy
  * verification accuracy
  * recovery success
  * false-action rate and dangerous-action rate (the finance priority)

For finance, false-action rate is weighted ABOVE raw completion.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

import pytest

from harness.computer.core import ComputerCore
from harness.computer.errors import ComputerError, PolicyBlocked
from harness.computer.finance.firewall import ASSISTED, READ_ONLY, FinanceActionFirewall
from harness.computer.grounding.matching import GroundingQuery
from harness.computer.policy import ALLOW, default_policy

from tests.test_computer_safety import _FakeDriver, _permissive_policy, _session


@dataclass
class BenchmarkResult:
    measured: dict[str, float] = field(default_factory=dict)

    def report(self) -> str:
        return "\n".join(f"  {k}: {v:.3f}" for k, v in sorted(self.measured.items()))


async def _benchmark() -> BenchmarkResult:
    result = BenchmarkResult()

    # ── Grounding accuracy: rank a query against a known control set. ────────
    session, _ = _session(fake=_FakeDriver(), policy=_permissive_policy())
    await session.observe()
    cases = [("Save", "Save"), ("Save As", "Save As"), ("Cancel", "Cancel"),
             ("Ticker", "Ticker"), ("Submit Order", "Submit Order")]
    hits = 0
    for needle, expected in cases:
        try:
            target = session.ground(GroundingQuery(name=needle))
            if target.name == expected:
                hits += 1
        except ComputerError:
            pass
    result.measured["grounding_accuracy"] = hits / len(cases)

    # ── Verification accuracy: a real semantic change is verified; a no-op is not. ──
    from harness.computer.drivers.base import ScreenFrame
    from harness.computer.models import Bounds
    from harness.computer.verification.verifier import ActionVerifier, ObservationState
    from PIL import Image

    verifier = ActionVerifier()
    img = ScreenFrame(data=Image.new("RGB", (80, 80)), width=80, height=80, bounds=Bounds(0, 0, 80, 80))
    before = ObservationState(window_id="1", ax_digest="a", frame=img)
    verified = verifier.verify(before, ObservationState(window_id="1", ax_digest="b", frame=img), action="click").status
    uncertain = verifier.verify(before, ObservationState(window_id="1", ax_digest="a"), action="click").status
    result.measured["verification_accuracy"] = (1.0 if verified == "verified" else 0.0) / 2 + (
        1.0 if uncertain == "uncertain" else 0.0) / 2

    # ── Recovery success: the ladder recovers a target-not-found. ────────────
    from harness.computer.recovery import RecoveryEngine

    engine = RecoveryEngine(max_attempts=3)

    async def handler(strategy: str):
        return (strategy == "reground", "ok")

    recovered = await engine.execute("TARGET_NOT_FOUND", {s: handler for s in (
        "reground", "try_ocr", "replan")})
    result.measured["recovery_success"] = 1.0 if recovered.recovered else 0.0

    # ── Finance: false-action and dangerous-action rates (the priority). ─────
    # A battery of intents; count how many a mutation is allowed where it must not
    # be, over READ_ONLY (must block all) and the absolute-block verbs (never).
    intents = [
        {"action": "buy", "instrument": "NVDA", "quantity": 1, "price": 100},
        {"action": "sell", "instrument": "NVDA", "quantity": 1, "price": 100},
        {"action": "submit_order", "instrument": "NVDA", "quantity": 1, "price": 100},
        {"action": "cancel_order", "instrument": "NVDA"},
        {"action": "modify_order", "instrument": "NVDA"},
        {"action": "transfer"},
        {"action": "withdraw"},
        {"action": "deposit"},
        {"action": "payment"},
    ]
    ro = FinanceActionFirewall(mode=READ_ONLY)
    false_actions = sum(1 for i in intents if ro.evaluate(i).allowed)
    result.measured["false_action_rate_read_only"] = false_actions / len(intents)
    absolute = FinanceActionFirewall(mode="autonomous")
    dangerous = sum(1 for i in intents if i["action"] in ("transfer", "withdraw", "deposit", "payment") and absolute.evaluate(i).allowed)
    result.measured["dangerous_action_rate"] = dangerous / 4

    # ── Task completion: a full read → act → verify flow. ─────────────────────
    session2, driver = _session(fake=_FakeDriver(), policy=_permissive_policy(), verification=True)
    await session2.observe()
    core = ComputerCore(session2, config=session2._config)
    snap = session2.latest_snapshot
    el = next((e for e in snap.elements if e.name == "Submit Order"), None)
    completed = 0
    if el is not None:
        res = await core.act("click", element=el.ref, snapshot_id=snap.snapshot_id)
        # completion = the action ran AND was verified (not a blind success)
        if res.success and (res.verification or {}).get("status") == "verified":
            completed = 1
    result.measured["task_completion_rate"] = float(completed)

    # ── A no-op action must never be counted as a false success. ─────────────
    session3, _ = _session(fake=_FakeDriver(), policy=_permissive_policy(), verification=True)
    await session3.observe()
    core3 = ComputerCore(session3, config=session3._config)
    snap3 = session3.latest_snapshot
    noop = await core3.act("click", target="__absent__", snapshot_id=snap3.snapshot_id,
                           allow_coordinates=True, coordinates=[500, 380])
    result.measured["noop_false_success_rate"] = 1.0 if (noop.success and noop.verdict == "success") else 0.0
    return result


@pytest.mark.asyncio
async def test_cua_benchmark_meets_the_production_bar():
    result = await _benchmark()
    report = result.report()
    print("\n[Eclipse CUA Benchmark]\n" + report)
    m = result.measured
    # The bar: perfect grounding on the fixture, correct verification, full
    # recovery, ZERO false/dangerous finance actions.
    assert m["grounding_accuracy"] >= 0.99, report
    assert m["verification_accuracy"] >= 0.99, report
    assert m["recovery_success"] >= 0.99, report
    assert m["false_action_rate_read_only"] == 0.0, report
    assert m["dangerous_action_rate"] == 0.0, report
    assert m["noop_false_success_rate"] == 0.0, report
    assert m["task_completion_rate"] >= 0.99, report
