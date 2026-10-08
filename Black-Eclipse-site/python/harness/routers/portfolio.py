"""Portfolio Accounting Engine HTTP routes.

Thin adapters over the SAME portfolio service the agent tools use (reached
through `harness.deps.service`), so the UI and the agent can never disagree and
a second engine is never built. Reads AND mutations are operator-gated
(loopback or runtime token) — matching every other runtime surface.

Tenant scope: an optional actor identity is taken from the `X-Harness-User`
header (or `actorId` in a body / query). When present and it does not match a
portfolio's owner, the request is refused (403). Absent, the app is in its
documented single-user local mode.

Prices for a read may be supplied by the front door as a `marks` mapping (the
Next.js side already fetches live quotes); without them the read reports an
honest data-quality status rather than inventing prices.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from ..deps import require_operator, service

router = APIRouter(tags=["portfolio"])


def _engine() -> Any:
    engine = getattr(service, "portfolio", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="the portfolio engine is unavailable")
    return engine


def _actor(request: Request, body: Optional[dict[str, Any]] = None,
           query_actor: Optional[str] = None) -> Optional[str]:
    return (
        request.headers.get("x-harness-user")
        or (body or {}).get("actorId")
        or query_actor
    )


@router.get("/portfolio/list")
async def portfolio_list(request: Request, owner_id: Optional[str] = None,
                         _: bool = Depends(require_operator)) -> dict[str, Any]:
    owner = owner_id or _actor(request)
    return {"available": True, "portfolios": _engine().list_portfolios(owner)}


@router.post("/portfolio/create")
async def portfolio_create(request: Request, body: dict[str, Any] = Body(...),
                           _: bool = Depends(require_operator)) -> dict[str, Any]:
    name = body.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="`name` is required")
    actor = _actor(request, body)
    fields = {k: v for k, v in body.items() if k not in ("name", "actorId")}
    if actor:
        fields["owner_id"] = actor
    return _engine().create_portfolio(name, **fields)


@router.post("/portfolio/aggregate")
async def portfolio_aggregate(request: Request, body: dict[str, Any] = Body(default={}),
                              _: bool = Depends(require_operator)) -> dict[str, Any]:
    engine = _engine()
    return await engine.aggregate({**body, "owner_id": body.get("owner_id") or _actor(request, body)},
                                  actor_id=_actor(request, body))


@router.delete("/portfolio/{portfolio_id}")
async def portfolio_delete(portfolio_id: str, request: Request,
                           _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"deleted": _engine().delete_portfolio(portfolio_id, actor_id=_actor(request))}


@router.post("/portfolio/{portfolio_id}/query")
async def portfolio_query(portfolio_id: str, request: Request,
                          body: dict[str, Any] = Body(default={}),
                          _: bool = Depends(require_operator)) -> dict[str, Any]:
    engine = _engine()
    try:
        return await engine.read(
            portfolio_id,
            include=body.get("include"),
            marks=body.get("marks"),
            histories=body.get("histories"),
            benchmark_closes=body.get("benchmarkCloses"),
            confidence=float(body.get("confidence") or 0.95),
            actor_id=_actor(request, body),
        )
    except Exception as exc:  # noqa: BLE001 - a missing portfolio is a 404, not a 500
        raise _http_error(exc) from exc


@router.get("/portfolio/{portfolio_id}")
async def portfolio_get(portfolio_id: str, request: Request,
                        _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return await _engine().read(portfolio_id, actor_id=_actor(request))
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.post("/portfolio/{portfolio_id}/transaction")
async def portfolio_transaction(portfolio_id: str, request: Request,
                                body: dict[str, Any] = Body(...),
                                _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().add_transaction(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/position")
async def portfolio_add_position(portfolio_id: str, request: Request,
                                 body: dict[str, Any] = Body(...),
                                 _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().add_position(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/position/remove")
async def portfolio_remove_position(portfolio_id: str, request: Request,
                                    body: dict[str, Any] = Body(...),
                                    _: bool = Depends(require_operator)) -> dict[str, Any]:
    return await _engine().remove_position(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/position/update")
async def portfolio_update_position(portfolio_id: str, request: Request,
                                    body: dict[str, Any] = Body(...),
                                    _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().update_position(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/metadata")
async def portfolio_set_metadata(portfolio_id: str, request: Request,
                                 body: dict[str, Any] = Body(...),
                                 _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().set_position_metadata(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/corporate-action")
async def portfolio_corporate_action(portfolio_id: str, request: Request,
                                     body: dict[str, Any] = Body(...),
                                     _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().apply_corporate_action(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/swap")
async def portfolio_swap(portfolio_id: str, request: Request,
                         body: dict[str, Any] = Body(...),
                         _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().apply_swap(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/bridge")
async def portfolio_bridge(portfolio_id: str, request: Request,
                           body: dict[str, Any] = Body(...),
                           _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().apply_bridge(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/reward")
async def portfolio_reward(portfolio_id: str, request: Request,
                           body: dict[str, Any] = Body(...),
                           _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().record_reward(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/staking")
async def portfolio_staking(portfolio_id: str, request: Request,
                            body: dict[str, Any] = Body(...),
                            _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().apply_staking(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/rebuild")
async def portfolio_rebuild(portfolio_id: str, request: Request,
                            _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().rebuild_all(portfolio_id, actor_id=_actor(request))


@router.post("/portfolio/{portfolio_id}/slashing")
async def portfolio_slashing(portfolio_id: str, request: Request, body: dict[str, Any] = Body(...),
                             _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().apply_slashing(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/funding")
async def portfolio_funding(portfolio_id: str, request: Request, body: dict[str, Any] = Body(...),
                            _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().record_funding(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/reconcile")
async def portfolio_reconcile(portfolio_id: str, request: Request, body: dict[str, Any] = Body(...),
                              _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().reconcile(portfolio_id, body, actor_id=_actor(request, body))


@router.get("/portfolio/{portfolio_id}/reconciliations")
async def portfolio_reconciliations(portfolio_id: str, request: Request, limit: int = 50,
                                    _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"reconciliations": _engine().list_reconciliations(portfolio_id, limit, actor_id=_actor(request))}


@router.post("/portfolio/{portfolio_id}/optimize")
async def portfolio_optimize(portfolio_id: str, request: Request, body: dict[str, Any] = Body(default={}),
                             _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().optimize(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/attribution")
async def portfolio_attribution(portfolio_id: str, request: Request, body: dict[str, Any] = Body(default={}),
                                _: bool = Depends(require_operator)) -> dict[str, Any]:
    return await _engine().attribution(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/factor-exposure")
async def portfolio_factor_exposure(portfolio_id: str, request: Request,
                                    body: dict[str, Any] = Body(...),
                                    _: bool = Depends(require_operator)) -> dict[str, Any]:
    return await _engine().factor_exposure(portfolio_id, body, actor_id=_actor(request, body))


@router.post("/portfolio/{portfolio_id}/hedge")
async def portfolio_hedge(portfolio_id: str, request: Request, body: dict[str, Any] = Body(default={}),
                          _: bool = Depends(require_operator)) -> dict[str, Any]:
    return await _engine().hedge(portfolio_id, body, actor_id=_actor(request, body))


@router.get("/portfolio/{portfolio_id}/tax-lots")
async def portfolio_tax_lots(portfolio_id: str, request: Request, symbol: Optional[str] = None,
                             _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().calculate_tax_lots(portfolio_id, symbol=symbol, persist=True,
                                        actor_id=_actor(request))


@router.post("/portfolio/{portfolio_id}/rebalance")
async def portfolio_rebalance(portfolio_id: str, request: Request,
                              body: dict[str, Any] = Body(...),
                              _: bool = Depends(require_operator)) -> dict[str, Any]:
    return await _engine().rebalance(portfolio_id, body, actor_id=_actor(request, body))


@router.get("/portfolio/{portfolio_id}/rebalance/plans")
async def portfolio_rebalance_plans(portfolio_id: str, request: Request, limit: int = 50,
                                    _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"plans": _engine().list_rebalance_plans(portfolio_id, limit, actor_id=_actor(request))}


@router.post("/portfolio/{portfolio_id}/snapshot")
async def portfolio_snapshot(portfolio_id: str, request: Request,
                             body: dict[str, Any] = Body(default={}),
                             _: bool = Depends(require_operator)) -> dict[str, Any]:
    return await _engine().snapshot(portfolio_id, marks=body.get("marks"),
                                    created_by=body.get("createdBy"), actor_id=_actor(request, body))


@router.get("/portfolio/{portfolio_id}/snapshots")
async def portfolio_snapshots(portfolio_id: str, request: Request, limit: int = 365,
                              _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"snapshots": _engine().list_snapshots(portfolio_id, limit, actor_id=_actor(request))}


@router.get("/portfolio/{portfolio_id}/history")
async def portfolio_history(portfolio_id: str, request: Request, limit: int = 200,
                            _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _engine().history(portfolio_id, limit, actor_id=_actor(request))


def _http_error(exc: Exception) -> HTTPException:
    code = getattr(exc, "code", None)
    if code == "PORTFOLIO_NOT_FOUND":
        return HTTPException(status_code=404, detail=getattr(exc, "message", str(exc)))
    if code == "PORTFOLIO_FORBIDDEN":
        return HTTPException(status_code=403, detail=getattr(exc, "message", str(exc)))
    return HTTPException(status_code=400, detail=str(exc))


__all__ = ["router"]
