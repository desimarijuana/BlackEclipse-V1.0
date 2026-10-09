"""Compensating actions — undoing a side effect when a repair was wrong.

`OperationLedger` records WHAT to compensate; this module performs it. For every
operation that declared a `compensatingAction` and is not yet compensated, it
looks up the registered handler, checks the autonomy envelope authorizes the
`COMPENSATE` action class, runs the handler, and marks the operation compensated.

It never invents a compensation: an operation with no registered handler stays
pending and is reported. A handler that fails leaves the operation pending and
records the error. This is deliberately caller-driven — the runtime cannot know
how to undo an arbitrary external effect, so the caller registers the handler per
compensating action, inside the normal security boundary.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional

from .envelope import AutonomyEnvelope
from .policy import RecoveryStrategy

CompensationHandler = Callable[[dict[str, Any]], Any]


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


async def compensate_pending(
    service: Any,
    handlers: dict[str, CompensationHandler],
    *,
    envelope: Optional[AutonomyEnvelope] = None,
    limit: int = 50,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, Any]:
    """Compensate every pending operation that has a handler and is permitted."""
    active_envelope = envelope if envelope is not None else getattr(service, "envelope", None)
    compensated: list[str] = []
    skipped: list[dict[str, Any]] = []

    for operation in service.operations.pending_compensations(limit=limit):
        action = operation.get("compensatingAction")
        handler = handlers.get(action) if action else None
        if handler is None:
            skipped.append({"id": operation["id"], "reason": "no handler", "action": action})
            continue
        if active_envelope is not None:
            decision = active_envelope.check(RecoveryStrategy.COMPENSATE, reversible=True, risk="low")
            if not decision.allowed:
                skipped.append({"id": operation["id"], "reason": "outside envelope", "action": action})
                continue
        try:
            await _maybe_await(handler(operation))
            service.operations.compensate(operation["id"], result={"compensated": True})
            compensated.append(operation["id"])
        except BaseException as exc:  # noqa: BLE001 - a failed compensation stays pending
            service.operations.fail(operation["id"], result={"error": str(exc)})
            skipped.append({"id": operation["id"], "reason": "handler failed", "error": str(exc)})

    return {"compensated": compensated, "skipped": skipped}


__all__ = ["CompensationHandler", "compensate_pending"]