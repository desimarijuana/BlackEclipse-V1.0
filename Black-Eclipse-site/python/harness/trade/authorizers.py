"""Effect authorizer for the ONE agent trade-submission tool.

The generic effect gate requires an approval for every non-read tool. An
unattended mandate is a different, stronger authorization: an operator created it
with symbols, a margin cap, an order count and an expiry. This wrapper admits
`order_submit` only when an active mandate covers the connection and symbol; the
handler/service still enforces the margin cap, policy, money guardrails, demo
account mode and single-use order count.

No mandate, no submission. There is no agent path for live orders.
"""

from __future__ import annotations

from typing import Any


def wrap_trade_authorizer(inner: Any) -> Any:
    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name != "order_submit":
            return bool(await inner(tool, args, ctx))
        from .bootstrap import get_service  # noqa: PLC0415

        service = get_service()
        if service is None:
            return False
        connection_id = str(args.get("connectionId") or "").strip()
        mandate_id = str(args.get("mandateId") or "").strip()
        intent = args.get("intent") or {}
        symbol = str((intent or {}).get("symbol") or "").strip()
        if not connection_id or not symbol:
            return False
        if not mandate_id:
            try:
                active = service.list_mandates(connection_id, active_only=True)
            except Exception:  # noqa: BLE001 - fail closed
                return False
            if len(active) != 1:
                return False
            mandate_id = str(active[0].get("id") or "").strip()
            if not mandate_id:
                return False
        try:
            return service.mandates.covers(
                mandate_id, connection_id=connection_id, symbol=symbol
            )
        except Exception:  # noqa: BLE001 - fail closed
            return False

    return authorize


__all__ = ["wrap_trade_authorizer"]
