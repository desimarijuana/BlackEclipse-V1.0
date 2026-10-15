"""Agent tools for the trading Journal — the SAME store the Journal screen reads.

The Journal is front-door-owned (Prisma ``Trade``/``JournalProfile``, served at
``/api/journal/*``). The runtime reaches it over the loopback callback
(``HARNESS_CALLBACK_URL`` + the operator token) — the same transport the
read-only data bridge uses, except a journal ADD is a MUTATION, which the
read-only bridge deliberately cannot carry, so this module makes the one
authenticated POST. It targets the screen's own route, never a second book, and
RE-READS the store to verify a write before reporting it (the standing rule).

The write is admitted at the effect seam only after a single-use, digest-bound
operator approval (``make_journal_authorizer``).
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .tools import ToolContext, ToolDefinition, ToolRegistry

APPROVAL_KIND = "journal_write"

# The fields the Journal's create route accepts (camelCase, matching
# `CreateTradeInput`); anything absent is simply not sent.
_WRITE_FIELDS = (
    "symbol", "direction", "entry", "exit", "stopLoss", "takeProfit", "quantity",
    "entryTime", "exitTime", "timeframe", "session", "marketRegime", "trend",
    "confluences", "emotion", "confidence", "notes", "grade", "strategyId",
    "setupId", "accountId", "commission", "fee", "status",
)


def _callback_base() -> str:
    return (os.environ.get("HARNESS_CALLBACK_URL") or "http://127.0.0.1:3000").rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("CRON_SECRET")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _journal_request(
    method: str, path: str, *, body: Optional[dict[str, Any]] = None,
) -> tuple[int, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(method, f"{_callback_base()}{path}", headers=_headers(), json=body)
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001 - a non-JSON error body is reported as empty
        payload = {}
    return response.status_code, payload


async def journal_trades_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    status, payload = await _journal_request("GET", "/api/journal/trades")
    if status >= 400:
        return (f"The Journal is unavailable (HTTP {status}).", {"status": "unavailable"})
    trades = payload.get("trades") or []
    return (f"{len(trades)} journal trade(s).", {"status": "ok", "count": len(trades), "trades": trades})


async def journal_add_trade_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    body = {k: args.get(k) for k in _WRITE_FIELDS if args.get(k) is not None}
    if not body.get("symbol") or body.get("entry") is None or body.get("quantity") is None:
        return (
            "A journal trade needs at least symbol, entry and quantity.",
            {"status": "error", "reason": "missing required fields"},
        )
    status, payload = await _journal_request("POST", "/api/journal/trades", body=body)
    if status >= 400 or not payload.get("success"):
        return (
            f"Could not add the trade: {payload.get('error') or f'HTTP {status}'}.",
            {"status": "error"},
        )
    trade = payload.get("trade") or {}
    trade_id = str(trade.get("id") or "")
    # Standing rule: read it back from the store the screen reads before reporting done.
    verified = False
    if trade_id:
        vstatus, vpayload = await _journal_request("GET", "/api/journal/trades")
        if vstatus < 400:
            verified = any(str(t.get("id")) == trade_id for t in (vpayload.get("trades") or []))
    if not verified:
        return (
            "The trade was submitted but could not be read back from the Journal store; treat as NOT confirmed.",
            {"status": "unverified", "trade": trade},
        )
    return (
        f"Added the trade to the Journal (id {trade_id}); verified in the Journal store.",
        {"status": "ok", "trade": trade, "verified": True},
    )


def register_journal_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="journal_trades",
            description=(
                "List the trades in the user's trading Journal (the SAME store the Journal screen "
                "shows). Read-only."
            ),
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=journal_trades_handler,
            permission="read",
            risk="low",
            timeout_ms=20_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="journal_add_trade",
            description=(
                "Add ONE trade to the user's trading Journal (the SAME Prisma store the Journal "
                "screen reads). Computes the derived metrics the screen shows. Requires an operator "
                "approval bound to the trade; the result is re-read from the store before it is "
                "reported as done."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Instrument symbol, e.g. 'AAPL'."},
                    "direction": {"type": "string", "enum": ["LONG", "SHORT"]},
                    "entry": {"type": "number", "description": "Entry price."},
                    "quantity": {"type": "number"},
                    "entryTime": {"type": "string", "description": "ISO timestamp of entry."},
                    "exit": {"type": "number", "description": "Exit price (omit for an open position)."},
                    "exitTime": {"type": "string"},
                    "stopLoss": {"type": "number"},
                    "takeProfit": {"type": "number"},
                    "notes": {"type": "string"},
                },
                "required": ["symbol", "entry", "quantity"],
                "additionalProperties": False,
            },
            handler=journal_add_trade_handler,
            permission="write",
            risk="medium",
            effect="external_action",
            timeout_ms=30_000,
        )
    )


def make_journal_authorizer(inner: Any = None):
    """Gate `journal_add_trade` on a single-use, digest-bound operator approval.

    Same semantics as every other approval card: single-use, digest-bound,
    pause-in-card-mode, deny/timeout never authorizes. Reads and every other tool
    fall through to `inner`.
    """

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name != "journal_add_trade":
            return bool(await inner(tool, args, ctx)) if inner is not None else False
        run_args = args or {}
        symbol = str(run_args.get("symbol") or "").strip().upper()
        if not symbol:
            return False
        import hashlib

        digest = hashlib.sha256(
            f"journal_add_trade\x00{symbol}\x00{run_args.get('entry')}\x00{run_args.get('quantity')}".encode("utf-8")
        ).hexdigest()
        approvals = getattr(ctx, "approvals", None) if ctx is not None else None
        if approvals is None:
            return False
        claimed = approvals.consume_kind(kind=APPROVAL_KIND, request_key="journal", digest=digest)
        if claimed is not None:
            return True
        pending = None
        try:
            pending = approvals.request_kind(
                kind=APPROVAL_KIND, request_key="journal", digest=digest,
                effect="external_action",
                run_id=str(getattr(ctx, "run_id", "")),
                action_summary=f"Add a trade to the Journal: {symbol}",
                affected_data={"symbol": symbol},
                risk="medium",
            )
        except Exception:  # noqa: BLE001 - a store failure must never authorize
            return False
        emitter = getattr(ctx, "emitter", None)
        if emitter is not None:
            try:
                await emitter.emit("approval.requested", {
                    "approvalId": (pending or {}).get("id"),
                    "kind": APPROVAL_KIND,
                    "title": "Approve adding a Journal trade",
                    "summary": f"Add {symbol} to the Journal",
                    "effect": "external_action",
                    "risk": "medium",
                    "symbol": symbol,
                })
            except Exception:  # noqa: BLE001 - the card is best-effort
                pass
        if pending is not None:
            from .mcp.approvals import pause_for_decision  # noqa: PLC0415

            if await pause_for_decision(
                approvals, ctx, pending.get("id"),
                lambda: approvals.consume_kind(kind=APPROVAL_KIND, request_key="journal", digest=digest),
                emitter=emitter, digest=digest,
                event_type="approval.approved",
                approved_payload={"kind": APPROVAL_KIND, "symbol": symbol},
            ):
                return True
        return False

    return authorize


__all__ = [
    "APPROVAL_KIND",
    "journal_add_trade_handler",
    "journal_trades_handler",
    "make_journal_authorizer",
    "register_journal_tools",
]
