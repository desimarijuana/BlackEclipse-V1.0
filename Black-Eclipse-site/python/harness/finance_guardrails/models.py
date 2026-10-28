"""Contracts for the money-movement guardrails.

These are DATA. The runtime enforces them; nothing here touches a UI, a broker
or the network. A `MoneyIntent` is the normalized shape of any action that could
move money; a `GuardrailVerdict` is the augment-only decision the guardrail layer
attaches to it.

Invariants:
  * a verdict can only make an action MORE restrictive than the layers below it
    (Security Floor / policy / gateway);
  * `DENY` is terminal for the action; `CONFIRM` means the existing single-use
    approval store must authorize this exact intent;
  * a verdict always explains itself in plain language (`reasons`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

# ── Decisions ────────────────────────────────────────────────────────────────
ALLOW = "allow"
CONFIRM = "confirm"
DENY = "deny"
ESCALATE = "escalate"

DECISION_RANK = {ALLOW: 0, CONFIRM: 1, ESCALATE: 2, DENY: 3}

# ── Channels ─────────────────────────────────────────────────────────────────
CHANNEL_COMPUTER = "computer"
CHANNEL_BROWSER = "browser"
CHANNEL_MCP = "mcp"
CHANNEL_SHELL = "shell"
CHANNEL_NATIVE = "native"

# ── Money-moving verbs (canonical) ───────────────────────────────────────────
MONEY_ACTIONS: frozenset[str] = frozenset({
    "buy", "sell", "short", "cover", "submit_order", "place_order",
    "cancel_order", "modify_order", "prepare_order", "fill_order", "stage_order",
    "transfer", "withdraw", "deposit", "payment", "send", "pay",
})

# Verbs that move money OUT of the user's control (irreversible rails).
IRREVERSIBLE_ACTIONS: frozenset[str] = frozenset({
    "transfer", "withdraw", "deposit", "payment", "send", "pay",
})

# Trading verbs (discretionary). Crisis mode blocks these outright.
TRADING_ACTIONS: frozenset[str] = frozenset({
    "buy", "sell", "short", "cover", "submit_order", "place_order",
    "cancel_order", "modify_order",
})


@dataclass
class MoneyIntent:
    """A normalized money-moving action assembled from a tool call."""

    action: str
    tool: str = ""
    channel: str = CHANNEL_NATIVE
    amount: Optional[float] = None
    currency: str = "USD"
    counterparty: Optional[str] = None
    instrument: Optional[str] = None
    account: Optional[str] = None
    run_id: str = ""
    source_text: str = ""
    args: dict[str, Any] = field(default_factory=dict)

    @property
    def is_irreversible(self) -> bool:
        return self.action in IRREVERSIBLE_ACTIONS

    @property
    def is_trading(self) -> bool:
        return self.action in TRADING_ACTIONS

    @property
    def key(self) -> str:
        """A stable request key for the single-use approval store."""
        target = self.counterparty or self.instrument or self.account or "any"
        return f"money:{self.action}:{target}"

    @property
    def digest(self) -> str:
        canonical = json.dumps(
            {
                "action": self.action,
                "amount": self.amount,
                "currency": self.currency,
                "counterparty": self.counterparty,
                "instrument": self.instrument,
                "account": self.account,
                "tool": self.tool,
                "channel": self.channel,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "tool": self.tool,
            "channel": self.channel,
            "amount": self.amount,
            "currency": self.currency,
            "counterparty": self.counterparty,
            "instrument": self.instrument,
            "account": self.account,
            "runId": self.run_id,
            "irreversible": self.is_irreversible,
        }


@dataclass
class RuleHit:
    rule: str
    reason: str
    decision: str


@dataclass
class GuardrailVerdict:
    """The augment-only decision for one `MoneyIntent`."""

    decision: str = ALLOW
    reasons: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    risk: str = "none"
    cooling_off_seconds: int = 0
    requires_typed_confirmation: bool = False
    confirm_phrase: str = ""
    escalate_to: Optional[str] = None
    intent: Optional[MoneyIntent] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision == ALLOW

    @property
    def blocked(self) -> bool:
        return self.decision == DENY

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": list(self.reasons),
            "rules": list(self.rules),
            "risk": self.risk,
            "coolingOffSeconds": self.cooling_off_seconds,
            "requiresTypedConfirmation": self.requires_typed_confirmation,
            "confirmPhrase": self.confirm_phrase,
            "escalateTo": self.escalate_to,
            "intent": self.intent.to_dict() if self.intent else None,
            "metadata": self.metadata,
        }

    def challenge(self) -> dict[str, Any]:
        return {
            "reasons": list(self.reasons),
            "coolingOffSeconds": self.cooling_off_seconds,
            "requiresTypedConfirmation": self.requires_typed_confirmation,
            "confirmPhrase": self.confirm_phrase,
            "escalateTo": self.escalate_to,
            "amount": self.intent.amount if self.intent else None,
            "currency": self.intent.currency if self.intent else None,
            "counterparty": self.intent.counterparty if self.intent else None,
        }


def combine(verdicts: list[GuardrailVerdict], *, intent: MoneyIntent) -> GuardrailVerdict:
    """Merge rule verdicts into ONE, keeping the most restrictive decision.

    Reasons and rule names accumulate so the operator sees every signal, never
    only the first one. Cooling-off and typed-confirmation are the maximum of the
    contributing verdicts. This function can only raise restrictiveness.
    """
    merged = GuardrailVerdict(intent=intent)
    rank = -1
    for verdict in verdicts:
        if not verdict or verdict.decision == ALLOW:
            continue
        merged.reasons.extend(r for r in verdict.reasons if r not in merged.reasons)
        merged.rules.extend(r for r in verdict.rules if r not in merged.rules)
        merged.cooling_off_seconds = max(merged.cooling_off_seconds, verdict.cooling_off_seconds)
        merged.requires_typed_confirmation = (
            merged.requires_typed_confirmation or verdict.requires_typed_confirmation
        )
        if verdict.confirm_phrase and not merged.confirm_phrase:
            merged.confirm_phrase = verdict.confirm_phrase
        if verdict.escalate_to and not merged.escalate_to:
            merged.escalate_to = verdict.escalate_to
        if verdict.risk and _risk_rank(verdict.risk) > _risk_rank(merged.risk):
            merged.risk = verdict.risk
        current_rank = DECISION_RANK.get(verdict.decision, 0)
        if current_rank > rank:
            rank = current_rank
            merged.decision = verdict.decision
    if merged.decision == ALLOW:
        merged.risk = "none"
    if merged.decision in (CONFIRM, ESCALATE) and not merged.confirm_phrase:
        merged.requires_typed_confirmation = True
    return merged


_RISK_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _risk_rank(value: str) -> int:
    return _RISK_ORDER.get(str(value or "none").lower(), 0)


__all__ = [
    "ALLOW", "CHANNEL_BROWSER", "CHANNEL_COMPUTER", "CHANNEL_MCP",
    "CHANNEL_NATIVE", "CHANNEL_SHELL", "CONFIRM", "DECISION_RANK", "DENY",
    "ESCALATE", "GuardrailVerdict", "IRREVERSIBLE_ACTIONS", "MONEY_ACTIONS",
    "MoneyIntent", "RuleHit", "TRADING_ACTIONS", "combine",
]
