"""Impaired-spending protection.

Two independent inputs, both additive:

  * a SELF-DECLARED state (the operator says they are unwell, grieving, manic,
    sleep-deprived or otherwise not making deliberate decisions today); and
  * BEHAVIOURAL signals measured against the user's own ledger — rapid repeats,
    escalating sizes, and an amount far above their normal range.

Neither path is diagnostic. The effect is simply more friction (a cooling-off
period and an explicit typed confirmation), never a silent block.
"""

from __future__ import annotations

from typing import Any

from .limits import Aggregates
from .models import CONFIRM, GuardrailVerdict, MoneyIntent


def _num(config: dict[str, Any], key: str, default: float) -> float:
    try:
        value = config.get(key, default)
        return float(value) if value is not None else float(default)
    except (TypeError, ValueError):
        return float(default)


def evaluate(intent: MoneyIntent, config: dict[str, Any], aggregates: Aggregates) -> GuardrailVerdict:
    verdict = GuardrailVerdict(intent=intent)

    if bool(config.get("impairedMode")):
        verdict.decision = CONFIRM
        verdict.risk = "high"
        verdict.rules.append("impaired.declared")
        verdict.reasons.append(
            "You told Eclipse you are not making deliberate money decisions today. "
            "Take a pause before this moves."
        )
        verdict.cooling_off_seconds = 1800
        verdict.requires_typed_confirmation = True
        return verdict

    if intent.amount is None:
        return verdict

    amount = abs(float(intent.amount))
    multiplier = _num(config, "baselineMultiplier", 3.0)
    baseline = aggregates.baseline_p95
    if baseline and baseline > 0 and amount > baseline * multiplier:
        verdict.decision = CONFIRM
        verdict.risk = "high"
        verdict.rules.append("impaired.above-baseline")
        verdict.reasons.append(
            f"{amount:,.2f} is more than {multiplier:g}x your usual money-movement size "
            f"(p95 {baseline:,.2f})."
        )
        verdict.cooling_off_seconds = max(verdict.cooling_off_seconds, 600)
        verdict.requires_typed_confirmation = True
        return verdict

    recent = [abs(a) for a in (aggregates.recent_amounts or []) if a]
    if len(recent) >= 3:
        last_three = recent[:3]
        if last_three[0] > last_three[1] * 2 and last_three[1] > last_three[2] * 2:
            verdict.decision = CONFIRM
            verdict.risk = "high"
            verdict.rules.append("impaired.escalating")
            verdict.reasons.append(
                "Your three most recent money movements each roughly doubled the previous one."
            )
            verdict.cooling_off_seconds = max(verdict.cooling_off_seconds, 600)
            verdict.requires_typed_confirmation = True
            return verdict

    return verdict


__all__ = ["evaluate"]
