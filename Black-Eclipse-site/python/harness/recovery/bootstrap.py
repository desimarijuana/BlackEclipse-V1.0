"""Boot wiring for the recovery engine.

Construction installs the service + the read tools. Startup attaches a durable
subscription to the canonical Event System so a failure emitted by ANY subsystem
(`tool.failed`, `run.failed`, `task.failed`, …) is classified and recorded as an
incident. The subscription is bounded by the Event System's own loop guard and by
the recovery budget, so it can never spin.

Everything is best-effort and additive: a missing event system, memory store or
flag only means the engine records nothing — it never blocks boot or changes a
run's outcome.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .config import recovery_enabled
from .service import RecoveryService
from .tools import register_recovery_tools, set_recovery_service

log = logging.getLogger("harness.recovery")

# The failure event types the engine listens to (a subset of the canonical
# registry's failure vocabulary). Kept here so the engine owns its own filter.
_FAILURE_TYPES = (
    "tool.failed",
    # Round 4: a constructed request could not be satisfied by the catalog and
    # was escalated; the incident records the gap so the self-repair loop can
    # diagnose it. It is a failure of the route, not of the user's request.
    "ui.capability_gap",
    "run.failed",
    "task.failed",
    "agent.failed",
    "workflow.failed",
    "plugin.failed",
    "automation.failed",
    "process.failed",
    "research.failed",
    "backtest.failed",
)

_SUBS: list[Any] = []


def install_recovery_layer(service: Any) -> Optional[RecoveryService]:
    """Construct the recovery service + tools. Never raises."""
    memory_store = getattr(service, "memory_store", None)
    if memory_store is None:
        service.recovery = None
        log.warning("recovery engine unavailable: no eclipse-memory store")
        return None
    try:
        from .discovery import build_default_index  # noqa: PLC0415

        capability_index = build_default_index(service)
    except Exception:  # noqa: BLE001 - discovery is optional
        capability_index = None
    try:
        from .envelope import load_envelope  # noqa: PLC0415
        from .probes import register_default_probes  # noqa: PLC0415

        recovery = RecoveryService(
            memory_store,
            capability_index=capability_index,
            envelope=load_envelope(),
        )
        register_default_probes(recovery.diagnosis, service)
        service.recovery = recovery
        set_recovery_service(recovery)
        register_recovery_tools(service.registry)
        return recovery
    except Exception:  # noqa: BLE001 - recovery must never block boot
        service.recovery = None
        log.warning("recovery engine unavailable", exc_info=True)
        return None


def _event_system(service: Any) -> Any:
    for attr in ("events", "_event_system"):
        system = getattr(service, attr, None)
        if system is not None and hasattr(system, "subscribe"):
            return system
    return None


async def start_recovery(service: Any) -> None:
    """Subscribe to failure events. Best-effort; never raises."""
    recovery = getattr(service, "recovery", None)
    if recovery is None or not recovery_enabled():
        return
    system = _event_system(service)
    if system is None:
        log.info("recovery engine: no event system; incident capture disabled")
        return
    try:
        sub = system.subscribe(
            _FAILURE_TYPES,
            _make_handler(recovery),
            consumer_id="recovery.incidents",
            idempotent=True,
        )
        _SUBS.append((system, sub))
    except Exception:  # noqa: BLE001 - subscription is best-effort
        log.warning("recovery event subscription failed", exc_info=True)


async def stop_recovery(_service: Any) -> None:
    while _SUBS:
        system, sub = _SUBS.pop()
        try:
            system.bus.unsubscribe(sub)
        except Exception:  # noqa: BLE001
            pass


def _make_handler(recovery: RecoveryService):
    async def _on_failure(event: Any) -> None:
        if getattr(event, "replay", False):
            return
        payload = getattr(event, "payload", None) or {}
        if not isinstance(payload, dict):
            payload = {}
        details: dict[str, Any] = {
            "eventType": event.type, "eventId": getattr(event, "id", None),
        }
        # Round 4: carry the routing facts as diagnosis evidence (booleans only;
        # the request text stays in `message`).
        for src, dst in (
            ("capabilityGap", "capability_gap"),
            ("vocabularyGap", "vocabulary_gap"),
            ("capabilityAbsent", "capability_absent"),
            ("policyDenied", "policy_denied"),
        ):
            if src in payload:
                details[dst] = bool(payload[src])
        try:
            recovery.record_failure(
                code=str(payload.get("code") or payload.get("errorCode") or event.type),
                message=str(payload.get("message") or payload.get("error") or ""),
                subsystem=str(
                    payload.get("tool") or payload.get("subsystem")
                    or getattr(event, "source", None) or "harness"
                ),
                source="event",
                location=payload.get("tool"),
                run_id=payload.get("runId") or payload.get("run_id"),
                task_id=getattr(event, "task_id", None),
                details=details,
            )
        except Exception:  # noqa: BLE001 - capture must never break the bus
            log.debug("recovery incident capture failed", exc_info=True)

    return _on_failure


__all__ = ["install_recovery_layer", "start_recovery", "stop_recovery"]
