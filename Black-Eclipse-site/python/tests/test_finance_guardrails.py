"""Money-movement guardrails: deterministic rules + the single-use confirm gate.

Every test is synthetic. No broker, no network, no model: the guardrail layer is
deliberately model-free, so a failure here is a real behavioural regression.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest

from harness.finance_guardrails.intent import intent_from_payload, intent_from_tool
from harness.finance_guardrails.models import MoneyIntent
from harness.finance_guardrails.service import FinanceGuardrailService
from harness.mcp.approvals import ApprovalStore
from harness.persistence import AgentMemoryStore


def _service(tmp_path, *, approvals: bool = False) -> FinanceGuardrailService:
    store = AgentMemoryStore(os.path.join(str(tmp_path), "guardrails-test.db"))
    return FinanceGuardrailService(store, approvals=ApprovalStore(store) if approvals else None)


class _Ctx:
    def __init__(self, approvals=None) -> None:
        self.approvals = approvals
        self.pause_for_approval = False
        self.emitter = None
        self.run_id = "run_test"


# ── scam / coercion ──────────────────────────────────────────────────────────

def test_two_high_scam_signals_deny(tmp_path):
    service = _service(tmp_path)
    intent = MoneyIntent(
        action="transfer",
        amount=5000,
        counterparty="new-wallet",
        source_text="URGENT: wire transfer now, don't tell anyone, guaranteed profit",
    )
    verdict = service.evaluate(intent)
    assert verdict.decision == "deny"
    assert "scam.urgency" in verdict.rules
    assert "scam.secrecy" in verdict.rules


def test_single_high_scam_signal_confirms_with_cooling(tmp_path):
    service = _service(tmp_path)
    intent = MoneyIntent(action="transfer", amount=100, source_text="please act now")
    verdict = service.evaluate(intent)
    assert verdict.decision == "confirm"
    assert verdict.cooling_off_seconds >= 900
    assert verdict.requires_typed_confirmation is True


def test_plain_trade_has_no_scam_friction(tmp_path):
    service = _service(tmp_path)
    intent = MoneyIntent(action="buy", amount=250, instrument="AAPL", source_text="buy 10 shares")
    verdict = service.evaluate(intent)
    assert verdict.decision == "allow"


# ── limits ───────────────────────────────────────────────────────────────────

def test_per_transaction_cap_denies(tmp_path):
    service = _service(tmp_path)
    service.update_config({"perTxnCap": 100})
    verdict = service.evaluate(MoneyIntent(action="buy", amount=500))
    assert verdict.decision == "deny"
    assert "limit.per-transaction" in verdict.rules


def test_daily_cap_uses_the_ledger(tmp_path):
    service = _service(tmp_path)
    service.update_config({"dailyCap": 1000})
    assert service.evaluate_and_record(MoneyIntent(action="buy", amount=600)).decision == "allow"
    verdict = service.evaluate(MoneyIntent(action="buy", amount=600))
    assert verdict.decision == "deny"
    assert "limit.daily" in verdict.rules


def test_velocity_denies_repetition(tmp_path):
    service = _service(tmp_path)
    service.update_config({"velocityPerHour": 2})
    service.evaluate_and_record(MoneyIntent(action="buy", amount=10))
    service.evaluate_and_record(MoneyIntent(action="buy", amount=10))
    verdict = service.evaluate(MoneyIntent(action="buy", amount=10))
    assert verdict.decision == "deny"
    assert "limit.velocity" in verdict.rules


def test_blocked_counterparty_is_denied(tmp_path):
    service = _service(tmp_path)
    service.update_config({"blocklist": ["0xbad"]})
    verdict = service.evaluate(MoneyIntent(action="transfer", amount=10, counterparty="0xbad"))
    assert verdict.decision == "deny"
    assert "limit.counterparty-blocked" in verdict.rules


# ── impaired / crisis ────────────────────────────────────────────────────────

def test_declared_impairment_confirms_for_half_an_hour(tmp_path):
    service = _service(tmp_path)
    service.update_config({"impairedMode": True})
    verdict = service.evaluate(MoneyIntent(action="buy", amount=100))
    assert verdict.decision == "confirm"
    assert verdict.cooling_off_seconds >= 1800
    assert "impaired.declared" in verdict.rules


def test_amount_far_above_baseline_confirms(tmp_path):
    service = _service(tmp_path)
    for _ in range(6):
        service.evaluate_and_record(MoneyIntent(action="buy", amount=10))
    verdict = service.evaluate(MoneyIntent(action="buy", amount=500))
    assert verdict.decision == "confirm"
    assert "impaired.above-baseline" in verdict.rules


def test_crisis_blocks_trading_and_escalates_transfers(tmp_path):
    service = _service(tmp_path)
    service.update_config({"crisisMode": True, "trustedContact": "Sam"})
    trade = service.evaluate(MoneyIntent(action="buy", amount=10))
    assert trade.decision == "deny"
    assert trade.escalate_to == "Sam"
    transfer = service.evaluate(MoneyIntent(action="transfer", amount=10, counterparty="x"))
    assert transfer.decision == "escalate"
    assert transfer.escalate_to == "Sam"


def test_panic_pause_denies_everything_even_when_mode_off(tmp_path):
    service = _service(tmp_path)
    service.update_config({"mode": "off", "panicPaused": True})
    verdict = service.evaluate(MoneyIntent(action="buy", amount=10))
    assert verdict.decision == "deny"
    assert "crisis.panic-pause" in verdict.rules


# ── novelty ──────────────────────────────────────────────────────────────────

def test_new_counterparty_on_an_irreversible_rail_confirms(tmp_path):
    service = _service(tmp_path)
    verdict = service.evaluate(MoneyIntent(action="transfer", amount=50, counterparty="brand-new"))
    assert verdict.decision == "confirm"
    assert "novelty.new-counterparty" in verdict.rules


def test_known_counterparty_is_not_novel(tmp_path):
    service = _service(tmp_path)
    service.update_config({"coolingSeconds": 0})
    service.evaluate_and_record(MoneyIntent(action="transfer", amount=50, counterparty="friend"))
    verdict = service.evaluate(MoneyIntent(action="transfer", amount=50, counterparty="friend"))
    assert "novelty.new-counterparty" not in verdict.rules


# ── intent recognition ───────────────────────────────────────────────────────

def test_computer_click_recognises_a_money_action():
    intent = intent_from_tool(
        "computer_use", {"action": "click", "target": "Buy 10 AAPL at 190"},
        run_id="r1",
    )
    assert intent is not None
    assert intent.action == "buy"
    assert intent.amount == 1900.0
    assert intent.channel == "computer"


def test_browser_click_recognises_a_withdrawal():
    intent = intent_from_tool("browser_click", {"target": "Withdraw funds"}, run_id="r1")
    assert intent is not None
    assert intent.action == "withdraw"
    assert intent.channel == "browser"


def test_mcp_order_tool_is_recognised():
    intent = intent_from_tool(
        "place_order",
        {"quantity": 2, "price": 50, "symbol": "msft"},
        effect="external_action",
    )
    assert intent is not None
    assert intent.action == "place_order"
    assert intent.amount == 100.0
    assert intent.instrument == "MSFT"


def test_unrelated_tool_is_not_a_money_intent():
    assert intent_from_tool("get_quote", {"symbol": "AAPL"}) is None
    assert intent_from_tool("computer_use", {"action": "capture"}) is None


def test_payload_intent_requires_a_verb():
    assert intent_from_payload({"action": "view"}) is None
    intent = intent_from_payload({"action": "transfer", "amount": 25, "counterparty": "x"})
    assert intent is not None
    assert intent.action == "transfer"


# ── the single-use confirm gate ──────────────────────────────────────────────

def test_confirm_gate_requires_an_approval_then_consumes_it_once(tmp_path):
    service = _service(tmp_path, approvals=True)
    service.update_config({"highValue": 100, "coolingSeconds": 0})
    approvals = service.approvals
    ctx = _Ctx(approvals=approvals)
    intent = MoneyIntent(action="buy", amount=500, instrument="AAPL")

    allowed, verdict = asyncio.run(service.enforce(intent, ctx))
    assert allowed is False
    assert verdict.decision == "confirm"
    pending = approvals.list_kind("money_guardrail", status="pending")
    assert len(pending) == 1
    approvals.decide(pending[0]["id"], approve=True)

    # Cooling-off is still in force (the high-value rule asks for 120s), so the
    # approval alone does not authorize the call yet.
    allowed, _ = asyncio.run(service.enforce(intent, ctx))
    assert allowed is False

    # Move the decision into the past and retry: the single approval authorizes
    # exactly one call.
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    approvals._db.execute("UPDATE McpApproval SET createdAt=? WHERE id=?", (past, pending[0]["id"]))
    approvals._db.commit()

    allowed, _ = asyncio.run(service.enforce(intent, ctx))
    assert allowed is True
    allowed_again, _ = asyncio.run(service.enforce(intent, ctx))
    assert allowed_again is False


# ── store / status ───────────────────────────────────────────────────────────

def test_config_round_trip_and_status(tmp_path):
    service = _service(tmp_path)
    config = service.update_config({
        "perTxnCap": 250, "dailyCap": 1000, "velocityPerHour": 4,
        "impairedMode": True, "allowlist": ["friend"], "blocklist": "bad, worse",
    })
    assert config["perTxnCap"] == 250
    assert config["impairedMode"] is True
    assert config["blocklist"] == ["bad", "worse"]
    status = service.status()
    assert status["available"] is True
    assert "spendToday" in status["aggregates"]
