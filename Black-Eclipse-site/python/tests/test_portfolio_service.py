"""PortfolioService: mutations, safety, valuation, FX, data quality, rebalance."""

from __future__ import annotations

from decimal import Decimal

from portfolio_helpers import buy, make_portfolio, make_service, sell


def test_add_position_records_a_transaction_and_a_lot(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    out = buy(svc, pid, "AAPL", "10", "100")
    assert out["status"] == "SUCCESS"
    assert out["transaction"]["type"] == "BUY"
    assert out["position"]["quantity"] == "10.000000000000"


def test_negative_quantity_is_rejected(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    out = svc.add_transaction(pid, {"type": "BUY", "symbol": "AAPL", "quantity": "-1", "price": "10"})
    assert out["status"] == "FAILED"
    assert out["error"]["code"] == "NEGATIVE_QUANTITY"


def test_zero_quantity_is_rejected(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    out = svc.add_transaction(pid, {"type": "BUY", "symbol": "AAPL", "quantity": "0", "price": "10"})
    assert out["error"]["code"] == "ZERO_QUANTITY"


def test_oversell_is_refused_without_writing(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "5", "100")
    out = sell(svc, pid, "AAPL", "10", "150")
    assert out["status"] == "FAILED"
    assert out["error"]["code"] == "INSUFFICIENT_POSITION"
    # the bad transaction must not be in the ledger
    assert svc.store.count_transactions(pid) == 1


def test_update_position_appends_adjustment_and_preserves_history(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "10", "100", date="2024-01-01")
    out = svc.update_position(pid, {"symbol": "AAPL", "target_quantity": "7", "reason": "reconciliation"})
    assert out.get("changed") is True
    # history survives: the original BUY is still there, plus an ADJUSTMENT
    assert svc.store.count_transactions(pid) == 2
    types = {t.transaction_type.value for t in svc.store.list_transactions(pid)}
    assert {"BUY", "ADJUSTMENT"} <= types
    audit = svc.store.list_audit(pid)
    assert any(e["kind"] == "POSITION_CORRECTED" and e["reason"] == "reconciliation" for e in audit)


def test_update_position_requires_reason(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "10", "100")
    out = svc.update_position(pid, {"symbol": "AAPL", "target_quantity": "7"})
    assert out["status"] == "FAILED"


async def test_remove_position_records_a_sell(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "10", "100")
    out = await svc.remove_position(pid, {"symbol": "AAPL", "price": "150"})
    assert out["status"] == "SUCCESS"
    types = [t.transaction_type.value for t in svc.store.list_transactions(pid)]
    assert types.count("SELL") == 1


async def test_valuation_with_fx_and_data_quality(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc, base="USD")
    svc.add_transaction(pid, {"type": "DEPOSIT", "gross_amount": "100000"})
    buy(svc, pid, "SAP", "10", "100", currency="EUR")
    marks = {
        "SAP": {"price": "110", "currency": "EUR", "timestamp": "2026-10-08T00:00:00Z"},
        "USD/EUR": {"rate": "0.9", "timestamp": "2026-10-08T00:00:00Z"},
    }
    read = await svc.read(pid, marks=marks, include=["positions", "pnl", "allocation", "exposure"])
    pos = read["positions"][0]
    # 10 * 110 EUR = 1100 EUR; EUR per USD = 0.9 ⇒ /0.9 ⇒ 1222.22 USD
    assert Decimal(pos["marketValueBase"]) == Decimal("1222.22222222")
    assert read["dataQuality"]["status"] == "OK"


async def test_missing_price_is_reported_not_fabricated(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "10", "100")
    read = await svc.read(pid, marks={}, include=["positions", "pnl"])
    assert read["valuation"]["totalValue"] == "-1000.00000000"  # cash -1000, no price
    assert "AAPL" in read["dataQuality"]["missingPrices"]
    assert read["dataQuality"]["status"] == "PARTIAL"


async def test_missing_fx_is_reported(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc, base="USD")
    buy(svc, pid, "SAP", "10", "100", currency="EUR")
    marks = {"SAP": {"price": "110", "currency": "EUR", "timestamp": "2026-10-08T00:00:00Z"}}
    read = await svc.read(pid, marks=marks, include=["positions"])
    assert "USD/EUR" in read["dataQuality"]["missingFX"]
    assert read["positions"][0]["marketValueBase"] is None


async def test_allocation_reconciles(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    svc.add_transaction(pid, {"type": "DEPOSIT", "gross_amount": "10000"})
    buy(svc, pid, "AAPL", "10", "100")
    buy(svc, pid, "MSFT", "10", "100")
    marks = {"AAPL": {"price": "100", "timestamp": "2026-10-08T00:00:00Z"},
             "MSFT": {"price": "100", "timestamp": "2026-10-08T00:00:00Z"}}
    read = await svc.read(pid, marks=marks, include=["allocation", "exposure"])
    assert read["allocation"]["asset"]["reconciles"] is True
    assert abs(read["allocation"]["asset"]["weightSum"] - 100.0) < 1e-4
    assert Decimal(read["exposure"]["asset"]["netExposure"]) == Decimal("2000")


async def test_rebalance_is_proposal_only(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    svc.add_transaction(pid, {"type": "DEPOSIT", "gross_amount": "10000"})
    buy(svc, pid, "AAPL", "10", "100")
    buy(svc, pid, "MSFT", "10", "100")
    marks = {"AAPL": {"price": "100", "timestamp": "2026-10-08T00:00:00Z"},
             "MSFT": {"price": "100", "timestamp": "2026-10-08T00:00:00Z"}}
    before = svc.store.count_transactions(pid)
    out = await svc.rebalance(pid, {"target": {"AAPL": 0.5, "MSFT": 0.5}, "marks": marks,
                                    "allowed_drift": 0.0, "persist": True})
    assert out["status"] == "PROPOSED"
    assert "proposal-only" in out["execution"]
    # rebalancing must never write a trade
    assert svc.store.count_transactions(pid) == before
    assert svc.store.list_rebalance_plans(pid)[0]["id"] == out["planId"]


async def test_rebalance_estimates_tax_when_rates_configured(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    svc.add_transaction(pid, {"type": "DEPOSIT", "gross_amount": "100000"})
    buy(svc, pid, "AAPL", "100", "100", date="2024-01-01")
    marks = {"AAPL": {"price": "200", "timestamp": "2026-10-08T00:00:00Z"}}
    out = await svc.rebalance(pid, {
        "target": {"AAPL": 0.1}, "marks": marks, "allowed_drift": 0.0,
        "tax_rules": {"longTermRate": "0.20", "shortTermRate": "0.37"},
    })
    sell_rec = next(r for r in out["recommendations"] if r["action"] == "SELL")
    assert sell_rec["taxImpact"] is not None
    assert Decimal(sell_rec["estRealizedPnl"]) > 0
