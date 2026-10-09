"""The runtime's FastAPI lifespan (boot/shutdown wiring).

Extracted from `main.py` so the route surface and the subsystem start/stop
sequence are separate concerns (and `main.py` stays under its size ratchet). The
sequence is unchanged: each subsystem starts once on the first lifespan entry and
stops on the last exit, and every step is best-effort — a failure is a diagnostic,
never a boot blocker.

The service is process-wide, but FastAPI may enter/exit the lifespan more than
once (nested test clients, reload). Reference-count so only the LAST exit tears the
subsystems down — an inner lifespan must never disconnect the servers a sibling
still uses.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

from .deps import deployment_exposure, service

if TYPE_CHECKING:
    from fastapi import FastAPI

log = logging.getLogger("harness")

_lifespan_refs = 0


@asynccontextmanager
async def lifespan(_app: "FastAPI") -> AsyncIterator[None]:
    global _lifespan_refs
    _lifespan_refs += 1
    if _lifespan_refs == 1:
        await _boot()
    try:
        yield
    finally:
        _lifespan_refs -= 1
        if _lifespan_refs == 0:
            await _shutdown()


async def _boot() -> None:
    """Start every subsystem exactly once. Never a boot blocker."""
    # Deployment guard: this app is single-user local with NO authentication or
    # tenancy isolation. A non-loopback bind without an operator secret is flagged
    # loudly so the configuration is never mistaken for multi-user secure. It does
    # not block boot (a local dev bind is the normal case).
    exposure = deployment_exposure()
    if exposure.get("exposed"):
        log.warning("[harness-py] DEPLOYMENT WARNING: %s", exposure["warning"])
    # Retention: mark due AUTOMATIC memories expired on startup. Idempotent and
    # best-effort.
    service.run_startup_maintenance()
    # Failure Intelligence & Adaptive Recovery: construct the classifier/controller
    # and register its read-only inspection tools. Additive; capture itself is
    # wired after the Event System starts.
    from .recovery.bootstrap import install_recovery_layer

    install_recovery_layer(service)
    # Terminal subsystem recovery: reconcile persisted process/session rows.
    service.start_terminal()
    # Application Runtime reconciliation: re-examine the runtimes left by a
    # previous process.
    service.reconcile_application_runtime()
    # Code Intelligence & Understanding Engine (CIUE): warm the code index in the
    # background. Language servers start lazily on first use.
    service.start_code_intel()
    # Browser + Computer-Use runtimes: wire resolvers, start idle sweepers. No
    # browser/desktop is launched until a tool asks.
    service.start_browser()
    await service.start_browser_sweeper()
    service.start_computer()
    await service.start_computer_sweeper()
    # Connect configured MCP servers and register selected read-only tools.
    await service.start_mcp()
    # The bounded learning-review queue: reviews completed runs in the background.
    # It only creates inert records/suggestions and never enables a skill.
    await service.start_learning_review()
    # Native Automation Engine (ADR-H152): one durable scheduler/trigger router
    # beside the three TS refresh loops, which stay exactly as they are.
    await service.start_automation()
    # Event System: the durable event store + bus. Started AFTER the subsystems
    # that publish, so their legacy run-bus emissions are ingested from boot.
    from .event_system.bootstrap import start_events
    await start_events(service)
    # Failure Intelligence & Adaptive Recovery: subscribe to the now-live event
    # bus so failures from every subsystem are classified and recorded as durable
    # incidents. Bounded by the Event System's loop guard + the recovery budget.
    from .recovery.bootstrap import start_recovery

    await start_recovery(service)
    # The Task / Plan runtime: one durable scheduler task that claims runnable
    # tasks and dispatches each through the ordinary run path. Started after jobs
    # so a task-triggering job sees a live scheduler.
    await service.start_tasks()
    # The Artifact Center: a bounded background reconciler that repairs catalog/
    # storage inconsistencies (missing objects, recovered rows). Best-effort.
    await service.start_artifacts()
    # The Plugin Platform: reload every plugin enabled before the last shutdown.
    # Durable state means a restart restores the same active plugin set; a plugin
    # that fails to reload is quarantined as FAILED, never silently dropped.
    from .plugins.bootstrap import start_plugins

    await start_plugins(service)
    # Parallel execution & DAG orchestration: register the tools and recover any
    # execution left mid-flight by a previous process. Best-effort, never a boot
    # blocker.
    from .orchestration.bootstrap import install_orchestration_layer, recover_orchestration

    install_orchestration_layer(service)
    await recover_orchestration(service)
    # Agent-to-Agent: the versioned Agent Registry + durable Message Bus + budgets,
    # and the A2A tools. Delegated tasks are executed by the TaskScheduler above.
    from .a2a.bootstrap import install_a2a_layer, recover_a2a

    install_a2a_layer(service)
    recover_a2a(service)
    # Execution Fabric (ADR-H156): the durable queue + worker pool + execution-mode
    # router. Installed AFTER the subsystems it workers over (agent runtime,
    # tools, automation, events, plugins) so its event rules can subscribe to a
    # live Event System. It recovers any job left mid-flight by a previous process.
    from .fabric.bootstrap import install_fabric_layer, start_fabric

    install_fabric_layer(service)
    await start_fabric(service)
    # Unified search: build the vector/FTS index from existing sources in the
    # background (non-blocking). With no embedding provider this is an honest
    # keyword-only index; disabled by HARNESS_SEARCH_WARM_INDEX=0.
    search_layer = getattr(service, "search", None)
    if search_layer is not None:
        try:
            search_layer.schedule_warm_index()
        except Exception:  # noqa: BLE001 - warm-up must never block boot
            log.warning("[harness-py] search warm index skipped", exc_info=True)
    # Observability platform: report readiness once every subsystem is live.
    try:
        from .observability.integration import start_observability

        start_observability(service)
    except Exception:  # noqa: BLE001 - telemetry startup must never block boot
        log.warning("[harness-py] observability startup skipped", exc_info=True)
    # Security subsystem: attach the now-live event system + observability metrics
    # to the audit log (the gateway itself was installed at construction). Last so
    # every sink it reports into already exists.
    try:
        from .security.bootstrap import start_security

        await start_security(service)
    except Exception:  # noqa: BLE001 - security startup must never block boot
        log.warning("[harness-py] security startup skipped", exc_info=True)


async def _shutdown() -> None:
    """Stop every subsystem on the last exit. Cancel queued work and terminate
    subprocesses cleanly so none leak across restarts. Never raises."""
    from .plugins.bootstrap import stop_plugins

    await stop_plugins(service)
    # Flush + close telemetry sinks FIRST so terminal-job/plugin events reach a
    # live exporter before the bus is torn down.
    from .security.bootstrap import stop_security

    await stop_security(service)
    from .observability.integration import stop_observability

    stop_observability(service)
    # Drain the Execution Fabric BEFORE the event system so its terminal
    # publications still reach a live bus, releasing locks and cancelling work.
    from .fabric.bootstrap import stop_fabric

    await stop_fabric(service)
    # Detach the recovery subscription before the event bus is torn down.
    from .recovery.bootstrap import stop_recovery

    await stop_recovery(service)
    from .event_system.bootstrap import stop_events
    await service.stop_artifacts()
    await service.stop_tasks()
    await stop_events(service)
    await service.stop_automation()
    orchestration = getattr(service, "orchestration", None)
    if orchestration is not None:
        await orchestration.primary.shutdown()
    await service.stop_learning_review()
    await service.stop_code_intel()
    await service.stop_browser()
    await service.stop_computer()
    await service.stop_mcp()
    service.stop_application_runtime()
    service.stop_execution()
    await service.stop_terminal()


__all__ = ["lifespan"]
