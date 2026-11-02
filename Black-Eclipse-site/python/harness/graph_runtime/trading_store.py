"""The durable state shared by the trading graph nodes.

Two things live here instead of in `trading_nodes.py`, so the paper and broker
node modules can share them without importing each other:

- the PAPER account store (wired once at boot), and
- the idempotency guard (`trading.broker_order` / `trading.paper_order`
  `dedupe: key | day`), which claims a row on `agent-memory.db` BEFORE the send.

`set_paper_store` stays re-exported from `trading_nodes` for existing importers.
"""

from __future__ import annotations

from typing import Any

from ..persistence import now_iso
from .registry import NodeExecContext

_store: Any = None


def set_paper_store(store: Any) -> None:
    global _store
    _store = store


def require_paper_store() -> Any:
    if _store is None:
        raise ValueError("the paper account store is not configured in this runtime")
    return _store


def claim_guard(context: NodeExecContext, scope: str) -> bool:
    """Claim this node's idempotency slot, or False when it was already used.

    `dedupe: none` (the default) sends every run. `key` uses the node's
    `idempotencyKey`; `day` uses the node id plus the UTC date. The claim happens
    BEFORE the send, so an ambiguous failure is never automatically repeated.
    """
    mode = str(context.config.get("dedupe") or "none").strip().lower()
    if mode == "none":
        return True
    if mode == "key":
        key = str(context.config.get("idempotencyKey") or "").strip()
        if not key:
            raise ValueError("dedupe 'key' needs a non-empty idempotencyKey")
        suffix = f"key:{key}"
    elif mode == "day":
        suffix = f"day:{now_iso()[:10]}:{context.node_id}"
    else:
        raise ValueError("dedupe must be none, key or day")
    return require_paper_store().claim_guard(scope, suffix)


__all__ = ["set_paper_store", "require_paper_store", "claim_guard"]
