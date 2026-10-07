"""Runtime observability — status, list, logs, events, metrics, metrics history.

Extracted from `manager.py` so the orchestrator stays bounded. These are thin
read-only functions over an `ApplicationRuntimeManager`: they read the in-memory
runtime table, the shared `ApplicationRuntimeStore` and the terminal process
manager. No lifecycle, no execution — pure observation.
"""

from __future__ import annotations

import time
from typing import Any, Optional


def status(manager: Any, runtime_id: str) -> dict[str, Any]:
    handle = manager._runtimes.get(runtime_id)  # noqa: SLF001 - the manager is ours
    if handle is None:
        if manager.store is not None:
            row = manager.store.get_runtime(runtime_id)
            if row is not None:
                return {"status": "ok", "runtime": row, "live": False}
        return {"status": "not_found", "runtimeId": runtime_id}
    return {"status": "ok", "runtime": handle.to_dict(), "live": True}


def list_runtimes(manager: Any, *, state: Optional[str] = None) -> list[dict[str, Any]]:
    handles = list(manager._runtimes.values())  # noqa: SLF001
    if state:
        handles = [h for h in handles if h.state.value == state]
    return [h.to_dict() for h in handles]


def logs(
    manager: Any,
    runtime_id: str,
    *,
    tail: int = 200,
    stream: Optional[str] = None,
    service: str = "",
    filter_text: str = "",
    severity: str = "",
    errors_only: bool = False,
    max_lines: int = 2000,
) -> dict[str, Any]:
    """Read a runtime's output, bounded and filterable.

    `filter_text` keeps lines containing a substring; `errors_only` keeps only lines
    that look like errors; `severity` filters by a matched severity token.
    `max_lines` bounds the total returned so a chatty service cannot flood the
    caller's context. Every stream keeps its own `processId`/`status`.
    """
    from .manager import _filter_lines

    handle = manager._runtimes.get(runtime_id)  # noqa: SLF001
    if handle is None:
        return {"status": "not_found", "runtimeId": runtime_id}
    lines: list[dict[str, Any]] = []
    total_lines = 0
    truncated = False
    needle = str(filter_text or "").casefold()
    for process_id in handle.processes:
        window = manager.terminal.read_process_output(process_id, tail=tail, stream=stream) if manager.terminal is not None else None
        if not window:
            continue
        text = window.get("text", "") or ""
        kept = _filter_lines(text, needle=needle, errors_only=errors_only, severity=severity)
        total_lines += len(text.splitlines())
        if sum(len(s["lines"]) for s in lines) + len(kept) > max_lines:
            room = max(0, max_lines - sum(len(s["lines"]) for s in lines))
            kept = kept[:room]
            truncated = True
        if kept:
            lines.append({
                "processId": process_id, "status": window.get("status", ""),
                "lines": kept, "text": "\n".join(kept),
            })
    return {
        "status": "ok", "runtimeId": runtime_id, "streams": lines, "tail": tail,
        "totalLines": total_lines, "truncated": truncated,
        "filters": {"filterText": filter_text, "errorsOnly": errors_only, "severity": severity, "service": service},
    }


def events(manager: Any, runtime_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
    if manager.store is None:
        return []
    return manager.store.list_events(runtime_id, limit=limit)


def metrics(manager: Any, runtime_id: str) -> dict[str, Any]:
    """Point-in-time resource usage for the runtime's processes (persists a sample)."""
    from ..telemetry import sample_tree

    handle = manager._runtimes.get(runtime_id)  # noqa: SLF001
    if handle is None:
        return {"status": "not_found", "runtimeId": runtime_id}
    process_metrics: list[dict[str, Any]] = []
    if manager.terminal is not None:
        for process_id in handle.processes:
            info = manager.terminal.get_process(process_id)
            if info is None:
                continue
            pid = info.get("pid")
            usage = sample_tree(int(pid)) if pid else None
            process_metrics.append({
                "processId": process_id, "pid": pid, "state": info.get("state"),
                "cpuMs": getattr(usage, "cpu_ms", None) if usage else None,
                "memoryMb": getattr(usage, "memory_mb", None) if usage else None,
                "processCount": getattr(usage, "process_count", None) if usage else None,
            })
    result = {
        "status": "ok", "runtimeId": runtime_id,
        "uptimeS": max(0.0, time.time() - (handle.started_at or time.time())),
        "restartCount": handle.restart_count,
        "health": handle.health.to_dict(),
        "processes": process_metrics,
        "ports": [p.to_dict() for p in handle.ports],
    }
    if manager.store is not None:
        try:
            cpu_values = [p["cpuMs"] for p in process_metrics if p["cpuMs"] is not None]
            mem_values = [p["memoryMb"] for p in process_metrics if p["memoryMb"] is not None]
            count_values = [p["processCount"] for p in process_metrics if p["processCount"] is not None]
            manager.store.record_metric(
                runtime_id,
                cpu_ms=(sum(cpu_values) if cpu_values else None),
                memory_mb=(sum(mem_values) if mem_values else None),
                process_count=(sum(count_values) if count_values else None),
                uptime_s=result["uptimeS"],
                restart_count=handle.restart_count,
                health=handle.health.status.value if handle.health else "",
            )
            manager.store.prune_metrics(runtime_id, keep=500)
        except Exception:  # noqa: BLE001 - metrics persistence must not break a read
            pass
    return result


def metrics_history(manager: Any, runtime_id: str, *, limit: int = 200) -> dict[str, Any]:
    """The recent metric samples + a bounded trend summary for a runtime."""
    from .manager import _trend

    if manager.store is None:
        return {"status": "ok", "runtimeId": runtime_id, "samples": [], "trend": {}}
    samples = manager.store.metric_history(runtime_id, limit=limit)
    return {"status": "ok", "runtimeId": runtime_id, "samples": samples, "trend": _trend(samples)}


__all__ = ["events", "list_runtimes", "logs", "metrics", "metrics_history", "status"]
