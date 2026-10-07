"""Workspace-level operations: start/stop/observe MANY applications in order.

Extracted from `manager.py` so the orchestrator stays under its size ceiling. These
are thin functions over an `ApplicationRuntimeManager`: they build the
cross-application graph and drive the existing `start`/`stop` lifecycle in
dependency order. No new lifecycle, no new execution path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from .models import ApplicationState


def app_graph(root: Path) -> dict[str, Any]:
    """The cross-application dependency graph under `root` (read-only)."""
    from .app_graph import build_application_graph

    return build_application_graph(Path(root)).to_dict()


def start_workspace(
    manager: Any,
    root: Path,
    *,
    workspace_id: Optional[str] = None,
    run_id: str = "",
    agent_id: Optional[str] = None,
    actor: Any = None,
    install: bool = True,
    build: bool = False,
    wait_ready: bool = True,
    emit: Optional[Callable[[str, dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    """Start EVERY application under `root`, in dependency order.

    Each application is started with `manager.start()` in the graph's
    `startupOrder` (a dependency starts before its dependent). A failure stops the
    sequence and reports exactly which app failed — later apps are not started, so
    the operator is never left with a half-built workspace.
    """
    from .app_graph import build_application_graph

    graph = build_application_graph(Path(root))
    order = graph.startup_order()
    handles: list[dict[str, Any]] = []
    for app_id in order:
        node = graph.nodes.get(app_id)
        if node is None:
            continue
        handle = manager.start(
            Path(node.root), name=node.name, workspace_id=workspace_id, run_id=run_id,
            agent_id=agent_id, actor=actor, install=install, build=build,
            wait_ready=wait_ready, emit=emit,
        )
        handles.append({"appId": app_id, **handle.to_dict()})
        if handle.state is ApplicationState.FAILED:
            return {
                "status": "failed", "failedApp": app_id, "startupOrder": order,
                "started": handles,
                "reason": (handle.last_error or {}).get("message", "an application could not start"),
            }
    return {"status": "ok", "startupOrder": order, "started": handles, "graph": graph.to_dict()}


def stop_workspace(manager: Any, root: Path, *, actor: Any = None) -> dict[str, Any]:
    """Stop every application under `root`, in REVERSE dependency order."""
    from .app_graph import build_application_graph

    graph = build_application_graph(Path(root))
    stopped: list[dict[str, Any]] = []
    for app_id in graph.stop_order():
        node = graph.nodes.get(app_id)
        if node is None:
            continue
        app_root = str(Path(node.root).resolve())
        for handle in list(manager._runtimes.values()):  # noqa: SLF001 - the manager is ours
            if handle.descriptor and str(Path(handle.descriptor.path).resolve()) == app_root:
                result = manager.stop(handle.runtime_id, actor=actor)
                stopped.append({"appId": app_id, **result})
    return {"status": "ok", "stopOrder": graph.stop_order(), "stopped": stopped}


__all__ = ["app_graph", "start_workspace", "stop_workspace"]
