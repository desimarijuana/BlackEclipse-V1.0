"""Code Intelligence & Understanding Engine (CIUE) routes.

Read-only inspection plus an operator-gated index trigger. The engine itself is
reached through the agent tools; these routes exist so an operator (or the front
door) can observe what CIUE has — the index size, the project shape, the running
language tools — without a run. Every mutation is operator-gated (transport/token),
mirroring the other code routes. Shared state comes from `harness.deps`; this module
never imports `main`.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..deps import require_operator, service

router = APIRouter(tags=["code-intel"])


def _runtime():
    runtime = getattr(service, "code_intel", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="code intelligence is unavailable")
    return runtime


def _workspace():
    from ..code.workspace import resolve_workspace  # noqa: PLC0415

    ws = resolve_workspace(None)
    if ws is None:
        raise HTTPException(status_code=503, detail="no workspace root")
    return ws


@router.get("/code/intel/status")
def code_intel_status(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Read-only: the process-wide CIUE runtime status (no secrets)."""
    from ..code.intel.config import load_config  # noqa: PLC0415

    runtime = _runtime()
    payload = {"success": True, **runtime.status()}
    payload.setdefault("config", load_config().to_dict())
    return payload


@router.get("/code/intel/project")
def code_intel_project(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Read-only: the resolved project's languages, frameworks and structure."""
    runtime = _runtime()
    manager = runtime.manager_for(_workspace())
    return {"success": True, "project": manager.detect_project(), "structure": manager.get_project_structure()}


@router.post("/code/intel/index")
def code_intel_index(force: bool = False, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Index (or re-index) the server-resolved workspace. Idempotent and incremental."""
    runtime = _runtime()
    return {"success": True, **runtime.ensure_indexed(_workspace(), force=force)}


@router.post("/code/intel/servers/start")
def code_intel_start_servers(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Start a language server for each detected language (best-effort per language)."""
    runtime = _runtime()
    ws = _workspace()
    return {"success": True, "servers": runtime.start_language_servers(ws)}


@router.post("/code/intel/servers/stop")
def code_intel_stop_servers(_: bool = Depends(require_operator)) -> dict[str, Any]:
    runtime = _runtime()
    stopped = runtime.lsp.stop_all()
    return {"success": True, "stopped": stopped}


@router.post("/code/intel/servers/{language}/restart")
def code_intel_restart_server(language: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    runtime = _runtime()
    ws = _workspace()
    try:
        return {"success": True, **runtime.manager_for(ws).restart_language_server(language)}
    except Exception as exc:  # noqa: BLE001 - a restart failure is an honest 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc


__all__ = ["router"]
