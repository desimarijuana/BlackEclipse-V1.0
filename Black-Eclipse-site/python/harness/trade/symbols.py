"""Symbol facts: the static half of a symbol the quote cannot give when closed.

`BrokerService.symbol_info` delegates here so the service stays inside its size
budget. The read is honest in the same way as the other reads: a broker that
cannot answer is a named `UNAVAILABLE`, never a guessed contract size.
"""

from __future__ import annotations

from typing import Any

from .adapter import AdapterUnavailable
from .registry import make_adapter


def symbol_info(service: Any, connection_id: str, symbol: str) -> dict[str, Any]:
    connection = service._connection(connection_id)
    adapter: Any = None
    try:
        adapter = make_adapter(connection.kind, connection.config)
    except KeyError as exc:
        raise AdapterUnavailable("BROKER_KIND_UNKNOWN", str(exc)) from exc
    try:
        payload = adapter.symbol_info(symbol)
    except AdapterUnavailable as exc:
        return service._unavailable(connection, exc)
    except Exception as exc:  # noqa: BLE001 - an adapter bug is not a broker fact
        failure = AdapterUnavailable(
            "ADAPTER_ERROR", f"{connection.kind} adapter failed: {exc}"
        )
        return service._unavailable(connection, failure)
    finally:
        try:
            if adapter is not None:
                adapter.close()
        except Exception:  # noqa: BLE001
            pass
    service.connections.set_status(
        connection.id, status="connected", reason=None, mark_seen=True
    )
    service.connections.record_event(
        connection.id, "symbol_info", "ok", {"symbol": payload.get("symbol")}
    )
    return {
        "available": True,
        "status": "connected",
        "connectionId": connection.id,
        "kind": connection.kind,
        "mode": connection.mode.value,
        "data": payload,
    }


__all__ = ["symbol_info"]
