"""Materialized positions: incremental cache, equality with the ledger, self-heal."""

from __future__ import annotations

from decimal import Decimal

from portfolio_helpers import buy, make_portfolio, make_service, sell


def test_materialized_row_matches_ledger_after_a_buy(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "10", "100")
    row = svc.store.get_materialized_position(pid, "AAPL")
    assert row is not None
    assert Decimal(row["quantity"]) == Decimal("10")
    assert Decimal(row["costBasis"]) == Decimal("1000")


def test_materialized_row_updates_on_sell(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "10", "100")
    sell(svc, pid, "AAPL", "4", "150")
    row = svc.store.get_materialized_position(pid, "AAPL")
    assert Decimal(row["quantity"]) == Decimal("6")
    assert Decimal(row["costBasis"]) == Decimal("600")


def test_read_self_heals_a_missing_materialized_row(tmp_path):
    import asyncio

    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "10", "100")
    svc.store.delete_materialized_position(pid, "AAPL")
    assert svc.store.get_materialized_position(pid, "AAPL") is None
    marks = {"AAPL": {"price": "110", "timestamp": "2026-10-08T00:00:00Z"}}
    read = asyncio.run(svc.read(pid, marks=marks, include=["positions"]))
    assert read["positions"][0]["symbol"] == "AAPL"
    # the cache was rebuilt from the ledger
    assert svc.store.get_materialized_position(pid, "AAPL") is not None


def test_rebuild_all_restores_consistency(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "10", "100")
    buy(svc, pid, "MSFT", "5", "200")
    svc.store.delete_materialized_position(pid)
    out = svc.rebuild_all(pid)
    assert out["status"] == "SUCCESS"
    assert out["symbols"] == 2
    assert Decimal(svc.store.get_materialized_position(pid, "MSFT")["quantity"]) == Decimal("5")


def test_materialized_equals_fresh_ledger_recompute(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "10", "100")
    buy(svc, pid, "AAPL", "5", "120")
    sell(svc, pid, "AAPL", "8", "130")
    cached = svc.store.get_materialized_position(pid, "AAPL")
    fresh = svc._symbol_accounting(pid, "AAPL", svc._method(svc.store.get_portfolio(pid)))
    assert Decimal(cached["quantity"]) == fresh.remaining_qty
    assert Decimal(cached["costBasis"]) == fresh.remaining_cost_basis
    assert Decimal(cached["realizedPnl"]) == fresh.realized_pnl
