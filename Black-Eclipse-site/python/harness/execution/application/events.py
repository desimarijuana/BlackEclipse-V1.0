"""Runtime events — a machine-readable vocabulary for the application runtime.

Events are emitted through a small emitter that (a) persists each event to the
runtime store and (b) publishes it on the process-wide harness `EventBus` so live
SSE subscribers see it. The event NAMES are a closed set; the payload is
structured data, never a free-text blob.

Every long-running process and container operation that changes state produces an
event here, so the runtime is observable without polling.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

# ── The closed event vocabulary ─────────────────────────────────────────────────
APPLICATION_DISCOVERED = "application.discovered"
APPLICATION_VALIDATED = "application.validated"
APPLICATION_VALIDATION_FAILED = "application.validation_failed"

DEPENDENCIES_INSTALLING = "dependencies.installing"
DEPENDENCIES_INSTALLED = "dependencies.installed"
DEPENDENCY_INSTALL_FAILED = "dependency.install_failed"

BUILD_STARTED = "build.started"
BUILD_COMPLETED = "build.completed"
BUILD_FAILED = "build.failed"

PROCESS_STARTED = "process.started"
PROCESS_STOPPED = "process.stopped"
PROCESS_EXITED = "process.exited"
PROCESS_CRASHED = "process.crashed"

CONTAINER_STARTED = "container.started"
CONTAINER_STOPPED = "container.stopped"
CONTAINER_CRASHED = "container.crashed"

HEALTH_CHECK_STARTED = "health_check.started"
HEALTH_CHECK_PASSED = "health_check.passed"
HEALTH_CHECK_FAILED = "health_check.failed"

RUNTIME_STARTED = "runtime.started"
RUNTIME_STOPPED = "runtime.stopped"
RUNTIME_FAILED = "runtime.failed"
RUNTIME_RECONCILED = "runtime.reconciled"
RUNTIME_DEGRADED = "runtime.degraded"
RUNTIME_RECOVERY_ATTEMPT = "runtime.recovery_attempt"
RUNTIME_RECOVERY_COMPLETED = "runtime.recovery_completed"

DEPLOYMENT_STARTED = "deployment.started"
DEPLOYMENT_COMPLETED = "deployment.completed"
DEPLOYMENT_FAILED = "deployment.failed"

#: Every event name the runtime can emit. A test asserts this is closed.
EVENT_NAMES: frozenset[str] = frozenset(
    {
        APPLICATION_DISCOVERED, APPLICATION_VALIDATED, APPLICATION_VALIDATION_FAILED,
        DEPENDENCIES_INSTALLING, DEPENDENCIES_INSTALLED, DEPENDENCY_INSTALL_FAILED,
        BUILD_STARTED, BUILD_COMPLETED, BUILD_FAILED,
        PROCESS_STARTED, PROCESS_STOPPED, PROCESS_EXITED, PROCESS_CRASHED,
        CONTAINER_STARTED, CONTAINER_STOPPED, CONTAINER_CRASHED,
        HEALTH_CHECK_STARTED, HEALTH_CHECK_PASSED, HEALTH_CHECK_FAILED,
        RUNTIME_STARTED, RUNTIME_STOPPED, RUNTIME_FAILED, RUNTIME_RECONCILED,
        RUNTIME_DEGRADED, RUNTIME_RECOVERY_ATTEMPT, RUNTIME_RECOVERY_COMPLETED,
        DEPLOYMENT_STARTED, DEPLOYMENT_COMPLETED, DEPLOYMENT_FAILED,
    }
)


class RuntimeEventEmitter:
    """Persist + publish runtime events. Every method is exception-safe."""

    def __init__(self, *, store: Any = None, bus: Any = None, run_id: str = "") -> None:
        self._store = store
        self._bus = bus
        self._run_id = run_id

    def emit(self, runtime_id: str, event_type: str, data: Optional[dict[str, Any]] = None, *,
             severity: str = "info", message: str = "") -> dict[str, Any]:
        event = {
            "runtimeId": runtime_id,
            "type": event_type,
            "data": data or {},
            "severity": severity,
            "message": message,
        }
        if self._store is not None:
            try:
                self._store.append_event(runtime_id, event_type, data, severity=severity, message=message)
            except Exception:  # noqa: BLE001 - persistence must never break a runtime op
                pass
        if self._bus is not None:
            try:
                import time

                self._bus.publish({
                    "type": f"runtime.{event_type}" if not event_type.startswith("runtime") else event_type,
                    "runId": self._run_id or (data or {}).get("runId"),
                    "data": {"runtimeId": runtime_id, "event": event_type, **(data or {})},
                    "at": time.time(),
                })
            except Exception:  # noqa: BLE001
                pass
        return event


def make_emitter(*, store: Any = None, bus: Any = None, run_id: str = "") -> RuntimeEventEmitter:
    return RuntimeEventEmitter(store=store, bus=bus, run_id=run_id)


__all__ = [
    "APPLICATION_DISCOVERED",
    "APPLICATION_VALIDATED",
    "APPLICATION_VALIDATION_FAILED",
    "BUILD_COMPLETED",
    "BUILD_FAILED",
    "BUILD_STARTED",
    "CONTAINER_CRASHED",
    "CONTAINER_STARTED",
    "CONTAINER_STOPPED",
    "DEPENDENCIES_INSTALLED",
    "DEPENDENCIES_INSTALLING",
    "DEPENDENCY_INSTALL_FAILED",
    "DEPLOYMENT_COMPLETED",
    "DEPLOYMENT_FAILED",
    "DEPLOYMENT_STARTED",
    "EVENT_NAMES",
    "HEALTH_CHECK_FAILED",
    "HEALTH_CHECK_PASSED",
    "HEALTH_CHECK_STARTED",
    "PROCESS_CRASHED",
    "PROCESS_EXITED",
    "PROCESS_STARTED",
    "PROCESS_STOPPED",
    "RUNTIME_DEGRADED",
    "RUNTIME_FAILED",
    "RUNTIME_RECONCILED",
    "RUNTIME_RECOVERY_ATTEMPT",
    "RUNTIME_RECOVERY_COMPLETED",
    "RUNTIME_STARTED",
    "RUNTIME_STOPPED",
    "RuntimeEventEmitter",
    "make_emitter",
]
