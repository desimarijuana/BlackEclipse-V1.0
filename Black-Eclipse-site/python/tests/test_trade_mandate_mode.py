"""A mandate authorizes one EXECUTION MODE, never both.

Regression: `TradingMandateStore.covers` used to ignore `mode`, so a demo mandate
could be read as covering a live connection (and vice versa) whenever the caller
forgot to check. The mode is now part of the coverage decision.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from harness.trade.mandates import TradingMandateStore


class _Store:
    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db


def _store() -> TradingMandateStore:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    return TradingMandateStore(_Store(db))


def _insert(mandate: TradingMandateStore, *, mode: str, symbols: str = '["EURUSD"]') -> str:
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    mandate._db.execute(
        "INSERT INTO TradingMandate "
        "(id, connectionId, mode, symbols, maxOrders, maxMargin, ordersUsed, "
        "expiresAt, createdAt) VALUES (?,?,?,?,?,?,?,?,?)",
        ("mnd_1", "brk_1", mode, symbols, 5, 100.0, 0, expires, expires),
    )
    mandate._db.commit()
    return "mnd_1"


def test_a_demo_mandate_covers_only_demo():
    store = _store()
    mandate_id = _insert(store, mode="demo")
    assert store.covers(
        mandate_id, connection_id="brk_1", symbol="EURUSD", mode="demo"
    ) is True
    assert store.covers(
        mandate_id, connection_id="brk_1", symbol="EURUSD", mode="live"
    ) is False


def test_a_live_mandate_covers_only_live():
    store = _store()
    mandate_id = _insert(store, mode="live")
    assert store.covers(
        mandate_id, connection_id="brk_1", symbol="EURUSD", mode="live"
    ) is True
    assert store.covers(
        mandate_id, connection_id="brk_1", symbol="EURUSD", mode="demo"
    ) is False


def test_an_omitted_mode_keeps_the_legacy_behaviour():
    # Only callers that cannot know the mode omit it; the authorizer always
    # passes it, so omission is not a bypass on the trade path.
    store = _store()
    mandate_id = _insert(store, mode="demo")
    assert store.covers(mandate_id, connection_id="brk_1", symbol="EURUSD") is True


def test_connection_symbol_and_expiry_still_apply():
    store = _store()
    mandate_id = _insert(store, mode="demo")
    assert store.covers(
        mandate_id, connection_id="brk_2", symbol="EURUSD", mode="demo"
    ) is False
    assert store.covers(
        mandate_id, connection_id="brk_1", symbol="GBPUSD", mode="demo"
    ) is False
