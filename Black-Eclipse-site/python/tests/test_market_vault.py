"""JDdS inventory + cross-store resolution: labelled, never merged."""

from __future__ import annotations

import sqlite3

import pytest

from harness.market.vault import jdds_inventory, resolve_series


@pytest.fixture()
def jdds(tmp_path, monkeypatch):
    path = tmp_path / "jdds.db"
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE Candles (symbol TEXT, timeframe TEXT, ts TEXT, o REAL, h REAL, l REAL, c REAL, v REAL);
        CREATE TABLE Price (assetId TEXT, price REAL, updatedAt TEXT);
        CREATE TABLE Asset (id TEXT, symbol TEXT, name TEXT);
        """
    )
    for symbol in ("AAPL", "MSFT"):
        for day in ("2026-01-02", "2026-01-03"):
            db.execute(
                "INSERT INTO Candles VALUES (?, '1d', ?, 1, 1, 1, 1, 1)",
                (symbol, day),
            )
    db.execute("INSERT INTO Price VALUES ('a1', 100.0, '2026-01-03')")
    db.execute("INSERT INTO Asset VALUES ('a1', 'AAPL', 'Apple')")
    db.commit()
    db.close()
    monkeypatch.setenv("BE_JDDS_PATH", str(path))
    return path


class _Cache:
    def coverage(self, symbol, interval="1d", *, adjusted=True):
        return {
            "symbol": symbol, "interval": interval, "store": "history_cache",
            "barCount": 5, "start": "2026-01-01", "end": "2026-01-10",
            "providers": ["yahoo"],
        }


def test_jdds_inventory_is_store_exact(jdds):
    result = jdds_inventory()
    assert result["status"] == "ok"
    assert result["store"] == "jdds"
    assert result["symbols"] == 2
    assert result["counts"] == {"candles": 4, "prices": 1, "assets": 1}
    assert all(row["store"] == "jdds" for row in result["series"])


def test_missing_vault_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("BE_JDDS_PATH", str(tmp_path / "nope.db"))
    result = jdds_inventory()
    assert result["status"] == "UNAVAILABLE"
    assert result["store"] == "jdds"


def test_resolver_labels_both_stores_and_flags_a_count_conflict(jdds):
    result = resolve_series("AAPL", "1d", series_store=_Cache())
    assert result["status"] == "ok"
    stores = {record["store"] for record in result["records"]}
    assert stores == {"jdds", "history_cache"}
    assert all(record["quality"]["status"] == "conflict" for record in result["records"])


def test_resolver_does_not_invent_a_missing_series(jdds):
    assert resolve_series("ZZQX", "1d")["status"] == "UNAVAILABLE"
