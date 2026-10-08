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
    screen_rejections,
    upsert_mcp_config,
)

router = APIRouter()


@router.get("/mcp/servers")
def list_mcp_servers(_: None = Depends(require_mcp_operator)) -> dict[str, Any]:
    """Configured servers + live status + discovered tools (secret-free).

    Operator-gated at the Python boundary (loopback or runtime secret), matching
    every other MCP route, so a directly reachable runtime does not expose the
    configured subprocess surface to an unauthenticated caller.
    """
    if service.mcp is None:
        return {"success": False, "unavailable": True, "servers": [],
                "configured": 0, "connected": 0, "registeredTools": 0, "loadDiagnostics": []}
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
    # Static screening runs at SAVE (refuse, not sanitize) so a shell/exec entry
    # is rejected here with a structured diagnostic, independent of load/spawn.
    entry = request.server.model_dump()
    rejections = screen_rejections(entry)
    if rejections:
        raise HTTPException(status_code=400, detail=rejections[0]["message"])
    upsert_mcp_config(request.server, env_keys=request.envKeys)
    summary = await service.reload_mcp() if request.reload else (
        service.mcp.summary() if service.mcp is not None else {"configured": 0, "connected": 0, "registeredTools": 0})
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
    if service.mcp is None:
        raise HTTPException(status_code=503, detail="MCP is unavailable (runtime missing the mcp SDK)")
    result = await service.mcp.test_server(config)
    return JSONResponse({"success": result.get("state") == "connected", **result})


@router.post("/mcp/servers/{server_id}/verify")
async def verify_mcp_server(
    server_id: str, payload: Optional[dict[str, Any]] = None, _: None = Depends(require_mcp_operator)
) -> JSONResponse:
    """Prove a server's credentials work: ONE operator-chosen read call.

    Distinct from Test (which only proves the process started and listed tools).
    Never automatic, never at boot, never a loop; the response body is never
    returned. `tool` is required and must be a read tool.
    """
    payload = payload or {}
    tool = str(payload.get("tool") or "").strip()
    if not tool:
        raise HTTPException(status_code=400, detail="a read tool name is required")
    arguments = payload.get("arguments")
    if arguments is not None and not isinstance(arguments, dict):
        raise HTTPException(status_code=400, detail="arguments must be an object")
    result = await service.verify_mcp_server(server_id, tool=tool, arguments=arguments)
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=str(result.get("reason") or "verify failed"))
    return JSONResponse(result)


@router.post("/mcp/servers/{server_id}/circuit/reset")
async def reset_mcp_circuit(server_id: str, _: None = Depends(require_mcp_operator)) -> JSONResponse:
    """Operator reset of a server's circuit breaker (back to CLOSED).

    A server that connects but fails every call trips the breaker into OPEN and
    is not re-probed until its cooldown. This is the explicit operator action that
    clears it immediately.
    """
    result = service.reset_mcp_circuit(server_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=str(result.get("reason") or "reset failed"))
    return JSONResponse(result)


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


@router.post("/mcp/servers/{server_id}/login")
async def mcp_oauth_login(
    server_id: str, payload: Optional[dict[str, Any]] = None, _: None = Depends(require_mcp_operator)
) -> JSONResponse:
    """Start an OAuth device-code login for a remote server (operator-gated)."""
    payload = payload or {}
    result = await service.oauth_login(
        server_id,
        client_id=payload.get("clientId"),
        scope=str(payload.get("scope") or ""),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=str(result.get("reason") or "login failed"))
    return JSONResponse(result)


@router.post("/mcp/servers/{server_id}/logout")
async def mcp_oauth_logout(server_id: str, _: None = Depends(require_mcp_operator)) -> JSONResponse:
    """Clear a server's stored credentials; it stays configured but disconnected."""
    result = await service.oauth_logout(server_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=str(result.get("reason") or "logout failed"))
    return JSONResponse(result)


@router.get("/mcp/approvals")
def list_mcp_approvals(status: Optional[str] = None, _: None = Depends(require_mcp_operator)) -> dict[str, Any]:
    return {"success": True, "approvals": service.approvals.list(status)}


@router.post("/mcp/approvals/{approval_id}/decide")
async def decide_mcp_approval(
    approval_id: str, payload: dict[str, Any], _: None = Depends(require_mcp_operator)
) -> JSONResponse:
    approve = bool(payload.get("approve"))
    remember = bool(payload.get("remember"))
    result = service.approvals.decide(
        approval_id, approve=approve,
        decided_by=str(payload.get("decidedBy") or "operator"),
        reason=str(payload.get("reason") or ""),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    # "Always allow": create the standing grant the row describes, AFTER the
    # single-use decision is committed. A grant is created only for a real
    # approval, and only when the row carries a grantable pattern.
    grant = None
    if approve and remember:
        grant = service.approvals.remember_grant(approval_id)
    return JSONResponse({"success": True, "approval": result, "grant": grant})


@router.get("/mcp/integrations")
def list_mcp_integrations(_: None = Depends(require_mcp_operator)) -> dict[str, Any]:
    from ..mcp.presets import list_integrations

    return {"success": True, "integrations": list_integrations()}


@router.get("/mcp/workflows")
def list_mcp_workflows(_: None = Depends(require_mcp_operator)) -> dict[str, Any]:
    from ..mcp.presets import list_workflows

    return {"success": True, "workflows": list_workflows()}


@router.post("/mcp/diagnostics")
def mcp_diagnostics(
    payload: Optional[dict[str, Any]] = None, _: None = Depends(require_mcp_operator)
) -> dict[str, Any]:
    """Setup diagnostics for every configured server + the environment.

    `knownSecrets` (secret NAMES only) and `tokenStatus` (OAuth state by server
    id, no values) let the runtime report missing references and auth state
    without ever seeing a value.
    """
    known = set()
    if isinstance(payload, dict):
        for name in payload.get("knownSecrets") or []:
            if isinstance(name, str):
                known.add(name)
    if service.mcp is None:
        return {"success": False, "unavailable": True,
                "environment": [], "servers": []}
    resolved: dict[str, dict[str, bool]] = {}
    for cfg in service.mcp._runtimes.values():  # noqa: SLF001 - read-only inspection
        resolved[cfg.config.id] = {name: (name in known) for name in cfg.config.secret_ref_names()}
    token_status: dict[str, dict[str, Any]] = {}
    if isinstance(payload, dict):
        for server_id, status in (payload.get("tokenStatus") or {}).items():
            if isinstance(server_id, str) and isinstance(status, dict):
                token_status[server_id] = status
    return {"success": True, **service.mcp.diagnostics(resolved, token_status)}


@router.post("/mcp/integrations/{integration_id}/install")
async def install_mcp_integration(
    integration_id: str, _: None = Depends(require_mcp_operator)
) -> JSONResponse:
    """Write a preset integration into the config (disabled, nothing selected).

    The user must not hand-edit JSON for a server Eclipse itself recommends. The
    entry ships disabled with an empty selection: install is not activation.
    """
    result = service.install_mcp_integration(integration_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=str(result.get("reason") or "install failed"))
    return JSONResponse(result)


@router.get("/mcp/supply-chain")
def mcp_supply_chain(_: None = Depends(require_mcp_operator)) -> dict[str, Any]:
    """A read-only supply-chain report over pinned packages/commands.

    The report never contacts the network. It includes the last LIVE OSV verdict
    the spawn path already recorded for a configured package (when one exists),
    via an in-memory lookup, and sets `upstreamChecked` from those observations.
    """
    from ..mcp.audit import supply_chain_report

    report = supply_chain_report(service.mcp)
    if service.mcp is None:
        report["unavailable"] = True
    return {"success": True, **report}
