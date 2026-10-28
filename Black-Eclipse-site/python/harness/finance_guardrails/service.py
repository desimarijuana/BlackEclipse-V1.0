"""The money-movement guardrail service.

One evaluation pipeline, one persistence store, one confirmation gate. The
pipeline is ordered from the most absolute rule to the softest:

    panic pause → crisis → limits → scam/coercion → impaired → novelty/high value

Rules only ever ADD restrictiveness. A `CONFIRM` is not a pass: it routes the
exact intent through the SAME single-use, digest-bound approval store every
other effectful capability uses. `DENY` is terminal and explained.

The service is deliberately model-free. No LLM decides whether money moves.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from . import crisis, impaired as impaired_rules, limits, scam
from .intent import intent_from_tool
from .models import (
    ALLOW,
    CONFIRM,
    DENY,
    ESCALATE,
    GuardrailVerdict,
    MoneyIntent,
    combine,
)
from .store import MoneyGuardrailStore, _parse_iso


class FinanceGuardrailService:
    def __init__(self, store: Any, approvals: Any = None) -> None:
        self.store = MoneyGuardrailStore(store)
        self.approvals = approvals

    # ── configuration / state ────────────────────────────────────────────────
    def config(self) -> dict[str, Any]:
        return self.store.get_config()

    def update_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_config(patch)

    def status(self, *, limit: int = 25) -> dict[str, Any]:
        return {
            "available": True,
            "config": self.config(),
            "aggregates": self.store.aggregates(),
            "recent": self.store.list_intents(limit=limit),
        }

    # ── evaluation ───────────────────────────────────────────────────────────
    def _cooling_floor(self, config: dict[str, Any]) -> int:
        try:
            return max(0, int(config.get("coolingSeconds") or 0))
        except (TypeError, ValueError):
            return 0

    def evaluate(self, intent: MoneyIntent) -> GuardrailVerdict:
        config = self.config()

        # Panic is absolute: it applies even when the guardrail mode is "off".
        if bool(config.get("panicPaused")):
            verdict = crisis.evaluate(intent, config)
            return self._finalize(verdict, intent, config)

        if str(config.get("mode") or "guard") == "off":
            return GuardrailVerdict(decision=ALLOW, intent=intent)

        raw = self.store.aggregates()
        aggregates = limits.Aggregates(
            spend_today=float(raw.get("spendToday") or 0.0),
            spend_30d=float(raw.get("spend30d") or 0.0),
            count_last_hour=int(raw.get("countLastHour") or 0),
            baseline_p95=raw.get("baselineP95"),
            recent_amounts=list(raw.get("recentAmounts") or []),
        )
        verdicts: list[GuardrailVerdict] = [
            crisis.evaluate(intent, config),
            limits.evaluate(intent, config, aggregates),
            scam.evaluate(intent),
            impaired_rules.evaluate(intent, config, aggregates),
        ]

        # A brand-new counterparty on an irreversible rail is always a review.
        if (
            intent.is_irreversible
            and intent.counterparty
            and not self.store.counterparty_seen(intent.counterparty)
        ):
            verdicts.append(GuardrailVerdict(
                decision=CONFIRM,
                intent=intent,
                risk="high",
                rules=["novelty.new-counterparty"],
                reasons=[
                    f"This is the first payment to {intent.counterparty!r}. "
                    "Confirm the destination yourself before sending."
                ],
                cooling_off_seconds=300,
                requires_typed_confirmation=True,
            ))

        return self._finalize(combine(verdicts, intent=intent), intent, config)

    def _finalize(
        self, verdict: GuardrailVerdict, intent: MoneyIntent, config: dict[str, Any],
    ) -> GuardrailVerdict:
        verdict.intent = intent
        if verdict.decision in (CONFIRM, ESCALATE):
            floor = self._cooling_floor(config)
            verdict.cooling_off_seconds = max(verdict.cooling_off_seconds, floor if verdict.risk in ("high", "critical") else 0)
            if not verdict.confirm_phrase:
                amount = f" {intent.amount:,.2f}" if intent.amount is not None else ""
                verdict.confirm_phrase = f"{intent.action.upper()}{amount}"
            verdict.requires_typed_confirmation = True
        return verdict

    def evaluate_and_record(self, intent: MoneyIntent) -> GuardrailVerdict:
        verdict = self.evaluate(intent)
        self.store.record(intent, verdict)
        return verdict

    # ── the confirmation gate ────────────────────────────────────────────────
    async def enforce(self, intent: MoneyIntent, ctx: Any = None) -> tuple[bool, GuardrailVerdict]:
        """Evaluate an intent and, when required, obtain a single-use approval."""
        verdict = self.evaluate_and_record(intent)

        if verdict.decision == DENY:
            await self._emit(ctx, "money_guardrail.blocked", {
                "action": intent.action, "reasons": verdict.reasons,
                "rules": verdict.rules, "intent": intent.to_dict(),
            })
            return False, verdict
        if verdict.decision == ALLOW:
            return True, verdict

        approvals = getattr(ctx, "approvals", None) or self.approvals
        if approvals is None:
            return False, verdict

        key, digest = intent.key, intent.digest

        # Retry path: an operator already approved this exact intent (and the
        # cooling-off period has elapsed). Consumption is single-use.
        try:
            active = approvals.find_active_kind("money_guardrail", key, digest)
        except Exception:  # noqa: BLE001 - store failure must fail closed
            active = None
        if active is not None:
            if not self._cooling_met(active, verdict):
                await self._emit(ctx, "money_guardrail.cooling", {
                    "action": intent.action,
                    "remainingSeconds": self._cooling_remaining(active, verdict),
                })
                return False, verdict
            try:
                if approvals.consume_kind(
                    kind="money_guardrail", request_key=key, digest=digest
                ) is not None:
                    await self._emit(ctx, "money_guardrail.approved", {
                        "action": intent.action, "approvalId": active.get("id"),
                    })
                    return True, verdict
            except Exception:  # noqa: BLE001
                return False, verdict

        pending = self._request(approvals, intent, verdict)
        await self._emit(ctx, "approval.requested", {
            "approvalId": (pending or {}).get("id"),
            "kind": "money_guardrail",
            "title": f"Confirm {intent.action.replace('_', ' ')}",
            "summary": self._summary(intent, verdict),
            "effect": "external_action",
            "risk": verdict.risk,
            "challenge": verdict.challenge(),
            "grantPattern": None,
        })

        if pending is not None and bool(getattr(ctx, "pause_for_approval", False)):
            from ..mcp.approvals import pause_for_decision  # noqa: PLC0415

            approved = await pause_for_decision(
                approvals, ctx, pending.get("id"),
                lambda: approvals.consume_kind(
                    kind="money_guardrail", request_key=key, digest=digest
                ),
                emitter=getattr(ctx, "emitter", None), digest=digest,
                event_type="money_guardrail.approved",
                approved_payload={"kind": "money_guardrail", "action": intent.action},
            )
            if approved:
                decided = self._row(approvals, pending.get("id")) or pending
                if not self._cooling_met(decided, verdict):
                    await self._emit(ctx, "money_guardrail.cooling", {
                        "action": intent.action,
                        "remainingSeconds": self._cooling_remaining(decided, verdict),
                    })
                    return False, verdict
                return True, verdict

        return False, verdict

    def _request(self, approvals: Any, intent: MoneyIntent, verdict: GuardrailVerdict) -> Optional[dict[str, Any]]:
        try:
            return approvals.request_kind(
                kind="money_guardrail",
                request_key=intent.key,
                digest=intent.digest,
                effect="external_action",
                run_id=intent.run_id or None,
                action_summary=self._summary(intent, verdict),
                affected_data=json.dumps(verdict.challenge(), sort_keys=True, default=str),
                risk="critical" if verdict.risk == "critical" else "high",
                ttl_seconds=3600,
            )
        except Exception:  # noqa: BLE001 - fail closed
            return None

    def _row(self, approvals: Any, approval_id: Optional[str]) -> Optional[dict[str, Any]]:
        if not approval_id:
            return None
        try:
            return approvals.get(approval_id)
        except Exception:  # noqa: BLE001
            return None

    # ── cooling-off ──────────────────────────────────────────────────────────
    def _cooling_met(self, row: Optional[dict[str, Any]], verdict: GuardrailVerdict) -> bool:
        if verdict.cooling_off_seconds <= 0:
            return True
        return self._cooling_remaining(row, verdict) <= 0

    def _cooling_remaining(self, row: Optional[dict[str, Any]], verdict: GuardrailVerdict) -> int:
        created = _parse_iso((row or {}).get("createdAt"))
        if created is None:
            return verdict.cooling_off_seconds
        elapsed = (datetime.now(timezone.utc) - created).total_seconds()
        return max(0, int(verdict.cooling_off_seconds - elapsed))

    # ── helpers ──────────────────────────────────────────────────────────────
    def _summary(self, intent: MoneyIntent, verdict: GuardrailVerdict) -> str:
        bits = [f"{intent.action.replace('_', ' ')}"]
        if intent.amount is not None:
            bits.append(f"{intent.amount:,.2f} {intent.currency}")
        if intent.instrument:
            bits.append(f"({intent.instrument})")
        if intent.counterparty:
            bits.append(f"to {intent.counterparty}")
        head = " ".join(bits)
        if not verdict.reasons:
            return head
        return f"{head}. " + " ".join(verdict.reasons[:3])

    async def _emit(self, ctx: Any, event_type: str, payload: dict[str, Any]) -> None:
        emitter = getattr(ctx, "emitter", None) if ctx is not None else None
        emit = getattr(emitter, "emit", None)
        if emit is None:
            return
        try:
            await emit(event_type, payload)
        except Exception:  # noqa: BLE001 - telemetry must never change a decision
            pass

    # ── handler-level helper ─────────────────────────────────────────────────
    def assess_tool(self, name: str, args: dict[str, Any], *, effect: Optional[str] = None,
                    run_id: str = "", text: str = "") -> Optional[GuardrailVerdict]:
        intent = intent_from_tool(name, args, effect=effect, run_id=run_id, text=text)
        if intent is None:
            return None
        return self.evaluate_and_record(intent)


__all__ = ["FinanceGuardrailService"]
