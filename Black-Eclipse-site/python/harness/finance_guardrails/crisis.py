"""Crisis mode and the global panic pause.

Both are HUMAN switches. An agent may never enable or clear them; the operator
routes are the only writers (gated by `require_operator`).

  * `panicPaused` stops ALL money movement immediately and everywhere.
  * `crisisMode` blocks discretionary trading outright and escalates any
    irreversible transfer/payment to a confirmation that names the trusted
    contact, so the decision is not taken alone.
"""

from __future__ import annotations

from typing import Any

from .models import CONFIRM, DENY, ESCALATE, GuardrailVerdict, MoneyIntent


def evaluate(intent: MoneyIntent, config: dict[str, Any]) -> GuardrailVerdict:
    verdict = GuardrailVerdict(intent=intent)

    if bool(config.get("panicPaused")):
        verdict.decision = DENY
        verdict.risk = "critical"
        verdict.rules.append("crisis.panic-pause")
        verdict.reasons.append(
            "Money movement is paused. Nothing will be sent until you unpause it."
        )
        return verdict

    if not bool(config.get("crisisMode")):
        return verdict

    trusted = str(config.get("trustedContact") or "").strip() or None
    if intent.is_trading:
        verdict.decision = DENY
        verdict.risk = "critical"
        verdict.rules.append("crisis.trading")
        verdict.reasons.append(
            "Crisis mode is on: Eclipse will not place or change a trade for you right now."
        )
        verdict.escalate_to = trusted
        return verdict

    if intent.is_irreversible:
        verdict.decision = ESCALATE
        verdict.risk = "critical"
        verdict.rules.append("crisis.irreversible")
        verdict.reasons.append(
            "Crisis mode is on: this moves money out and needs a deliberate confirmation"
            + (f" plus a check-in with {trusted}." if trusted else ".")
        )
        verdict.escalate_to = trusted
        verdict.cooling_off_seconds = 3600
        verdict.requires_typed_confirmation = True
        return verdict

    verdict.decision = CONFIRM
    verdict.risk = "high"
    verdict.rules.append("crisis.general")
    verdict.reasons.append("Crisis mode is on: confirm this deliberate money movement.")
    verdict.escalate_to = trusted
    verdict.cooling_off_seconds = 600
    verdict.requires_typed_confirmation = True
    return verdict


__all__ = ["evaluate"]
