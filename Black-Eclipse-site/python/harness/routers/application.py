"""Application Runtime HTTP routes — the UI surface over the shared engine.

Every route is `require_operator`, exactly like the execution and terminal
routers. Reads are operator-gated too: the runtime surface is powerful, so even
enumerating runtimes is not anonymous.

The routes are thin adapters over `harness.deps.service.application_runtime` — the
SAME manager the agent tools use, so UI and agent can never disagree.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["application"])


class StartRequest(BaseModel):
    name: str = Field(default="", max_length=200)
    install: bool = True
    build: bool = False
    useCompose: Optional[bool] = None  # noqa: N815
    waitReady: bool = True  # noqa: N815
    healthTimeoutS: float = Field(default=30.0, ge=1.0, le=600.0)  # noqa: N815


class RecoverRequest(BaseModel):
    maxAttempts: Optional[int] = Field(default=None, ge=1, le=10)  # noqa: N815


def _runtime():
    manager = getattr(service, "application_runtime", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="the application runtime is unavailable")
    return manager


def _workspace_root():
    from ..code.workspace import default_root, resolve_workspace

    ws = resolve_workspace(None)
    if ws is None:
        raise HTTPException(status_code=503, detail="no workspace root is selected")
    return default_root()


@router.get("/runtime/status")
def runtime_describe(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_runtime().describe()}


@router.get("/runtime/list")
def runtime_list(state: Optional[str] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "runtimes": _runtime().list(state=state)}


@router.get("/runtime/detect")
def runtime_detect(_: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..execution.application.environment import EnvironmentDetector

    return {"success": True, **EnvironmentDetector().detect()}


@router.get("/runtime/inspect")
def runtime_inspect(_: bool = Depends(require_operator)) -> dict[str, Any]:
    root = _workspace_root()
    return {"success": True, **_runtime().inspect(root)}


@router.post("/runtime/start")
def runtime_start(body: StartRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    root = _workspace_root()
    handle = _runtime().start(
        root, name=body.name, install=body.install, build=body.build,
        use_compose=body.useCompose, wait_ready=body.waitReady,
        health_timeout_s=body.healthTimeoutS,
    )
    return {"success": handle.state.value != "FAILED", "runtime": handle.to_dict()}


@router.get("/runtime/orchestrators")
def orchestrators(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "orchestrators": _runtime().registry.orchestrators.describe(),
            "infrastructure": _runtime().registry.infrastructure.describe(),
            "cloudProviders": _runtime().registry.deployments.describe()}


@router.get("/runtime/providers")
def runtime_providers(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """The provider install/auth readiness report (non-secret). Read-only."""
    return {"success": True, **_runtime().readiness()}


@router.get("/runtime/deploy/providers")
def deploy_providers(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "providers": _runtime().registry.deployments.describe()}


# NOTE: `GET /runtime/{runtime_id}` below is a catch-all for the id space. Every
# STATIC 2-segment `/runtime/...` GET route MUST be declared ABOVE it or FastAPI
# will match the catch-all first.
@router.get("/runtime/{runtime_id}")
def runtime_status(runtime_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _runtime().status(runtime_id)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such runtime")
    return {"success": True, **data}


@router.post("/runtime/{runtime_id}/stop")
def runtime_stop(runtime_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _runtime().stop(runtime_id)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such runtime")
    return {"success": True, **data}


@router.post("/runtime/{runtime_id}/restart")
def runtime_restart(runtime_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        handle = _runtime().restart(runtime_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="no such runtime") from exc
    return {"success": True, "runtime": handle.to_dict()}


@router.post("/runtime/{runtime_id}/cleanup")
def runtime_cleanup(runtime_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _runtime().cleanup(runtime_id)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such runtime")
    return {"success": True, **data}


@router.get("/runtime/{runtime_id}/health")
def runtime_health(runtime_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _runtime().status(runtime_id)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such runtime")
    return {"success": True, "health": data.get("runtime", {}).get("health", {})}


@router.get("/runtime/{runtime_id}/logs")
def runtime_logs(
    runtime_id: str,
    tail: int = 200,
    stream: Optional[str] = None,
    filter: str = "",
    severity: str = "",
    errorsOnly: bool = False,  # noqa: N803
    service: str = "",
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    data = _runtime().logs(runtime_id, tail=tail, stream=stream, filter_text=filter,
                           severity=severity, errors_only=errorsOnly, service=service)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such runtime")
    return {"success": True, **data}


@router.get("/runtime/{runtime_id}/metrics")
def runtime_metrics(runtime_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _runtime().metrics(runtime_id)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such runtime")
    return {"success": True, **data}


@router.get("/runtime/{runtime_id}/metrics/history")
def runtime_metrics_history(runtime_id: str, limit: int = 200, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """A runtime's metric samples + a trend summary. Read-only."""
    return {"success": True, **_runtime().metrics_history(runtime_id, limit=limit)}


@router.get("/runtime/{runtime_id}/events")
def runtime_events(runtime_id: str, limit: int = 200, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "events": _runtime().events(runtime_id, limit=limit)}


@router.get("/runtime/{runtime_id}/diagnose")
def runtime_diagnose(runtime_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _runtime().diagnose(runtime_id)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such runtime")
    return {"success": True, **data}


@router.post("/runtime/{runtime_id}/recover")
def runtime_recover(runtime_id: str, body: RecoverRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _runtime().recover(runtime_id, max_attempts=body.maxAttempts)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such runtime")
    return {"success": True, **data}


@router.post("/runtime/reconcile")
def runtime_reconcile(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_runtime().reconcile()}


# ── ports ─────────────────────────────────────────────────────────────────────


@router.get("/runtime/ports/list")
def port_list(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_runtime().ports.summary()}


@router.get("/runtime/ports/{port}")
def port_check(port: int, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_runtime().ports.check(port)}


# ── orchestration / infrastructure / cloud ────────────────────────────────────


class OrchestratorRequest(BaseModel):
    adapter: str = Field(default="", max_length=32)
    args: dict[str, Any] = Field(default_factory=dict)
    authorized: bool = False


class InfrastructureRequest(BaseModel):
    adapter: str = Field(default="", max_length=32)
    args: dict[str, Any] = Field(default_factory=dict)
    authorized: bool = False


class DeployRequest(BaseModel):
    provider: str = Field(default="", max_length=64)
    environment: str = Field(default="staging", max_length=32)
    service: str = Field(default="", max_length=255)
    install: bool = True
    build: bool = True
    test: bool = False
    args: dict[str, Any] = Field(default_factory=dict)
    authorized: bool = False


@router.post("/runtime/orchestrator/{operation}")
def run_orchestrator(operation: str, body: OrchestratorRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = _runtime()
    if operation in ("delete", "apply", "scale", "exec") and not body.authorized:
        raise HTTPException(status_code=403, detail="this operation requires the operator's authorization")
    result = manager.run_orchestrator(operation, body.args, adapter=body.adapter)
    if isinstance(result, dict) and result.get("status") == "refused":
        raise HTTPException(status_code=503, detail=result)
    return {"success": getattr(result, "ok", False), "result": result.to_dict() if hasattr(result, "to_dict") else result}


@router.post("/runtime/terraform/{operation}")
def run_terraform(operation: str, body: InfrastructureRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = _runtime()
    if operation in ("apply", "destroy") and not body.authorized:
        raise HTTPException(status_code=403, detail="this operation requires the operator's authorization")
    result = manager.run_infrastructure(operation, body.args, adapter=body.adapter)
    if isinstance(result, dict) and result.get("status") == "refused":
        raise HTTPException(status_code=503, detail=result)
    return {"success": getattr(result, "ok", False), "result": result.to_dict() if hasattr(result, "to_dict") else result}


@router.post("/runtime/deploy")
def run_deploy(body: DeployRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = _runtime()
    root = _workspace_root()
    outcome = manager.deployment.deploy(
        root, provider=body.provider, environment=body.environment, service=body.service,
        install=body.install, build=body.build, test=body.test, authorize=body.authorized,
        extra_args=body.args,
    )
    return {"success": outcome.status != "failed", "deployment": outcome.to_dict()}


__all__ = ["router"]
