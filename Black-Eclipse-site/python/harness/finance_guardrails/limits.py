"""Aggregate spend, velocity and counterparty limits.

Per-intent checks are not enough: harm usually appears as REPETITION. These
rules bound the rolling ledger (today / 30 days / the last hour) and the set of
counterparties an intent may pay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .models import CONFIRM, DENY, GuardrailVerdict, MoneyIntent


@dataclass
class Aggregates:
    spend_today: float = 0.0
    spend_30d: float = 0.0
    count_last_hour: int = 0
    baseline_p95: Optional[float] = None
    recent_amounts: list[float] = field(default_factory=list)


def _num(config: dict[str, Any], key: str, default: float) -> float:
    try:
        value = config.get(key, default)
        return float(value) if value is not None else float(default)
    except (TypeError, ValueError):
        return float(default)


def evaluate(intent: MoneyIntent, config: dict[str, Any], aggregates: Aggregates) -> GuardrailVerdict:
    verdict = GuardrailVerdict(intent=intent)
    amount = intent.amount
    counterparty = (intent.counterparty or "").strip().lower()

    blocklist = {str(v).strip().lower() for v in (config.get("blocklist") or []) if str(v).strip()}
    if counterparty and counterparty in blocklist:
        verdict.decision = DENY
        verdict.risk = "critical"
        verdict.rules.append("limit.counterparty-blocked")
        verdict.reasons.append(f"{intent.counterparty!r} is on your blocked counterparty list.")
        return verdict

    allowlist = {str(v).strip().lower() for v in (config.get("allowlist") or []) if str(v).strip()}
    if counterparty and allowlist and counterparty not in allowlist:
        verdict.decision = DENY
        verdict.risk = "high"
        verdict.rules.append("limit.counterparty-not-allowed")
        verdict.reasons.append(
            f"{intent.counterparty!r} is not on your approved counterparty list."
        )
        return verdict

    per_txn_cap = _num(config, "perTxnCap", 0.0)
    if amount is not None and per_txn_cap > 0 and amount > per_txn_cap:
        verdict.decision = DENY
        verdict.risk = "high"
        verdict.rules.append("limit.per-transaction")
        verdict.reasons.append(
            f"{amount:,.2f} exceeds your per-transaction cap of {per_txn_cap:,.2f}."
        )
        return verdict

    daily_cap = _num(config, "dailyCap", 0.0)
    if amount is not None and daily_cap > 0 and aggregates.spend_today + amount > daily_cap:
        verdict.decision = DENY
        verdict.risk = "high"
        verdict.rules.append("limit.daily")
        verdict.reasons.append(
            f"This would bring today's money movement to "
            f"{aggregates.spend_today + amount:,.2f}, above your daily cap of {daily_cap:,.2f}."
        )
        return verdict

    velocity = int(_num(config, "velocityPerHour", 0.0))
    if velocity > 0 and aggregates.count_last_hour + 1 > velocity:
        verdict.decision = DENY
        verdict.risk = "high"
        verdict.rules.append("limit.velocity")
        verdict.reasons.append(
            f"You have already made {aggregates.count_last_hour} money movements in the "
            f"last hour; the limit is {velocity}."
        )
        return verdict

    high_value = _num(config, "highValue", 0.0)
    if amount is not None and high_value > 0 and amount >= high_value:
        verdict.decision = CONFIRM
        verdict.risk = "high"
        verdict.rules.append("limit.high-value")
        verdict.reasons.append(
            f"{amount:,.2f} is at or above your high-value review threshold of {high_value:,.2f}."
        )
        verdict.cooling_off_seconds = max(verdict.cooling_off_seconds, 120)
        verdict.requires_typed_confirmation = True
        return verdict

    if intent.is_irreversible and amount is None:
        verdict.decision = CONFIRM
        verdict.risk = "high"
        verdict.rules.append("limit.unknown-amount")
        verdict.reasons.append("This transfer/payment does not state an amount; confirm the exact figure.")
        verdict.requires_typed_confirmation = True
        return verdict

    return verdict


__all__ = ["Aggregates", "evaluate"]
