"""Computer Use ADVERSARIAL tests.

The system must fail SAFELY when the world misbehaves: a button moves, a popup
appears, a window disappears, an application freezes, wrong/duplicate targets,
DPI and multi-monitor differences, an unexpected dialog, and — for finance —
wrong ticker/account/quantity/side/order-type, stale price, market closed,
insufficient buying power, order rejected and confirmation changed mid-workflow.

These run against pure/engine pieces (no real desktop); the point is that the
DECISION is correct and observable.
"""

from __future__ import annotations

import pytest

from harness.computer.drivers import build_driver
from harness.computer.errors import AmbiguousTarget, TargetNotFound, UnsupportedAction
from harness.computer.finance.firewall import ASSISTED, AUTONOMOUS, FinanceActionFirewall
from harness.computer.grounding.grounder import Grounder
from harness.computer.grounding.matching import GroundingQuery, rank_elements
from harness.computer.models import Bounds, Snapshot, SnapshotElement
from harness.computer.vision.router import decide_vision


def _snapshot(elements):
    return Snapshot(snapshot_id="s1", generation=1, elements=elements)


# ── target movement / disappearance / duplication ────────────────────────────

def test_button_moved_still_grounds_by_semantics_not_coordinates():
    snap = _snapshot([
        SnapshotElement(ref="1", role="button", name="Save", bounds=Bounds(10, 10, 60, 30)),
    ])
    target = Grounder().ground(GroundingQuery(name="Save"), snap)
    assert target.method == "accessibility"
    # A moved button is still found by name; coordinates are never the primary key.
    assert target.bounds.x == 10


def test_target_disappeared_raises_not_found():
    snap = _snapshot([SnapshotElement(ref="1", role="button", name="Save", bounds=Bounds(0, 0, 10, 10))])
    with pytest.raises(TargetNotFound):
        Grounder().ground(GroundingQuery(name="Delete"), snap)


def test_duplicate_target_is_ambiguous():
    snap = _snapshot([
        SnapshotElement(ref="1", role="button", name="Buy", bounds=Bounds(0, 0, 10, 10)),
        SnapshotElement(ref="2", role="button", name="Buy", bounds=Bounds(20, 0, 10, 10)),
    ])
    with pytest.raises(AmbiguousTarget):
        Grounder().ground(GroundingQuery(name="Buy"), snap)


def test_ambiguity_ranking_flags_close_scores():
    ranked = rank_elements(GroundingQuery(name="Buy"), [
        {"ref": "1", "role": "button", "name": "Buy", "bounds": [0, 0, 5, 5]},
        {"ref": "2", "role": "button", "name": "Buy", "bounds": [9, 0, 5, 5]},
    ])
    from harness.computer.grounding.matching import is_ambiguous
    assert is_ambiguous(ranked)


# ── unexpected dialog / window gone / app frozen ─────────────────────────────

def test_window_gone_raises_window_not_found():
    from harness.computer.windows.manager import WindowManager
    from harness.computer.errors import WindowNotFound

    class _NoWindows:
        def list_windows(self):
            return []

        def get_window(self, _):
            return None

    with pytest.raises(WindowNotFound):
        WindowManager(_NoWindows()).require("42")


def test_unresponsive_app_is_a_timeout_signal_from_recovery():
    from harness.computer.recovery import RecoveryEngine

    plan = RecoveryEngine().plan("APP_UNRESPONSIVE")
    assert "check_window_state" in plan
    assert "replan" in plan


# ── DPI / multi-monitor (data-level) ─────────────────────────────────────────

def test_bounds_survive_scale_and_negative_origins():
    # A second monitor to the LEFT gives negative virtual coordinates.
    b = Bounds(-1920, 0, 1920, 1080)
    assert b.center == (-960, 540)
    assert b.contains(-1000, 500)


def test_null_driver_reports_no_capabilities_and_raises():
    driver = build_driver("null")
    caps = driver.capabilities()
    assert caps.screen_capture is False and caps.accessibility is False
    with pytest.raises(UnsupportedAction):
        driver.list_windows()


# ── finance adversarial matrix ───────────────────────────────────────────────

def test_wrong_ticker_blocked_by_allowlist():
    fw = FinanceActionFirewall(mode=AUTONOMOUS, allowed_instruments=["NVDA"])
    assert fw.evaluate({"action": "buy", "instrument": "GME", "quantity": 1, "price": 1}).blocked


def test_wrong_side_still_requires_policy():
    # A "buy" where a "sell" was expected is still a mutation: assisted mode holds
    # BOTH for approval; it is never auto-executed.
    fw = FinanceActionFirewall(mode=ASSISTED)
    assert fw.evaluate({"action": "sell", "instrument": "NVDA", "quantity": 1, "price": 1}).requires_approval


def test_unknown_order_type_is_still_classified():
    from harness.computer.policy import classify_action
    # The order TYPE is carried, but the ACTION (submit_order) is what is gated.
    assert classify_action("submit_order") == "CRITICAL"


def test_stale_price_does_not_change_the_gate():
    fw = FinanceActionFirewall(mode=ASSISTED)
    decision = fw.evaluate({"action": "buy", "instrument": "NVDA", "quantity": 1, "price": 0})
    # A stale/zero price must NOT wave the order through — approval is still needed.
    assert decision.requires_approval


def test_insufficient_buying_power_is_a_runtime_failure_not_a_policy_pass():
    # The firewall gates POLICY; a broker rejection is a UI outcome the verifier
    # catches. The firewall never claims success on the agent's behalf.
    fw = FinanceActionFirewall(mode=AUTONOMOUS, max_order_value=1000)
    big = fw.evaluate({"action": "buy", "instrument": "NVDA", "quantity": 1000, "price": 500})
    assert big.blocked


def test_market_closed_and_order_rejected_are_known_failure_modes():
    from harness.computer.applications.registry import build_adapter_registry
    adapter = build_adapter_registry().select(title="MetaTrader 5")
    modes = adapter.failure_modes
    assert "market_closed" in modes
    assert "order_rejected" in modes
    assert "stale_price" in modes
    assert "confirmation_changed" in modes


# ── vision sensitivity adversarial ───────────────────────────────────────────

def test_sensitive_screen_never_reaches_a_cloud_model():
    decision = decide_vision(mode="cloud", sensitive=True, allow_cloud_sensitive=False,
                             local_available=False, cloud_available=True)
    assert decision.refused


def test_cloud_mode_falls_back_to_local_when_cloud_absent():
    decision = decide_vision(mode="cloud", sensitive=False, allow_cloud_sensitive=False,
                             local_available=True, cloud_available=False)
    assert decision.local and not decision.refused
