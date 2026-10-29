"""Demo position lifecycle: close (full or partial) and modify brackets.

These are the risk-reducing verbs. They live in their own module because the
broker service is near its size ceiling and because the rule is simple enough to
state in one place:

  * demo connection AND a demo account behind it, or the call is refused;
  * no mandate and no approval — an exit must always be possible;
  * the broker's own position is read before and after the send, so the returned
    `verified` flag is evidence, not optimism.

`close_positions` is the "step out" path and reports a per-ticket result instead
of pretending a partial failure succeeded.
"""

from __future__ import annotations

from typing import Any, Optional

from .adapter import AdapterUnavailable
from .model import TradeRefused


def _demo_adapter(service: Any, connection_id: str, action: str) -> tuple[Any, Any]:
    """The connection and an OPEN adapter, both proven demo, or a refusal."""
    connection = service._connection(connection_id)
    if connection.mode.value != "demo":
        raise TradeRefused(
            "LIVE_NOT_ENABLED",
            f"{action} live positions is not enabled; do it in the terminal",
            status_code=403,
        )
    adapter = service._trading_adapter(connection)
    try:
        account_mode = str(adapter.account().get("mode") or "unknown")
    except AdapterUnavailable as exc:
        _close(adapter)
        raise TradeRefused(exc.code, exc.reason, status_code=503) from exc
    except Exception as exc:  # noqa: BLE001
        _close(adapter)
        raise TradeRefused(
            "ADAPTER_ERROR", f"the broker could not be read: {exc}", status_code=503
        ) from exc
    if account_mode != "demo":
        _close(adapter)
        raise TradeRefused(
            "DEMO_ACCOUNT_REQUIRED",
            f"the connected account is {account_mode}; only a demo position can be "
            f"{action} from Eclipse",
            status_code=403,
        )
    return connection, adapter


def _close(adapter: Any) -> None:
    try:
        adapter.close()
    except Exception:  # noqa: BLE001
        pass


def close_position(
    service: Any, connection_id: str, ticket: int, *,
    deviation: int = 20, volume: Optional[float] = None,
) -> dict[str, Any]:
    """Close all or part of ONE demo position. No approval, no mandate."""
    connection, adapter = _demo_adapter(service, connection_id, "closing")
    try:
        try:
            result = adapter.close_position(
                int(ticket), deviation=int(deviation or 0), volume=volume,
            )
        except AdapterUnavailable as exc:
            raise TradeRefused(exc.code, exc.reason, status_code=503) from exc
    finally:
        _close(adapter)
    service.connections.record_event(
        connection.id,
        "close",
        "ok" if result.get("ok") else "rejected",
        {"ticket": int(ticket), "retcode": result.get("retcode"),
         "deal": result.get("deal"), "partial": result.get("partial"),
         "verified": result.get("verified")},
    )
    return {
        "available": True,
        "closed": bool(result.get("ok")),
        "connectionId": connection.id,
        "result": result,
    }


def close_positions(
    service: Any, connection_id: str, *, tickets: Optional[list[int]] = None,
    deviation: int = 20,
) -> dict[str, Any]:
    """Close every open demo position, or only the named tickets."""
    connection, adapter = _demo_adapter(service, connection_id, "closing")
    try:
        try:
            rows = adapter.positions()
        except AdapterUnavailable as exc:
            raise TradeRefused(exc.code, exc.reason, status_code=503) from exc
    finally:
        _close(adapter)
    wanted = {int(ticket) for ticket in (tickets or [])}
    targets = [
        int(row.get("ticket") or 0)
        for row in rows
        if not wanted or int(row.get("ticket") or 0) in wanted
    ]
    results: list[dict[str, Any]] = []
    for ticket in targets:
        try:
            outcome = close_position(service, connection_id, ticket, deviation=deviation)
            results.append(outcome.get("result") or {})
        except TradeRefused as exc:
            results.append({
                "ok": False, "ticket": ticket,
                "retcodeName": exc.code, "reasons": [exc.message],
            })
    if wanted:
        found = set(targets)
        for ticket in sorted(wanted - found):
            results.append({
                "ok": False, "ticket": ticket,
                "retcodeName": "POSITION_NOT_FOUND",
                "reasons": [f"no open position with ticket {ticket}"],
            })
    closed = sum(1 for result in results if result.get("ok"))
    return {
        "available": True,
        "connectionId": connection.id,
        "closed": closed,
        "failed": len(results) - closed,
        "requested": len(wanted) if wanted else len(rows),
        "results": results,
    }


def modify_position(
    service: Any, connection_id: str, ticket: int, *,
    stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
) -> dict[str, Any]:
    """Move a demo position's stop and/or target. No approval, no mandate.

    A wider stop can increase risk, so the tool text warns; the broker still enforces
    its own stops distance and the result is verified against the stored bracket.
    """
    if stop_loss is None and take_profit is None:
        raise TradeRefused(
            "INVALID_STOPS", "pass stopLoss and/or takeProfit", status_code=400
        )
    connection, adapter = _demo_adapter(service, connection_id, "modifying")
    try:
        try:
            result = adapter.modify_position(
                int(ticket), stop_loss=stop_loss, take_profit=take_profit,
            )
        except AdapterUnavailable as exc:
            raise TradeRefused(exc.code, exc.reason, status_code=503) from exc
    finally:
        _close(adapter)
    service.connections.record_event(
        connection.id,
        "modify",
        "ok" if result.get("ok") else "rejected",
        {"ticket": int(ticket), "retcode": result.get("retcode"),
         "stopLoss": result.get("stopLoss"),
         "takeProfit": result.get("takeProfit"),
         "verified": result.get("verified")},
    )
    return {
        "available": True,
        "modified": bool(result.get("ok")),
        "connectionId": connection.id,
        "result": result,
    }


__all__ = ["close_position", "close_positions", "modify_position"]
