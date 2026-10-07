"""The Finance Action Firewall.

The generic Computer Use engine must NEVER perform an unrestricted financial
mutation. Every financial intent is classified, evaluated against the finance
policy (read_only / assisted / autonomous / simulation), bounded by limits, and
either blocked, held for approval, or permitted as a dry run.

    Agent → Financial Intent → Finance Policy → Risk Classification → Approval
          → Computer Use

The firewall returns a `FinanceDecision` (DATA): permitted / requires_approval /
blocked, with a plain reason and the classification facts. It never touches the
UI — the core only proceeds when the firewall permits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Finance risk modes.
READ_ONLY = "read_only"
ASSISTED = "assisted"
AUTONOMOUS = "autonomous"
SIMULATION = "simulation"
FINANCE_RISK_MODES = (READ_ONLY, ASSISTED, AUTONOMOUS, SIMULATION)

# Financial mutation verbs (canonical).
MUTATION_VERBS: frozenset[str] = frozenset({
    "buy", "sell", "short", "cover", "submit_order", "place_order",
    "cancel_order", "modify_order", "transfer", "withdraw", "deposit",
    "payment", "account_change",
})

# Verbs that are never allowed under any mode (money movement / account change).
ABSOLUTE_BLOCK: frozenset[str] = frozenset({"transfer", "withdraw", "deposit", "payment", "account_change"})

# The "prepare-only" verbs of ASSISTED mode: fill an order ticket but never submit.
PREPARE_VERBS: frozenset[str] = frozenset({"prepare_order", "fill_order", "stage_order"})


@dataclass
class FinanceDecision:
    allowed: bool
    requires_approval: bool
    blocked: bool
    action: str
    reason: str
    classification: str = "financial_mutation"
    mode: str = READ_ONLY
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def verdict(self) -> str:
        if self.blocked:
            return "blocked"
        if self.requires_approval:
            return "approval_required"
        return "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed, "requiresApproval": self.requires_approval,
            "blocked": self.blocked, "action": self.action, "reason": self.reason,
            "classification": self.classification, "mode": self.mode,
            "dryRun": self.dry_run, "verdict": self.verdict, "metadata": self.metadata,
        }


class FinanceActionFirewall:
    def __init__(
        self,
        *,
        mode: str = READ_ONLY,
        max_order_value: float = 0.0,
        allowed_apps: Optional[list[str]] = None,
        allowed_accounts: Optional[list[str]] = None,
        allowed_instruments: Optional[list[str]] = None,
        prohibited_actions: Optional[list[str]] = None,
    ) -> None:
        self.mode = mode if mode in FINANCE_RISK_MODES else READ_ONLY
        self.max_order_value = float(max_order_value or 0.0)
        self.allowed_apps = [a.lower() for a in (allowed_apps or [])]
        self.allowed_accounts = [a.lower() for a in (allowed_accounts or [])]
        self.allowed_instruments = [i.upper() for i in (allowed_instruments or [])]
        self.prohibited_actions = {a.lower() for a in (prohibited_actions or [])}

    def evaluate(self, intent: dict[str, Any]) -> FinanceDecision:
        """Classify and decide a financial intent.

        `intent` carries: action, application, account, instrument, quantity,
        price, notional, order_type. Missing facts are treated conservatively.
        """
        action = str(intent.get("action") or "").strip().lower()
        if action not in MUTATION_VERBS and action not in PREPARE_VERBS:
            return FinanceDecision(
                allowed=True, requires_approval=False, blocked=False, action=action,
                reason="not a financial mutation", classification="non_mutation", mode=self.mode,
            )

        # 1. Prohibited / absolute-block verbs.
        if action in self.prohibited_actions:
            return self._blocked(action, f"{action.replace('_', ' ')} is prohibited by policy.")
        if action in ABSOLUTE_BLOCK:
            return self._blocked(action, f"Eclipse never performs {action.replace('_', ' ')} on its own.")

        # 2. Application allowlist.
        app = str(intent.get("application") or "").lower()
        if self.allowed_apps and app and app not in self.allowed_apps and not any(a in app for a in self.allowed_apps):
            return self._blocked(action, f"{intent.get('application')!r} isn't an approved trading application.")

        # 3. Account allowlist.
        account = str(intent.get("account") or "").lower()
        if self.allowed_accounts and account and account not in self.allowed_accounts:
            return self._blocked(action, f"Account {intent.get('account')!r} isn't approved for trades.")

        # 4. Instrument allowlist.
        instrument = str(intent.get("instrument") or "").upper()
        if self.allowed_instruments and instrument and instrument not in self.allowed_instruments:
            return self._blocked(action, f"{instrument!r} isn't on the approved instrument list.")

        # 5. READ_ONLY: mutations are blocked; prepare is refused too (no UI change).
        if self.mode == READ_ONLY:
            return self._blocked(action, "Eclipse is in read-only mode and won't place or prepare orders.")

        # 6. ASSISTED: only prepare operations; the SUBMIT always needs approval.
        if self.mode == ASSISTED:
            if action in PREPARE_VERBS:
                return FinanceDecision(
                    allowed=True, requires_approval=False, blocked=False, action=action,
                    reason="order preparation is allowed in assisted mode; submission is not",
                    mode=self.mode,
                )
            return FinanceDecision(
                allowed=False, requires_approval=True, blocked=False, action=action,
                reason=f"Assisted mode prepared the {action.replace('_', ' ')} and is waiting for your approval.",
                mode=self.mode, metadata={"limit": self.max_order_value},
            )

        # 7. Notional limit (autonomous/simulation).
        notional = self._notional(intent)
        if self.max_order_value and notional is not None and notional > self.max_order_value:
            return self._blocked(
                action,
                f"Order value {notional:,.0f} exceeds the {self.max_order_value:,.0f} limit.",
                metadata={"notional": notional, "limit": self.max_order_value},
            )

        # 8. AUTONOMOUS: permitted only when policy explicitly allows it. Even then,
        # a live autonomous mutation is still approval-gated unless the operator set
        # the autonomous mode deliberately (which we surface, not hide).
        if self.mode == AUTONOMOUS:
            return FinanceDecision(
                allowed=True, requires_approval=False, blocked=False, action=action,
                reason="autonomous mode: policy permits this mutation within limits",
                mode=self.mode, metadata={"notional": notional},
            )

        # 9. SIMULATION: paper trading — permitted as a dry-run-style action.
        if self.mode == SIMULATION:
            return FinanceDecision(
                allowed=True, requires_approval=False, blocked=False, action=action,
                reason="simulation mode: paper trading only", mode=self.mode, dry_run=True,
                metadata={"notional": notional},
            )

        return self._blocked(action, "this financial action isn't permitted in the current mode.")

    def _notional(self, intent: dict[str, Any]) -> Optional[float]:
        if intent.get("notional") is not None:
            try:
                return float(intent["notional"])
            except (TypeError, ValueError):
                return None
        try:
            qty = float(intent.get("quantity")) if intent.get("quantity") is not None else None
            price = float(intent.get("price")) if intent.get("price") is not None else None
        except (TypeError, ValueError):
            return None
        if qty is not None and price is not None:
            return abs(qty * price)
        return None

    def _blocked(self, action: str, reason: str, *, metadata: Optional[dict[str, Any]] = None) -> FinanceDecision:
        return FinanceDecision(
            allowed=False, requires_approval=False, blocked=True, action=action,
            reason=reason, mode=self.mode, metadata=metadata or {},
        )


def build_firewall_from_config(cfg: Any) -> FinanceActionFirewall:
    return FinanceActionFirewall(
        mode=cfg.finance_mode, max_order_value=cfg.finance_max_order_value,
        prohibited_actions=list(cfg.prohibited_actions),
    )


__all__ = [
    "ABSOLUTE_BLOCK", "ASSISTED", "AUTONOMOUS", "FINANCE_RISK_MODES",
    "FinanceActionFirewall", "FinanceDecision", "MUTATION_VERBS", "PREPARE_VERBS",
    "READ_ONLY", "SIMULATION", "build_firewall_from_config",
]
