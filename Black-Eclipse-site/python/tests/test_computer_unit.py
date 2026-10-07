"""Computer Use Engine unit tests — pure logic, no desktop required.

Covers: errors/verdicts, the action state machine, config resolution, the policy
engine + risk classification, key normalization, target grounding + stale
handles, verification, the recovery ladder, OCR field extraction, the finance
firewall, security detection, the vision router, takeover leases, replay and the
application adapters.
"""

from __future__ import annotations

import sys

import pytest

from harness.computer import errors as cua_errors
from harness.computer.actions.keymap import normalize_combo, virtual_key
from harness.computer.applications.adapters import ADAPTERS
from harness.computer.applications.registry import build_adapter_registry
from harness.computer.drivers import build_driver
from harness.computer.drivers.null import NullDriver
from harness.computer.finance.fields import canonical_field, extract_fields, parse_number
from harness.computer.finance.firewall import (
    ASSISTED,
    AUTONOMOUS,
    READ_ONLY,
    SIMULATION,
    FinanceActionFirewall,
)
from harness.computer.grounding.matching import GroundingQuery, is_ambiguous, rank_elements, score_element
from harness.computer.models import Bounds, Snapshot, SnapshotElement, Target
from harness.computer.policy import (
    ALLOW,
    ASK,
    DENY,
    ComputerPolicy,
    AppPolicy,
    classify_action,
    default_policy,
    is_financial_mutation,
)
from harness.computer.recovery import LADDER, RecoveryEngine
from harness.computer.security import SecurityLayer, is_sensitive_label, looks_sensitive
from harness.computer.state import ActionState, ActionStateMachine, InvalidTransition
from harness.computer.takeover import TakeoverManager
from harness.computer.vision.router import decide_vision
from harness.computer.replay import Replayer


# ── errors + verdicts ────────────────────────────────────────────────────────

def test_verdicts_are_the_closed_set():
    assert "success" in cua_errors.VERDICTS
    assert "recapture" in cua_errors.VERDICTS
    assert "foreground_required" in cua_errors.VERDICTS
    assert "blocked" in cua_errors.VERDICTS


def test_error_carries_code_verdict_and_to_dict():
    err = cua_errors.StaleElement("element moved", session_id="s1", target="7")
    assert err.code == "COMPUTER_STALE_ELEMENT"
    assert err.verdict == "recapture"
    payload = err.to_dict()
    assert payload["code"] == "COMPUTER_STALE_ELEMENT"
    assert payload["verdict"] == "recapture"
    assert payload["target"] == "7"


def test_approval_and_policy_verdicts():
    assert cua_errors.ApprovalRequired("x").verdict == "approval_required"
    assert cua_errors.PolicyBlocked("x").verdict == "blocked"
    assert cua_errors.TargetNotFound("x").verdict == "reground"
    assert cua_errors.HumanInterventionRequired("captcha").verdict == "ask_user"


# ── action state machine ─────────────────────────────────────────────────────

def test_state_machine_happy_path():
    m = ActionStateMachine()
    for target in (ActionState.OBSERVED, ActionState.TARGET_IDENTIFIED, ActionState.AUTHORIZED,
                   ActionState.ACTION_READY, ActionState.ACTION_EXECUTED, ActionState.VERIFYING,
                   ActionState.CONFIRMED):
        m.transition(target)
    assert m.state == ActionState.CONFIRMED
    assert m.state.terminal
    assert len(m.log) == 7


def test_state_machine_refuses_invalid_transition():
    m = ActionStateMachine()
    with pytest.raises(InvalidTransition):
        m.transition(ActionState.CONFIRMED)


def test_state_machine_failure_is_terminal():
    m = ActionStateMachine()
    m.transition(ActionState.OBSERVED)
    m.fail(ActionState.STALE_ELEMENT)
    assert m.state == ActionState.STALE_ELEMENT
    assert m.state.terminal
    # A failed machine does not move again.
    m.fail(ActionState.TIMEOUT)
    assert m.state == ActionState.STALE_ELEMENT


# ── policy + risk ────────────────────────────────────────────────────────────

def test_default_permissions_are_fail_closed():
    policy = ComputerPolicy()
    assert policy.permission_level("observe") == ALLOW
    assert policy.permission_level("click") == ASK
    assert policy.permission_level("type") == ASK
    assert policy.permission_level("finance_mutate") == DENY
    assert policy.permission_level("not_a_permission") == DENY


def test_risk_classification():
    assert classify_action("capture") == "READ"
    assert classify_action("mouse_move") == "LOW"
    assert classify_action("click") == "MEDIUM"
    assert classify_action("window_close") == "HIGH"
    assert classify_action("submit_order") == "CRITICAL"
    assert classify_action("something_new") == "MEDIUM"  # fail-safe
    assert is_financial_mutation("buy")
    assert not is_financial_mutation("click")


def test_app_policy_allow_deny():
    policy = AppPolicy(denied=["bank"], allowed=["excel", "chrome"])
    assert policy.check_app("bank").code == "COMPUTER_APP_DENIED"
    assert policy.check_app("excel").allowed
    assert policy.check_app("random").code == "COMPUTER_APP_NOT_ALLOWED"


def test_policy_evaluate_routes_approval():
    policy = ComputerPolicy(apps=AppPolicy(prohibited_actions=["withdraw"]))
    assert policy.evaluate("observe").allowed
    ask = policy.evaluate("click")
    assert ask.requires_approval and ask.code == "COMPUTER_APPROVAL_REQUIRED"
    blocked = policy.evaluate("click", action="withdraw")
    assert not blocked.allowed and blocked.code == "COMPUTER_ACTION_PROHIBITED"


def test_read_only_finance_denies_mutation():
    policy = default_policy()
    decision = policy.evaluate("finance_mutate", action="buy")
    assert not decision.allowed and not decision.requires_approval


# ── keymap ───────────────────────────────────────────────────────────────────

def test_normalize_combo_primary_modifier():
    combo = normalize_combo("ctrl+s")
    assert combo.endswith("s") and "ctrl" in combo
    semantic = normalize_combo("SAVE")
    expected_mod = "meta" if sys.platform == "darwin" else "ctrl"
    assert expected_mod in semantic


def test_normalize_combo_aliases_and_case():
    assert normalize_combo("Control+S") == normalize_combo("ctrl+s")
    assert normalize_combo("ESC") == "esc"
    assert normalize_combo("Return") == "enter"
    assert normalize_combo("cmd+c").startswith("meta")


def test_virtual_key():
    assert virtual_key("enter") == 0x0D
    assert virtual_key("a") == 0x41
    assert virtual_key("F5") == 0x74
    assert virtual_key("notakey") is None


# ── models ───────────────────────────────────────────────────────────────────

def test_bounds_coercion_and_center():
    b = Bounds.from_any([100, 200, 180, 240])
    assert b.width == 80 and b.height == 40
    assert b.center == (140, 220)
    assert Bounds.from_any({"x": 1, "y": 2, "width": 3, "height": 4}).to_list() == [1, 2, 4, 6]
    assert Bounds.from_any("nonsense") is None


# ── grounding ────────────────────────────────────────────────────────────────

def _elements():
    return [
        {"ref": "1", "role": "button", "name": "Save", "bounds": [10, 10, 60, 30], "enabled": True, "source": "accessibility"},
        {"ref": "2", "role": "textbox", "name": "Ticker", "bounds": [10, 40, 120, 60], "enabled": True, "source": "accessibility"},
        {"ref": "3", "role": "button", "name": "Buy", "bounds": [200, 40, 240, 60], "enabled": True, "source": "accessibility"},
    ]


def test_score_and_rank():
    q = GroundingQuery(intent="Save")
    ranked = rank_elements(q, _elements())
    assert ranked and ranked[0][1]["name"] == "Save"
    assert score_element(q, _elements()[0]) > score_element(q, _elements()[1])


def test_grounder_prefers_accessibility():
    from harness.computer.grounding.grounder import Grounder

    snap = Snapshot(snapshot_id="s1", generation=1, application="excel", window_id="1", elements=[
        SnapshotElement(ref=e["ref"], role=e["role"], name=e["name"], bounds=Bounds.from_any(e["bounds"]), source="accessibility")
        for e in _elements()
    ])
    target = Grounder().ground(GroundingQuery(intent="Buy"), snap)
    assert target.method == "accessibility"
    assert target.name == "Buy"
    assert target.confidence > 0.7


def test_grounder_not_found_and_ambiguous():
    from harness.computer.grounding.grounder import Grounder

    snap = Snapshot(snapshot_id="s1", generation=1, elements=[
        SnapshotElement(ref="1", role="button", name="OK", bounds=Bounds(0, 0, 10, 10)),
        SnapshotElement(ref="2", role="button", name="OK", bounds=Bounds(20, 0, 10, 10)),
    ])
    with pytest.raises(cua_errors.TargetNotFound):
        Grounder().ground(GroundingQuery(intent="Nonexistent"), snap)
    assert is_ambiguous(rank_elements(GroundingQuery(intent="OK"), [e.to_dict() for e in snap.elements]))


# ── verification ─────────────────────────────────────────────────────────────

def test_verifier_verified_changed_uncertain():
    from harness.computer.verification.verifier import ActionVerifier, ObservationState

    verifier = ActionVerifier()
    before = ObservationState(window_id="1", ax_digest="abc")
    after_same = ObservationState(window_id="1", ax_digest="abc")
    after_changed = ObservationState(window_id="1", ax_digest="xyz")
    assert verifier.verify(before, after_changed, action="click").status == "verified"
    uncertain = verifier.verify(before, after_same, action="click")
    assert uncertain.status == "uncertain"
    failed = verifier.verify(before, after_same, action="click", expect={"stateChanged": True})
    assert failed.status == "failed"


# ── recovery ladder ──────────────────────────────────────────────────────────

def test_recovery_plan_order_and_bounds():
    engine = RecoveryEngine(max_attempts=3)
    plan = engine.plan("STALE_ELEMENT")
    assert plan[0] == "recapture"
    assert "escalate_foreground" not in engine.plan("PERMISSION_REQUIRED")
    # Ladder names are all closed.
    for strategy in plan:
        assert strategy in LADDER


@pytest.mark.asyncio
async def test_recovery_execute_stops_on_success():
    engine = RecoveryEngine(max_attempts=3)
    calls: list[str] = []

    async def handler(strategy: str):
        calls.append(strategy)
        return (strategy == "reground", "ok")

    result = await engine.execute("TARGET_NOT_FOUND", {"reground": handler, "try_ocr": handler})
    assert result.recovered and result.strategy == "reground"
    assert calls == ["reground"]


@pytest.mark.asyncio
async def test_recovery_exhausts_budget():
    engine = RecoveryEngine(max_attempts=1)

    async def handler(strategy: str):
        return (False, "nope")

    result = await engine.execute("ACTION_FAILED", {s: handler for s in LADDER})
    assert not result.recovered and result.exhausted and len(result.attempts) == 1


# ── finance extraction ───────────────────────────────────────────────────────

def test_canonical_field_and_parse_number():
    assert canonical_field("Bid") == "bid"
    assert canonical_field("Average Cost") == "average_cost"
    assert canonical_field("Unrealized P&L") == "unrealized_pnl"
    assert parse_number("$254.21") == 254.21
    assert parse_number("+6,550") == 6550.0
    assert parse_number("1.5M") == 1_500_000.0
    assert parse_number("abc") is None


def test_extract_fields_from_lines():
    fields = extract_fields([
        "AAPL",
        "Bid: 254.21",
        "Ask 254.23",
        "Position: 500",
        "Avg Cost: 241.12",
        "P&L: +6,550",
    ])
    assert fields.get("symbol") == "AAPL"
    assert fields["bid"] == 254.21
    assert fields["ask"] == 254.23
    assert fields["position"] == 500
    assert fields["average_cost"] == 241.12
    assert fields["unrealized_pnl"] == 6550.0


# ── finance firewall ─────────────────────────────────────────────────────────

def test_firewall_read_only_blocks_and_non_mutation_passes():
    fw = FinanceActionFirewall(mode=READ_ONLY)
    assert fw.evaluate({"action": "observe"}).allowed
    assert fw.evaluate({"action": "buy"}).blocked
    assert fw.evaluate({"action": "prepare_order"}).blocked


def test_firewall_absolute_block():
    fw = FinanceActionFirewall(mode=AUTONOMOUS)
    for verb in ("withdraw", "transfer", "deposit", "payment", "account_change"):
        assert fw.evaluate({"action": verb}).blocked


def test_firewall_assisted_prepare_then_submit_approval():
    fw = FinanceActionFirewall(mode=ASSISTED)
    prepared = fw.evaluate({"action": "prepare_order", "instrument": "NVDA", "quantity": 100, "price": 120})
    assert prepared.allowed and not prepared.requires_approval
    submitted = fw.evaluate({"action": "buy", "instrument": "NVDA", "quantity": 100, "price": 120})
    assert submitted.requires_approval and not submitted.blocked
    assert submitted.verdict == "approval_required"


def test_firewall_notional_limit_and_allowlists():
    fw = FinanceActionFirewall(mode=AUTONOMOUS, max_order_value=25_000, allowed_instruments=["NVDA"], allowed_apps=["paper_trading"])
    assert fw.evaluate({"action": "buy", "instrument": "NVDA", "quantity": 100, "price": 100, "application": "paper_trading"}).allowed
    blocked_notional = fw.evaluate({"action": "buy", "instrument": "NVDA", "quantity": 1000, "price": 100, "application": "paper_trading"})
    assert blocked_notional.blocked and "exceeds" in blocked_notional.reason
    blocked_instrument = fw.evaluate({"action": "buy", "instrument": "TSLA", "application": "paper_trading"})
    assert blocked_instrument.blocked
    blocked_app = fw.evaluate({"action": "buy", "instrument": "NVDA", "application": "robinhood_live"})
    assert blocked_app.blocked


def test_firewall_simulation_dry_run():
    fw = FinanceActionFirewall(mode=SIMULATION)
    decision = fw.evaluate({"action": "buy", "instrument": "AAPL", "quantity": 10, "price": 100})
    assert decision.allowed and decision.dry_run


# ── security ─────────────────────────────────────────────────────────────────

def test_sensitive_detection_and_redaction():
    layer = SecurityLayer(redaction_enabled=True)
    assert is_sensitive_label("Password")
    assert is_sensitive_label("API Key")
    assert not is_sensitive_label("Send")
    assert looks_sensitive("sk-abc1234567890abcdef")
    report = layer.scan_snapshot([{"name": "Password", "role": "edit", "bounds": [1, 2, 3, 4]}])
    assert report.sensitive and report.regions
    assert layer.redact_text("sk-abc1234567890abcdef") == "«redacted»"


# ── vision routing ───────────────────────────────────────────────────────────

def test_vision_router_refuses_sensitive_to_cloud():
    decision = decide_vision(mode="hybrid", sensitive=True, allow_cloud_sensitive=False,
                             local_available=True, cloud_available=True)
    assert decision.local and not decision.refused
    refused = decide_vision(mode="hybrid", sensitive=True, allow_cloud_sensitive=False,
                            local_available=False, cloud_available=True)
    assert refused.refused
    cloud = decide_vision(mode="hybrid", sensitive=False, allow_cloud_sensitive=False,
                          local_available=True, cloud_available=True)
    assert not cloud.local


# ── takeover ─────────────────────────────────────────────────────────────────

def test_takeover_lease_blocks_agent_until_released():
    manager = TakeoverManager()
    assert manager.agent_may_act("s1")
    manager.take_control("s1")
    assert not manager.agent_may_act("s1")
    manager.resume("s1")
    assert manager.agent_may_act("s1")
    manager.take_control("s1")
    manager.release("s1")
    assert manager.agent_may_act("s1")


# ── replay (inspect) ─────────────────────────────────────────────────────────

def test_replay_inspect_is_deterministic():
    trajectory = {"sessionId": "s1", "steps": [
        {"seq": 1, "kind": "observe", "data": {}},
        {"seq": 2, "kind": "action", "data": {"action": "click", "target": {"element": "1"}}},
    ]}
    report = Replayer().inspect(trajectory)
    assert report.mode == "inspect" and len(report.steps) == 2 and report.ok


# ── adapters ─────────────────────────────────────────────────────────────────

def test_adapter_registry_selects_known_apps():
    registry = build_adapter_registry()
    assert registry.select(app_name="excel.exe").id == "excel"
    assert registry.select(title="Visual Studio Code").id == "vscode"
    assert registry.select(title="MetaTrader 5").id == "mt5"
    assert registry.select(app_name="unknown-app").id == "generic"


def test_trading_adapters_flag_mutations_risky():
    registry = build_adapter_registry()
    adapter = registry.select(title="MetaTrader 5")
    assert adapter.is_risky("submit_order")
    assert adapter.is_risky("withdraw")
    assert not adapter.is_risky("observe")


# ── driver factory ───────────────────────────────────────────────────────────

def test_driver_factory_null_and_auto():
    assert isinstance(build_driver("null"), NullDriver)
    # `auto` always yields a driver (null on an unsupported platform).
    assert build_driver("auto") is not None
