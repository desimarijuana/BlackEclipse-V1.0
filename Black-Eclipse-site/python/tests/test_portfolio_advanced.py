"""Advanced engines: HIFO/SPECIFIC_ID, more corporate actions, crypto events,
attribution, optimizer, factor exposure, hedging, reconciliation, aggregation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from harness.portfolio.accounting import compute_accounting
from harness.portfolio.attribution import brinson_attribution
from harness.portfolio.models import CostBasisMethod, Transaction, TransactionType
from harness.portfolio.optimizer import optimize
from harness.portfolio.reconciliation import reconcile
from harness.portfolio.risk import factor_exposure
from portfolio_helpers import buy, make_portfolio, make_service


def tx(kind, qty, price=None, date="2024-01-01", symbol="X", **kw):
    return Transaction(portfolio_id="p", transaction_type=kind, symbol=symbol,
                       quantity=Decimal(qty), price=None if price is None else Decimal(price),
                       trade_date=date, **kw)


# ── Cost basis: HIFO / SPECIFIC_ID ───────────────────────────────────────────

def test_hifo_consumes_highest_cost_lot():
    txs = [tx(TransactionType.BUY, "10", "100"), tx(TransactionType.BUY, "10", "200"),
           tx(TransactionType.SELL, "10", "300")]
    r = compute_accounting("p", "X", txs, CostBasisMethod.HIFO)
    assert r.realized_cost_basis == Decimal("2000")
    assert r.realized_pnl == Decimal("1000")


def test_specific_id_consumes_named_lot():
    txs = [tx(TransactionType.BUY, "10", "100"), tx(TransactionType.BUY, "10", "200")]
    base = compute_accounting("p", "X", txs, CostBasisMethod.FIFO)
    cheap_lot = min(base.open_lots, key=lambda l: l.cost_per_unit)
    sell = tx(TransactionType.SELL, "10", "300")
    sell.lot_selection = [{"lotId": cheap_lot.id, "quantity": "10"}]
    r = compute_accounting("p", "X", txs + [sell], CostBasisMethod.SPECIFIC_ID)
    assert r.realized_cost_basis == Decimal("1000")
    assert r.realized_pnl == Decimal("2000")


# ── Corporate actions ────────────────────────────────────────────────────────

def _lots(svc, pid):
    return {s["symbol"]: s for s in svc.calculate_tax_lots(pid, persist=True)["symbols"]}


def test_rights_issue_acquires_at_subscription_price(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    svc.add_transaction(pid, {"type": "DEPOSIT", "gross_amount": "10000"})
    out = svc.apply_corporate_action(pid, {"action": "RIGHTS_ISSUE", "symbol": "ABC",
                                           "quantity": "20", "price": "30"})
    assert out["status"] == "SUCCESS"
    lots = _lots(svc, pid)
    assert Decimal(lots["ABC"]["remainingQuantity"]) == Decimal("20")
    assert Decimal(lots["ABC"]["remainingCostBasis"]) == Decimal("600")


def test_warrant_exercise_carries_warrant_basis_plus_strike(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    svc.add_transaction(pid, {"type": "DEPOSIT", "gross_amount": "10000"})
    buy(svc, pid, "W", "10", "2")
    out = svc.apply_corporate_action(pid, {"action": "WARRANT_EXERCISE", "warrant_symbol": "W",
                                           "underlying_symbol": "U", "quantity": "10", "ratio": "1", "strike": "5"})
    assert out["status"] == "SUCCESS"
    lots = _lots(svc, pid)
    assert Decimal(lots["W"]["remainingQuantity"]) == Decimal("0")
    assert Decimal(lots["U"]["remainingQuantity"]) == Decimal("10")
    # warrant basis 20 + strike 50 = 70
    assert Decimal(lots["U"]["remainingCostBasis"]) == Decimal("70")


def test_return_of_capital_reduces_basis(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "ABC", "10", "100")  # basis 1000
    out = svc.apply_corporate_action(pid, {"action": "RETURN_OF_CAPITAL", "symbol": "ABC",
                                           "amount_per_share": "5"})
    assert out["status"] == "SUCCESS"
    lots = _lots(svc, pid)
    assert Decimal(lots["ABC"]["remainingCostBasis"]) == Decimal("950")


def test_return_of_capital_excess_is_a_taxable_gain(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "ABC", "10", "10")  # basis 100
    out = svc.apply_corporate_action(pid, {"action": "RETURN_OF_CAPITAL", "symbol": "ABC",
                                           "total_amount": "150"})
    assert out["status"] == "SUCCESS"
    assert Decimal(out["taxableGain"]) == Decimal("50")
    lots = _lots(svc, pid)
    assert Decimal(lots["ABC"]["remainingCostBasis"]) == Decimal("0")
    assert Decimal(lots["ABC"]["realizedPnl"]) == Decimal("50")


# ── Crypto / derivatives events ──────────────────────────────────────────────

def test_slashing_realizes_a_loss(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "SOL", "10", "20")
    out = svc.apply_slashing(pid, {"symbol": "SOL", "quantity": "4"})
    assert out["status"] == "SUCCESS"
    lots = _lots(svc, pid)
    assert Decimal(lots["SOL"]["remainingQuantity"]) == Decimal("6")
    assert Decimal(lots["SOL"]["realizedPnl"]) == Decimal("-80")


def test_funding_payment_is_signed_cash(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    out = svc.record_funding(pid, {"symbol": "BTCUSDT", "amount": "12.5"})
    assert out["status"] == "SUCCESS"
    assert Decimal(out["transaction"]["cashImpact"]) == Decimal("12.5")


# ── Optimizer ────────────────────────────────────────────────────────────────

def test_min_variance_tilts_to_lower_variance_asset():
    cov = [[0.04, 0.0], [0.0, 0.01]]
    res = optimize(["A", "B"], covariance=cov, method="min_variance")
    assert res["available"] is True
    assert res["fullyInvested"] is True
    assert res["boundsRespected"] is True
    assert res["weights"]["B"] > res["weights"]["A"]
    equal_var = 0.25 * 0.04 + 0.25 * 0.01
    assert res["variance"] <= equal_var + 1e-9


def test_optimizer_respects_max_weight():
    res = optimize(["A", "B"], covariance=[[0.04, 0], [0, 0.01]],
                   max_weights=[0.6, 0.6], method="min_variance")
    assert res["weights"]["B"] <= 0.6 + 1e-6


def test_optimizer_turnover_cap():
    res = optimize(["A", "B"], covariance=[[0.04, 0], [0, 0.01]],
                   current_weights=[0.5, 0.5], turnover_cap=0.1, method="min_variance")
    assert res["turnover"] <= 0.1 + 1e-6


def test_inverse_volatility_weights():
    res = optimize(["A", "B"], covariance=[[0.04, 0], [0, 0.01]], method="inverse_volatility")
    # B has half the vol -> twice the weight
    assert res["weights"]["B"] > res["weights"]["A"]


# ── Attribution / factor exposure ────────────────────────────────────────────

def test_brinson_effects_sum_to_active_return():
    segments = [
        {"group": "Tech", "portfolioWeight": 0.6, "benchmarkWeight": 0.5,
         "portfolioReturn": 0.10, "benchmarkReturn": 0.08},
        {"group": "Energy", "portfolioWeight": 0.4, "benchmarkWeight": 0.5,
         "portfolioReturn": 0.02, "benchmarkReturn": 0.04},
    ]
    res = brinson_attribution(segments)
    assert res["available"] is True
    assert abs(res["effects"]["total"] - res["activeReturn"]) < 1e-9


def test_factor_exposure_weighted_sum():
    loadings = {"A": {"market": 1.2, "value": 0.3}, "B": {"market": 0.8, "value": -0.2}}
    res = factor_exposure({"A": 0.5, "B": 0.5}, loadings)
    assert res["exposures"]["market"] == pytest.approx(1.0)
    assert res["exposures"]["value"] == pytest.approx(0.05)


# ── Reconciliation ───────────────────────────────────────────────────────────

def test_reconcile_matched_mismatch_missing():
    internal = [{"symbol": "AAPL", "quantity": "10"}, {"symbol": "MSFT", "quantity": "5"}]
    external = [{"symbol": "AAPL", "quantity": "10"}, {"symbol": "MSFT", "quantity": "6"},
                {"symbol": "TSLA", "quantity": "1"}]
    res = reconcile(internal, external)
    by = {i["symbol"]: i["status"] for i in res["items"]}
    assert by["AAPL"] == "MATCHED"
    assert by["MSFT"] == "MISMATCH"
    assert by["TSLA"] == "MISSING"
    assert res["status"] == "MISMATCH"
    assert res["clean"] is False


def test_reconcile_clean(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "10", "100")
    out = svc.reconcile(pid, {"external_positions": [{"symbol": "AAPL", "quantity": "10"}]})
    assert out["status"] == "MATCHED"
    assert out["clean"] is True


# ── Aggregation / hedging ────────────────────────────────────────────────────

def test_aggregate_across_portfolios(tmp_path):
    import asyncio

    svc = make_service(tmp_path)
    p1 = make_portfolio(svc)
    buy(svc, p1, "AAPL", "10", "100")
    p2 = make_portfolio(svc)
    buy(svc, p2, "MSFT", "5", "200")
    marks = {"AAPL": {"price": "100", "timestamp": "2026-10-08T00:00:00Z"},
             "MSFT": {"price": "200", "timestamp": "2026-10-08T00:00:00Z"}}
    out = asyncio.run(svc.aggregate({"portfolio_ids": [p1, p2], "marks": marks}))
    # AAPL 1000 + MSFT 1000, minus 2000 cash (no deposits) = 0
    assert out["portfolioCount"] == 2
    assert Decimal(out["investedValue"]) == Decimal("2000")


async def test_hedge_proposes_fx_offset(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc, base="USD")
    svc.add_transaction(pid, {"type": "DEPOSIT", "gross_amount": "100000"})
    buy(svc, pid, "SAP", "10", "100", currency="EUR")
    marks = {"SAP": {"price": "110", "currency": "EUR", "timestamp": "2026-10-08T00:00:00Z"},
             "USD/EUR": {"rate": "0.9", "timestamp": "2026-10-08T00:00:00Z"}}
    out = await svc.hedge(pid, {"marks": marks, "target_flat": True})
    assert out["baseCurrency"] == "USD"
    assert out["proposals"][0]["currency"] == "EUR"
    assert out["proposals"][0]["direction"] == "SELL"
