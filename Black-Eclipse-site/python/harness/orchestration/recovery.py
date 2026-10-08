"""Crash recovery for interrupted executions.

Completed nodes stay COMPLETED; a node that was RUNNING when the process died is
reset to PENDING (attempts preserved) and re-run once its dependencies are
satisfied. Recovery is idempotent — a finished execution is skipped.

Agent nodes need model credentials, which the runtime resolves per run and never
persists. When no credentialed runtime is available, an execution containing agent
nodes is PARKED (`PAUSED`, `metadata.awaitingRuntime`) and reported via
`EXECUTION_AWAITING_RUNTIME` instead of failing its agent work. The front door
resumes it with credentials; no completed work is thrown away.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .events import EXECUTION_AWAITING_RUNTIME, EXECUTION_STARTED
from .models import ExecutionStatus, NodeKind, TaskStatus, now

log = logging.getLogger("harness.orchestration.recovery")

_TERMINAL = (
    ExecutionStatus.COMPLETED,
    ExecutionStatus.FAILED,
    ExecutionStatus.CANCELLED,
    ExecutionStatus.PARTIAL_SUCCESS,
)


def needs_runtime(graph: Any, runtime: Any) -> bool:
    """True when an execution has agent nodes and no model settings available."""
    if getattr(runtime, "model_settings", None) is not None:
        return False
    return any(node.kind is NodeKind.AGENT for node in graph.nodes.values())


async def recover_engine(engine: Any, runtime: Any = None, *, timeout_ms: Optional[int] = None) -> list[str]:
    """Re-drive every interrupted execution. Returns the affected execution ids."""
    recovered: list[str] = []
    for execution_id in engine.store.recoverable_executions():
        existing = engine._executions.get(execution_id)  # noqa: SLF001
        if existing is not None and not existing.done.is_set():
            continue
        graph = engine.store.get_execution(execution_id)
        if graph is None or graph.status in _TERMINAL:
            continue
        effective = runtime or engine.runtime
        for lease in engine.store.active_leases(execution_id):
            engine.store.release_lease(lease["leaseId"])
        # Re-queue any node abandoned mid-run, whether this execution resumes now
        # or is parked for credentials.
        changed = False
        for node in graph.nodes.values():
            if node.status in (TaskStatus.RUNNING, TaskStatus.READY):
                engine._reset_node(node)  # noqa: SLF001
                engine.store.save_node(node)
                changed = True
        if needs_runtime(graph, effective):
            graph.status = ExecutionStatus.PAUSED
            graph.metadata["awaitingRuntime"] = True
            engine.store.save_execution(graph)
            engine._emit(execution_id, EXECUTION_AWAITING_RUNTIME, {  # noqa: SLF001
                "reason": "agent tasks need model credentials; resume with modelSettings",
            })
            recovered.append(execution_id)
            continue
        graph.status = ExecutionStatus.RUNNING
        graph.started_at = graph.started_at or now()
        graph.completed_at = None
        engine.store.save_execution(graph)
        engine._emit(execution_id, EXECUTION_STARTED, {"recovered": True})  # noqa: SLF001
        recovered.append(execution_id)
        if not changed and all(node.terminal for node in graph.nodes.values()):
            await engine._finalize_recovered(graph)  # noqa: SLF001
            continue
        await engine.execute(execution_id, runtime=runtime, timeout_ms=timeout_ms)
    return recovered


__all__ = ["needs_runtime", "recover_engine"]
