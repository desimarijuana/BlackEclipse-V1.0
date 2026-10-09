"""Automatic strategy execution — the engine acts, within its budget.

The controller *decides*; this module *executes* the auto-executable part of that
decision for a caller's operation. It is bounded by the same `RecoveryBudget`, so
it can never spin: each iteration consults the controller, and a `stop`/`suspend`
or a strategy with no handler ends the loop.

What it auto-executes:

  * `RETRY` / `RATE_LIMIT_BACKOFF` — wait the controller's backoff, then run the
    operation again.
  * any strategy the caller registered a handler for (a `strategy_handlers` map),
    e.g. a repair-input or substitute-provider action that mutates state before
    the retry. The handler runs inside the caller's own security boundary; this
    module never bypasses it.

What it deliberately does NOT do: invent a repair, run a tool, or touch security.
A strategy with no handler (and not retry/backoff) ends the loop and is returned
to the caller as the decision to act on. Every attempt and outcome is recorded on
the incident through the SAME service/store the rest of the runtime uses.

Success is defined by an OPTIONAL `verify` callable, never by "no exception": a
run that completes but fails verification is a failure and is treated as such
(spec §5.3, §6.3).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .envelope import AutonomyEnvelope
from .policy import RecoveryStrategy
from .taxonomy import normalize_failure

# Awaitable-or-not helpers.
Operation = Callable[[], Awaitable[Any]]
Verify = Callable[[Any], Any]
StrategyHandler = Callable[[dict[str, Any]], Any]

_AUTO_STRATEGIES = frozenset({"retry", "rate_limit_backoff"})


class VerificationFailed(Exception):
    """Raised internally when an operation completes but fails verification."""


@dataclass
class RecoveryRunResult:
    ok: bool
    value: Any = None
    attempts: int = 0
    incident_id: Optional[str] = None
    decision: Optional[dict[str, Any]] = None
    stopped_reason: Optional[str] = None
    diagnosis: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "attempts": self.attempts,
            "incidentId": self.incident_id,
            "decision": self.decision,
            "stoppedReason": self.stopped_reason,
            "diagnosis": self.diagnosis,
        }


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


async def recover_operation(
    service: Any,
    operation: Operation,
    *,
    verify: Optional[Verify] = None,
    classifier: Optional[Callable[[BaseException], Any]] = None,
    strategy_handlers: Optional[dict[str, StrategyHandler]] = None,
    envelope: Optional[AutonomyEnvelope] = None,
    subsystem: str = "harness",
    source: str = "operation",
    task_id: Optional[str] = None,
    run_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    max_attempts: Optional[int] = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> RecoveryRunResult:
    """Run `operation`, recovering automatically within the budget.

    `service` is a `RecoveryService`. `classifier(exc)` optionally maps an
    exception to a `(code, message)`-bearing object; by default the exception
    type and text are used. `verify(value)` returns truthy for success.
    """
    budget_max = max_attempts or service.controller.budget.max_attempts
    handlers = strategy_handlers or {}
    active_envelope = envelope if envelope is not None else getattr(service, "envelope", None)
    incident_id: Optional[str] = None
    last_decision: Optional[dict[str, Any]] = None
    diagnosis: Optional[dict[str, Any]] = None
    attempts = 0

    while attempts < max(1, budget_max):
        attempts += 1
        try:
            value = await operation()
            if verify is not None and not await _maybe_await(verify(value)):
                raise VerificationFailed("operation completed but failed verification")
        except BaseException as exc:  # noqa: BLE001 - every failure is data here
            if classifier is not None:
                classified = classifier(exc)
                code = str(getattr(classified, "code", None) or getattr(classified, "error_class", None) or type(exc).__name__)
                message = str(getattr(classified, "message", None) or exc)
            else:
                code = type(exc).__name__
                message = str(exc)

            if incident_id is None:
                recorded = service.record_failure(
                    code=code, message=message, subsystem=subsystem, source=source,
                    task_id=task_id, run_id=run_id,
                    details={**(details or {}), "attempt": attempts},
                )
                incident_id = recorded["incidentId"]
                last_decision = recorded["decision"]
                diagnosis = recorded.get("diagnosis")
            else:
                failure = normalize_failure(
                    code=code, message=message, subsystem=subsystem, source=source,
                    details=details,
                )
                prior = service.store.find_incident(failure.signature, task_id=task_id) or {}
                # Within ONE bounded loop, retry stays available: the budget bound
                # (max_attempts) is the limit here. Cross-incident recurrence is
                # already reflected in the first decision (record_failure).
                last_decision = service.controller.decide(
                    failure,
                    attempts=int(prior.get("attempts", attempts)),
                    signature_attempts=0,
                    recurrent=False,
                ).to_dict()

            action = last_decision.get("action")
            strategy = last_decision.get("strategy")
            if action == "stop" or action == "suspend":
                service.record_outcome(incident_id, outcome="failed", detail={"reason": action})
                return RecoveryRunResult(
                    ok=False, attempts=attempts, incident_id=incident_id,
                    decision=last_decision, diagnosis=diagnosis, stopped_reason=action,
                )

            if strategy not in _AUTO_STRATEGIES:
                handler = handlers.get(strategy)
                # A non-retry strategy runs unattended ONLY if the operator's
                # autonomy envelope authorizes its action class AND a handler
                # exists to perform it. Otherwise it is handed back to the caller.
                if handler is None or active_envelope is None:
                    service.record_outcome(
                        incident_id, outcome="failed",
                        detail={"reason": "not_auto_executable", "strategy": strategy},
                    )
                    return RecoveryRunResult(
                        ok=False, attempts=attempts, incident_id=incident_id,
                        decision=last_decision, diagnosis=diagnosis,
                        stopped_reason="strategy_requires_caller",
                    )
                try:
                    strategy_enum = RecoveryStrategy(strategy)
                except ValueError:
                    strategy_enum = None
                candidate = next(
                    (c for c in (last_decision.get("candidates") or []) if c.get("strategy") == strategy),
                    {},
                )
                env_decision = active_envelope.check(
                    strategy_enum,
                    reversible=bool(candidate.get("reversible", True)),
                    risk="medium" if candidate.get("requiresApproval") else "low",
                ) if strategy_enum is not None else None
                if env_decision is None or not env_decision.allowed:
                    # A one-off operator approval authorizes exactly this incident.
                    approved = False
                    try:
                        approved = service.has_approval(incident_id, str(strategy))
                    except Exception:  # noqa: BLE001 - absence of approval store is not approval
                        approved = False
                    if not approved:
                        reason = env_decision.reason if env_decision is not None else "no envelope"
                        service.record_outcome(
                            incident_id, outcome="failed",
                            detail={"reason": "outside_envelope", "strategy": strategy, "envelope": reason},
                        )
                        return RecoveryRunResult(
                            ok=False, attempts=attempts, incident_id=incident_id,
                            decision=last_decision, diagnosis=diagnosis,
                            stopped_reason="outside_autonomy_envelope",
                        )

            service.store.record_attempt(
                incident_id, attempt_no=attempts, action="recover", strategy=strategy,
                reason=last_decision.get("reason", ""),
                backoff_ms=int(last_decision.get("backoffMs", 0)), outcome="failed",
            )
            handler = handlers.get(strategy)
            if handler is not None:
                # Cross-worker coordination: only one worker repairs a given
                # failure signature at a time (advisory, expiring lease).
                lease_signature = ""
                lease_holder = f"{incident_id}:{attempts}"
                lease_ok = True
                try:
                    incident_row = service.get_incident(incident_id) or {}
                    lease_signature = incident_row.get("signature", "") or ""
                    if lease_signature:
                        lease_ok = service.store.acquire_lease(lease_signature, lease_holder, ttl_s=120)
                except Exception:  # noqa: BLE001 - lease is best-effort coordination
                    lease_ok = True
                if not lease_ok:
                    return RecoveryRunResult(
                        ok=False, attempts=attempts, incident_id=incident_id,
                        decision=last_decision, diagnosis=diagnosis,
                        stopped_reason="repair_lease_held",
                    )
                try:
                    # Durable idempotency: a resumed worker must not repeat a side
                    # effect that already completed. `begin` is idempotent on the key.
                    op_key = f"{incident_id}:{strategy}:{attempts}"
                    op_record = service.operations.begin(
                        op_key, kind=str(strategy), incident_id=incident_id,
                        request={"strategy": str(strategy)},
                    )
                    if not op_record.get("created", True) and op_record.get("status") == "completed":
                        pass  # already applied in a prior attempt — do not repeat
                    else:
                        try:
                            await _maybe_await(handler(last_decision))
                            service.operations.complete(op_record["id"], result={"applied": True})
                        except BaseException as handler_exc:  # noqa: BLE001
                            service.operations.fail(op_record["id"], result={"error": str(handler_exc)})
                            service.record_outcome(
                                incident_id, outcome="failed",
                                detail={"reason": "strategy_handler_failed", "strategy": str(strategy)},
                            )
                            return RecoveryRunResult(
                                ok=False, attempts=attempts, incident_id=incident_id,
                                decision=last_decision, diagnosis=diagnosis,
                                stopped_reason="strategy_handler_failed",
                            )
                finally:
                    if lease_signature:
                        try:
                            service.store.release_lease(lease_signature, lease_holder)
                        except Exception:  # noqa: BLE001
                            pass
            backoff_ms = int(last_decision.get("backoffMs", 0) or 0)
            if backoff_ms > 0:
                await sleep(backoff_ms / 1000.0)
            continue

        # Success (operation returned AND verification passed, if any).
        if incident_id is not None:
            service.store.record_attempt(
                incident_id, attempt_no=attempts, action="recover",
                strategy=(last_decision or {}).get("strategy"), outcome="succeeded",
            )
            service.record_outcome(incident_id, outcome="succeeded")
        return RecoveryRunResult(
            ok=True, value=value, attempts=attempts, incident_id=incident_id,
            decision=last_decision, diagnosis=diagnosis,
        )

    if incident_id is not None:
        service.record_outcome(incident_id, outcome="exhausted")
    return RecoveryRunResult(
        ok=False, attempts=attempts, incident_id=incident_id,
        decision=last_decision, diagnosis=diagnosis, stopped_reason="budget_exhausted",
    )


__all__ = ["RecoveryRunResult", "StrategyHandler", "VerificationFailed", "recover_operation"]
