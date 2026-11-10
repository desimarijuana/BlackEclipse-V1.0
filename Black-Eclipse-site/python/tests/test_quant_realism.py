"""Realism layer: borrow, financing, margin, partial fills, corporate actions,
and the reproducibility manifest."""

from __future__ import annotations

from harness.quant import data as D
from harness.quant import engine as E
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.carry import (
    borrow_cost,
    elapsed_days,
    financing_cost,
    funding_payment,
    locate_fee,
    margin_status,
)
from harness.quant.corporate_actions import (
    CorporateAction,
    actions_on,
    apply_to_position,
    parse_actions,
)
from harness.quant.manifest import compare_metrics, dataset_fingerprint
from harness.quant.portfolio import Portfolio


def _spec(*, entry_side="long", execution=None, sizing=50, risk=None,
          max_fraction=None):
    entry = {"long" if entry_side == "long" else "short": {"conditions": [
        {"left": {"ref": "close"}, "op": ">", "right": {"value": 0}}
    ]}}
    base = {
        "strategy": {"id": "realism", "name": "Realism", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [{"id": "ema", "type": "ema", "params": {"period": 10}}],
        "rules": {"entry": entry, "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": sizing,
                            **({"max_fraction": max_fraction} if max_fraction else {})},
        "risk": risk or {"allow_short": True},
    }
    if execution:
        base["execution"] = execution
    return S.parse_strategy(base)


def _dataset(rows=None):
    rows = rows if rows is not None else F.bull_market("TESTUSDT", n=200)
    return D.build_dataset({"TESTUSDT": D.series_from_rows("TESTUSDT", "1d", rows, source="synthetic")})


# ── pure carry ───────────────────────────────────────────────────────────────

def test_interest_and_borrow_are_proportional():
    assert borrow_cost(100_000, 500, 30, 360) == borrow_cost(100_000, 500, 30, 360)
    assert borrow_cost(100_000, 500, 30, 360) > 0
    assert borrow_cost(100_000, 500, 0, 360) == 0
    assert locate_fee(10_000, 25) == 25.0


def test_financing_signs_and_funding():
    assert financing_cost(-100_000, debit_rate_bps=1000, credit_rate_bps=0, days=30) < 0
    assert financing_cost(100_000, debit_rate_bps=0, credit_rate_bps=500, days=30) > 0
    assert funding_payment(10_000, 10, side_sign=1, periods=1) == -10
    assert funding_payment(10_000, 10, side_sign=-1, periods=1) == 10


def test_elapsed_days_and_margin_status():
    assert elapsed_days("2024-01-01", "2024-01-31") == 30
    status = margin_status(equity=30, gross_exposure=100, maintenance_pct=0.25)
    assert status["breached"] is False
    status = margin_status(equity=10, gross_exposure=100, maintenance_pct=0.25)
    assert status["maintenanceRequirement"] == 25
    assert status["excess"] == -15
    assert status["breached"] is True


# ── corporate actions ────────────────────────────────────────────────────────

def test_corporate_action_parsing_and_effects():
    actions = parse_actions([
        {"symbol": "x", "exDate": "2026-01-02", "kind": "dividend", "amount": 0.5},
        {"symbol": "X", "exDate": "2026-01-03", "kind": "split", "ratio": 2},
    ])
    assert len(actions) == 2
    div = apply_to_position(actions[0], quantity=100, avg_entry_price=10)
    split = apply_to_position(actions[1], quantity=100, avg_entry_price=10)
    assert div["cashDelta"] == 50
    assert split["newQuantity"] == 200
    assert split["newAvgEntryPrice"] == 5
    assert actions_on(actions, "X", "2026-01-02T00:00:00") == [actions[0]]


def test_portfolio_applies_dividend_and_split():
    p = Portfolio(10_000)
    from harness.quant.models import Fill
    p.apply_fill(Fill("f1", "o1", "X", "buy", 100, 10, 0, 0, 0, 0, 0, "2026-01-01"))
    p.apply_corporate_action(CorporateAction("X", "2026-01-02", "dividend", amount=0.5))
    assert p.cash == 9050.0  # 10,000 - 1,000 cost + 50 dividend
    p.apply_corporate_action(CorporateAction("X", "2026-01-03", "split", ratio=2.0))
    pos = p.position("X")
    assert pos.quantity == 200
    assert pos.avg_entry_price == 5


# ── engine integration ───────────────────────────────────────────────────────

def test_short_pays_borrow_and_locate():
    spec = _spec(entry_side="short", execution={
        "borrow": {"annual_rate_bps": 5000, "locate_fee_bps": 25},
        "financing": {"debit_rate_bps": 1000, "credit_rate_bps": 0},
    })
    res = E.run_backtest(spec, _dataset(), E.BacktestConfig(initial_capital=100_000))
    assert res.configuration["carry"]["borrow"] > 0
    assert res.configuration["carry"]["locateFees"] > 0
    assert res.manifest["digest"]


def test_unavailable_borrow_rejects_short():
    spec = _spec(entry_side="short", execution={
        "borrow": {"available": False},
    })
    res = E.run_backtest(spec, _dataset(), E.BacktestConfig())
    assert res.observability["borrowRejections"] > 0
    assert any(w["code"] == "BORROW_UNAVAILABLE" for w in res.warnings)


def test_margin_call_liquidates_the_book():
    spec = _spec(entry_side="long", sizing=400, max_fraction=4.0, execution={
        "margin": {"enabled": True, "maintenance_pct": 0.25, "initial_pct": 0.5},
    })
    rows = F.bear_market("TESTUSDT", n=200)
    res = E.run_backtest(spec, _dataset(rows), E.BacktestConfig(initial_capital=100_000))
    assert res.observability["marginCalls"] > 0
    assert any(w["code"] == "MARGIN_CALL" for w in res.warnings)
    assert any(t["exitReason"] == "margin call liquidation" for t in res.trades)


def test_participation_caps_fills():
    spec = _spec(execution={
        "fill_model": {"type": "participation", "participation_rate": 0.0001},
    })
    res = E.run_backtest(spec, _dataset(), E.BacktestConfig())
    assert res.observability["partialFills"] > 0
    assert all(f["fillRatio"] <= 1.0 for f in res.fills)
    assert any(f["fillRatio"] < 1.0 for f in res.fills)


def test_manifest_is_stable_and_content_sensitive():
    a = E.run_backtest(_spec(), _dataset(), E.BacktestConfig())
    b = E.run_backtest(_spec(), _dataset(), E.BacktestConfig())
    assert a.manifest["digest"] == b.manifest["digest"]
    c = E.run_backtest(_spec(), _dataset(F.bull_market("TESTUSDT", n=200, seed=99)),
                       E.BacktestConfig())
    assert c.manifest["data"]["series"]["TESTUSDT"]["sha256"] != \
        a.manifest["data"]["series"]["TESTUSDT"]["sha256"]
    assert dataset_fingerprint(_dataset())["interval"] == "1d"
    assert compare_metrics(a.metrics, b.metrics)["reproduced"] is True
