"""Tests for the trade-log analysis and the prop-firm assumptions surface."""

from __future__ import annotations

import pytest

from harness.quant.propfirm import get_spec
from harness.quant.propfirm_mc import PropFirmMonteCarloConfig, run_prop_firm_monte_carlo
from harness.quant.trade_log import analyse_trade_log


def _bars(n=400):
    bars = []
    price = 100.0
    for i in range(n):
        drift = 0.004 if (i // 40) % 2 == 0 else -0.003
        price *= 1 + drift + (0.002 if i % 7 < 4 else -0.002)
        bars.append({"time": 1700000000000 + i * 86400000, "o": price * 0.997,
                     "h": price * 1.008, "l": price * 0.992, "c": price, "v": 1000.0})
    return bars


def _iso(ms):
    from datetime import datetime, timezone

    return (datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
            .isoformat().replace("+00:00", "Z"))


def test_an_empty_log_is_reported_not_analysed():
    analysis = analyse_trade_log([], {})
    assert analysis.to_dict()["entryCount"] == 0
    assert analysis.warnings[0]["code"] == "TRADE_LOG_EMPTY"


def test_each_entry_is_placed_on_the_regime_of_its_entry_bar():
    bars = _bars(400)
    trades = [
        {"id": "t1", "symbol": "TEST", "netPnl": 100.0,
         "exitTs": _iso(bars[50]["time"])},
        {"id": "t2", "symbol": "TEST", "netPnl": -50.0,
         "exitTs": _iso(bars[300]["time"])},
    ]
    analysis = analyse_trade_log(trades, {"TEST": bars})
    assert len(analysis.entries) == 2
    for entry in analysis.entries:
        assert entry.regime, "an entry must be placed on a regime"
        assert "_" in entry.regime
        assert entry.trend in ("up", "down", "flat")
        assert entry.volatility in ("high", "normal", "low")
    assert analysis.coverage["unclassifiedEntries"] == 0


def test_the_pnl_is_attributed_per_regime():
    bars = _bars(400)
    trades = [
        {"id": f"t{i}", "symbol": "TEST", "netPnl": 100.0 if i % 2 else -40.0,
         "exitTs": _iso(bars[i * 4]["time"])} for i in range(50)
    ]
    analysis = analyse_trade_log(trades, {"TEST": bars})
    assert analysis.by_regime
    total = sum(float(bucket["netPnl"]) for bucket in analysis.by_regime.values())
    assert total == pytest.approx(analysis.totals["netPnl"], rel=1e-6)
    for bucket in analysis.by_regime.values():
        assert bucket["winRate"] is not None
        assert bucket["grossPositiveShare"] is None or 0 <= bucket["grossPositiveShare"] <= 100


def test_an_entry_with_no_bars_is_counted_but_not_given_a_regime():
    bars = _bars(200)
    trades = [
        {"id": "t1", "symbol": "TEST", "netPnl": 10.0, "exitTs": _iso(bars[10]["time"])},
        {"id": "t2", "symbol": "OTHER", "netPnl": 20.0, "exitTs": _iso(bars[11]["time"])},
    ]
    analysis = analyse_trade_log(trades, {"TEST": bars})
    assert analysis.totals["trades"] == 2
    assert analysis.coverage["unclassifiedEntries"] == 1
    assert any(w["code"] == "TRADE_LOG_ENTRIES_UNCLASSIFIED" for w in analysis.warnings)
    assert analysis.by_regime["unclassified"]["trades"] == 1


def test_a_profit_concentrated_in_a_few_entries_is_flagged():
    bars = _bars(400)
    trades = [{"id": "t1", "symbol": "TEST", "netPnl": 10_000.0,
               "exitTs": _iso(bars[10]["time"])}]
    trades += [{"id": f"s{i}", "symbol": "TEST", "netPnl": 1.0,
                "exitTs": _iso(bars[i]["time"])} for i in range(30)]
    analysis = analyse_trade_log(trades, {"TEST": bars})
    assert analysis.concentration["topShareOfGrossPositive"] > 99.0
    assert any(w["code"] == "TRADE_LOG_PROFIT_CONCENTRATED" for w in analysis.warnings)


def test_an_evenly_profitable_log_is_not_flagged():
    bars = _bars(400)
    trades = [{"id": f"t{i}", "symbol": "TEST", "netPnl": 100.0,
               "exitTs": _iso(bars[i * 4]["time"])} for i in range(50)]
    analysis = analyse_trade_log(trades, {"TEST": bars})
    assert not any(w["code"] == "TRADE_LOG_PROFIT_CONCENTRATED" for w in analysis.warnings)


def test_the_coverage_reports_the_regimes_the_log_actually_saw():
    bars = _bars(400)
    trades = [{"id": f"t{i}", "symbol": "TEST", "netPnl": 10.0,
               "exitTs": _iso(bars[i * 5]["time"])} for i in range(40)]
    analysis = analyse_trade_log(trades, {"TEST": bars})
    assert analysis.coverage["regimeCount"] >= 1
    assert analysis.coverage["knownRegimes"] == 9
    assert 0 < analysis.coverage["coverageShare"] <= 1.0


# ── the prop-firm assumptions surface ─────────────────────────────────────────

def _trades(n=60):
    return [{"id": f"t{i}", "netPnl": 100.0,
             "exitTs": f"2026-01-{i % 28 + 1:02d}T12:00:00Z"} for i in range(n)]


def test_a_missing_fee_is_reported_and_the_ev_is_marked_as_gross():
    spec = get_spec("topstep")
    report = run_prop_firm_monte_carlo(_trades(), spec, spec.size("50k"),
                                       PropFirmMonteCarloConfig(simulations=20, seed=1))
    assert report["assumptions"]["feeSupplied"] is False
    assert "GROSS" in report["assumptions"]["note"]
    assert any("PROP_FIRM_NO_FEE_SUPPLIED" in w for w in report["warnings"])


def test_a_supplied_fee_is_stated_and_not_warned_about():
    spec = get_spec("topstep")
    report = run_prop_firm_monte_carlo(_trades(), spec, spec.size("50k"),
                                       PropFirmMonteCarloConfig(simulations=20, seed=1,
                                                                fee_per_attempt=49.0,
                                                                reset_fee=49.0))
    assert report["assumptions"]["feeSupplied"] is True
    assert report["assumptions"]["feePerAttempt"] == 49.0
    assert not any("PROP_FIRM_NO_FEE_SUPPLIED" in w for w in report["warnings"])
