"""MCP server catalog, approvals, presets and diagnostics routes (Phase 5).

Extracted verbatim from `main.py` so the front door stays navigable. Behavior,
authorization (`require_mcp_operator`, transport/token only) and response shapes
are unchanged; the shared runtime service comes from `harness.deps`.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..deps import require_mcp_operator, service
from ..mcp.config import (
    MCPServerConfig,
    remove_mcp_config,
    upsert_mcp_config,
)

router = APIRouter()


@router.get("/mcp/servers")
def list_mcp_servers() -> dict[str, Any]:
    """Configured servers + live status + discovered tools (secret-free)."""
    return {"success": True, "servers": service.mcp.public_configs(), **service.mcp.summary()}


class MCPServerUpsertRequest(BaseModel):
    """Create/replace one server. The full config is validated by pydantic."""

    server: MCPServerConfig
    reload: bool = True
    # The authoritative env key set (values are write-only and never echoed to
    # the UI, so the client sends key names to add/remove while values persist).
    envKeys: Optional[list[str]] = None  # noqa: N815


@router.post("/mcp/servers")
async def upsert_mcp_server(request: MCPServerUpsertRequest, _: None = Depends(require_mcp_operator)) -> JSONResponse:
    upsert_mcp_config(request.server, env_keys=request.envKeys)
    summary = await service.reload_mcp() if request.reload else service.mcp.summary()
    return JSONResponse({"success": True, **summary})


@router.delete("/mcp/servers/{server_id}")
async def delete_mcp_server(server_id: str, _: None = Depends(require_mcp_operator)) -> JSONResponse:
    removed = remove_mcp_config(server_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Server not found")
    summary = await service.reload_mcp()
    return JSONResponse({"success": True, "removed": server_id, **summary})


@router.post("/mcp/servers/test")
async def test_mcp_server(payload: dict[str, Any], _: None = Depends(require_mcp_operator)) -> JSONResponse:
    """Connect + discover a candidate config WITHOUT persisting or activating."""
    raw = payload.get("server")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="server config is required")
    try:
        config = MCPServerConfig(**raw)
    except Exception as exc:  # noqa: BLE001 - a bad config is a 400, not a crash
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = await service.mcp.test_server(config)
    return JSONResponse({"success": result.get("state") == "connected", **result})


@router.post("/mcp/reload")
async def reload_mcp(_: None = Depends(require_mcp_operator)) -> JSONResponse:
    summary = await service.reload_mcp()
    return JSONResponse({"success": True, **summary})


@router.post("/mcp/servers/{server_id}/confirm")
async def confirm_mcp_catalog(server_id: str, _: None = Depends(require_mcp_operator)) -> JSONResponse:
    """Record the operator's review of a server's current catalog digest.

    The explicit act that lets an annotation-sourced read-only tool activate.
    """
    result = await service.confirm_mcp_catalog(server_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=str(result.get("reason") or "confirm failed"))
    return JSONResponse(result)


@router.get("/mcp/approvals")
def list_mcp_approvals(status: Optional[str] = None) -> dict[str, Any]:
    return {"success": True, "approvals": service.approvals.list(status)}


@router.post("/mcp/approvals/{approval_id}/decide")
async def decide_mcp_approval(
    approval_id: str, payload: dict[str, Any], _: None = Depends(require_mcp_operator)
) -> JSONResponse:
    approve = bool(payload.get("approve"))
    result = service.approvals.decide(
        approval_id, approve=approve,
        decided_by=str(payload.get("decidedBy") or "operator"),
        reason=str(payload.get("reason") or ""),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return JSONResponse({"success": True, "approval": result})


@router.get("/mcp/integrations")
def list_mcp_integrations() -> dict[str, Any]:
    from ..mcp.presets import list_integrations

    return {"success": True, "integrations": list_integrations()}


@router.get("/mcp/workflows")
def list_mcp_workflows() -> dict[str, Any]:
    from ..mcp.presets import list_workflows

    return {"success": True, "workflows": list_workflows()}


@router.post("/mcp/diagnostics")
def mcp_diagnostics(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Setup diagnostics for every configured server + the environment.

    `knownSecrets` (secret NAMES only) lets the runtime report missing vault
    references without ever seeing a value.
    """
    known = set()
    if isinstance(payload, dict):
        for name in payload.get("knownSecrets") or []:
            if isinstance(name, str):
                known.add(name)
    resolved: dict[str, dict[str, bool]] = {}
    for cfg in service.mcp._runtimes.values():  # noqa: SLF001 - read-only inspection
        resolved[cfg.config.id] = {name: (name in known) for name in cfg.config.secret_ref_names()}
    return {"success": True, **service.mcp.diagnostics(resolved)}
