"""The durable state shared by the trading graph nodes.

Two things live here instead of in `trading_nodes.py`, so the paper and broker
node modules can share them without importing each other:

- the PAPER account store (wired once at boot), and
- the idempotency guard (`trading.broker_order` / `trading.paper_order`
  `dedupe: key | day`), which claims a row on `agent-memory.db` BEFORE the send
  and gives it back when the order definitely never reached the broker.

`set_paper_store` stays re-exported from `trading_nodes` for existing importers.
"""

from __future__ import annotations

from typing import Any

from ..persistence import now_iso
from .registry import NodeExecContext

_store: Any = None
#: Guards older than this are pruned at boot. One row per key/day per node, so
#: without a prune the table would grow forever.
GUARD_RETENTION_DAYS = 90


def set_paper_store(store: Any) -> None:
    global _store
    _store = store
    try:
        store.prune_guards(GUARD_RETENTION_DAYS)
    except Exception:  # noqa: BLE001 - housekeeping must never block boot
        pass


def require_paper_store() -> Any:
    if _store is None:
        raise ValueError("the paper account store is not configured in this runtime")
    return _store


def _guard_suffix(context: NodeExecContext) -> str | None:
    """The key this run would claim, or None when dedupe is off."""
    mode = str(context.config.get("dedupe") or "none").strip().lower()
    if mode == "none":
        return None
    if mode == "key":
        key = str(context.config.get("idempotencyKey") or "").strip()
        if not key:
            raise ValueError("dedupe 'key' needs a non-empty idempotencyKey")
        return f"key:{key}"
    if mode == "day":
        return f"day:{now_iso()[:10]}:{context.node_id}"
    raise ValueError("dedupe must be none, key or day")


def claim_guard(context: NodeExecContext, scope: str) -> tuple[bool, str | None]:
    """Claim this node's idempotency slot.

    Returns `(claimed, key)`. `key` is None when dedupe is off. The claim happens
    BEFORE the send, so an ambiguous failure is never automatically repeated; a
    caller that learns the order never reached the broker calls `release_guard`
    so a refusal does not burn the slot.
    """
    key = _guard_suffix(context)
    if key is None:
        return True, None
    return require_paper_store().claim_guard(scope, key), key


def release_guard(scope: str, key: str | None) -> None:
    if key is None:
        return
    try:
        require_paper_store().release_guard(scope, key)
    except Exception:  # noqa: BLE001 - a failed release must not fail the order
        pass


__all__ = [
    "GUARD_RETENTION_DAYS",
    "claim_guard",
    "release_guard",
    "require_paper_store",
    "set_paper_store",
]
