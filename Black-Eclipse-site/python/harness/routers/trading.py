"""Broker connectivity routes (P0, read-only).

Thin adapters over `harness.trade.service.BrokerService`, reached through
`harness.deps.service`. Reads AND mutations are operator-gated (loopback or
runtime token) exactly like the other runtime surfaces: an agent can never add a
broker connection or edit its settings.

There is deliberately no order route. Live execution is a later, separately
authorized phase; `POST /trading/orders` returns an honest 501 so a client cannot
mistake a missing feature for a working one.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..deps import require_operator, service
from ..trade.model import BrokerConfigError, TradeRefused

router = APIRouter(tags=["trading"])


def _brokers() -> Any:
    brokers = getattr(service, "brokers", None)
    if brokers is None:
        raise HTTPException(status_code=503, detail="broker connectivity is unavailable")
    return brokers


def _not_found(connection_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"no broker connection {connection_id!r}")


def _refusal(exc: TradeRefused) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.to_dict())


@router.get("/trading/brokers")
async def trading_brokers(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"available": True, "brokers": _brokers().kinds()}


@router.get("/trading/connections")
async def trading_connections(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"available": True, "connections": _brokers().list_connections()}


@router.post("/trading/connections")
async def trading_connection_create(
    body: dict[str, Any] = Body(default={}),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        connection = _brokers().create_connection(
            kind=str(body.get("kind") or ""),
            label=str(body.get("label") or ""),
            mode=body.get("mode") or "demo",
            config=body.get("config") or {},
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BrokerConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"available": True, "connection": connection}


@router.get("/trading/connections/{connection_id}")
async def trading_connection_get(
    connection_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        connection = _brokers().get_connection(connection_id)
    except KeyError:
        raise _not_found(connection_id) from None
    return {"available": True, "connection": connection}


@router.patch("/trading/connections/{connection_id}")
async def trading_connection_update(
    connection_id: str,
    body: dict[str, Any] = Body(default={}),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        connection = _brokers().update_connection(connection_id, body or {})
    except KeyError:
        raise _not_found(connection_id) from None
    except BrokerConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"available": True, "connection": connection}


@router.delete("/trading/connections/{connection_id}")
async def trading_connection_delete(
    connection_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {"available": True, "deleted": _brokers().delete_connection(connection_id)}


@router.post("/trading/connections/{connection_id}/test")
async def trading_connection_test(
    connection_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return _brokers().test_connection(connection_id)
    except KeyError:
        raise _not_found(connection_id) from None


@router.post("/trading/connections/{connection_id}/arm")
async def trading_connection_arm(
    connection_id: str,
    body: dict[str, Any] = Body(default={}),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return _brokers().arm_connection(
            connection_id,
            confirmation=str(body.get("confirmation") or ""),
            ttl_seconds=int(body.get("ttlSeconds") or 1800),
        )
    except KeyError:
        raise _not_found(connection_id) from None
    except TradeRefused as exc:
        raise _refusal(exc) from None


@router.post("/trading/connections/{connection_id}/disarm")
async def trading_connection_disarm(
    connection_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return _brokers().disarm_connection(connection_id)
    except KeyError:
        raise _not_found(connection_id) from None


@router.post("/trading/connections/{connection_id}/kill")
async def trading_connection_kill(
    connection_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return _brokers().kill_switch(connection_id)
    except KeyError:
        raise _not_found(connection_id) from None
    except TradeRefused as exc:
        raise _refusal(exc) from None


@router.post("/trading/connections/{connection_id}/mandates")
async def trading_mandate_create(
    connection_id: str,
    body: dict[str, Any] = Body(default={}),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        mandate = _brokers().create_mandate(connection_id, body or {})
    except KeyError:
        raise _not_found(connection_id) from None
    except TradeRefused as exc:
        raise _refusal(exc) from None
    return {"available": True, "mandate": mandate}


@router.get("/trading/mandates")
async def trading_mandates(
    connectionId: str | None = None, limit: int = 50,  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {
        "available": True,
        "mandates": _brokers().list_mandates(connectionId, limit=limit),
    }


@router.post("/trading/mandates/{mandate_id}/revoke")
async def trading_mandate_revoke(
    mandate_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        mandate = _brokers().revoke_mandate(mandate_id)
    except TradeRefused as exc:
        raise _refusal(exc) from None
    return {"available": True, "mandate": mandate}


@router.get("/trading/connections/{connection_id}/account")
async def trading_account(
    connection_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return _brokers().account(connection_id)
    except KeyError:
        raise _not_found(connection_id) from None


@router.get("/trading/connections/{connection_id}/positions")
async def trading_positions(
    connection_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return _brokers().positions(connection_id)
    except KeyError:
        raise _not_found(connection_id) from None


@router.get("/trading/connections/{connection_id}/orders")
async def trading_orders(
    connection_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return _brokers().orders(connection_id)
    except KeyError:
        raise _not_found(connection_id) from None


@router.get("/trading/connections/{connection_id}/quote")
async def trading_quote(
    connection_id: str, symbol: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return _brokers().quote(connection_id, symbol)
    except KeyError:
        raise _not_found(connection_id) from None


@router.get("/trading/connections/{connection_id}/events")
async def trading_events(
    connection_id: str, limit: int = 20, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    brokers = _brokers()
    try:
        brokers.get_connection(connection_id)
    except KeyError:
        raise _not_found(connection_id) from None
    return {"available": True, "events": brokers.events(connection_id, limit=limit)}


@router.post("/trading/connections/{connection_id}/sync")
async def trading_connection_sync(
    connection_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return _brokers().sync_connection(connection_id)
    except KeyError:
        raise _not_found(connection_id) from None


@router.get("/trading/connections/{connection_id}/reconciliation")
async def trading_connection_reconciliation(
    connection_id: str, limit: int = 100, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return _brokers().reconciliation(connection_id, limit=limit)
    except KeyError:
        raise _not_found(connection_id) from None


@router.get("/trading/connections/{connection_id}/fills")
async def trading_connection_fills(
    connection_id: str, limit: int = 100, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return {
            "available": True,
            "fills": _brokers().list_fills(connection_id, limit=limit),
        }
    except KeyError:
        raise _not_found(connection_id) from None


# ── P1: demo order execution (preview → approval → submit) ───────────────────
@router.post("/trading/connections/{connection_id}/orders/preview")
async def trading_order_preview(
    connection_id: str,
    body: dict[str, Any] = Body(default={}),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return _brokers().preview_order(connection_id, body.get("intent") or body)
    except KeyError:
        raise _not_found(connection_id) from None
    except TradeRefused as exc:
        raise _refusal(exc) from None


@router.post("/trading/connections/{connection_id}/orders/submit")
async def trading_order_submit(
    connection_id: str,
    body: dict[str, Any] = Body(default={}),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return _brokers().submit_order(
            connection_id,
            body.get("intent") or {},
            str(body.get("approvalId") or ""),
            confirmation=str(body.get("confirmation") or ""),
            mandate_id=str(body.get("mandateId") or ""),
            run_id=str(body.get("runId") or ""),
        )
    except KeyError:
        raise _not_found(connection_id) from None
    except TradeRefused as exc:
        raise _refusal(exc) from None


@router.post("/trading/connections/{connection_id}/orders/{ticket}/cancel")
async def trading_order_cancel(
    connection_id: str, ticket: int, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return _brokers().cancel_order(connection_id, ticket)
    except KeyError:
        raise _not_found(connection_id) from None
    except TradeRefused as exc:
        raise _refusal(exc) from None


@router.get("/trading/connections/{connection_id}/orders/ledger")
async def trading_order_ledger(
    connection_id: str, limit: int = 50, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        _brokers().get_connection(connection_id)
    except KeyError:
        raise _not_found(connection_id) from None
    return {
        "available": True,
        "orders": _brokers().ledger_orders(connection_id, limit=limit),
    }


@router.get("/trading/orders/{order_id}")
async def trading_order_get(order_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        order = _brokers().get_ledger_order(order_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no broker order {order_id!r}") from None
    return {"available": True, "order": order}


@router.get("/trading/approvals")
async def trading_approvals(
    status: str | None = None, limit: int = 50, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {"available": True, "approvals": _brokers().list_approvals(status, limit=limit)}


@router.post("/trading/approvals/{approval_id}/decide")
async def trading_approval_decide(
    approval_id: str,
    body: dict[str, Any] = Body(default={}),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        approval = _brokers().decide_approval(
            approval_id,
            approve=bool(body.get("approve")),
            reason=str(body.get("reason") or ""),
        )
    except TradeRefused as exc:
        raise _refusal(exc) from None
    return {"available": True, "approval": approval}


@router.post("/trading/orders")
async def trading_orders_submit(_: bool = Depends(require_operator)) -> dict[str, Any]:
    raise HTTPException(
        status_code=501,
        detail=(
            "direct submission is not available; use "
            "`/trading/connections/{id}/orders/preview` then `/submit` with an "
            "approved approvalId"
        ),
    )
