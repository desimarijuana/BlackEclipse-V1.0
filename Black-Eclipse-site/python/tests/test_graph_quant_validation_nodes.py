"""Validation nodes: the edge verdict, benchmark comparison and resampling.

Each node is an adapter over an already-tested engine
(``harness/quant/{verdict,benchmark,transform}.py``). These tests pin the three
things the adapters own: the input contract, the honest failure when a required
piece of evidence is missing, and that nothing is silently scored as zero.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.quant import fixtures as F
from harness.quant.verdict import GRADES

REGISTRY = build_default_registry()


def _run(node_type: str, inputs: dict, config: dict | None = None) -> dict:
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type,
        run_id="run",
        mode=ExecutionMode.BACKTEST,
        inputs=inputs,
        config=config or {},
    ))


def _metrics(**overrides) -> dict:
    metrics = {
        "total_return": 42.0,
        "sharpe": 1.2,
        "profit_factor": 1.6,
        "expectancy": 12.5,
        "max_drawdown": -12.0,
        "ulcer_index": 4.0,
        "trade_count": 120,
    }
    metrics.update(overrides)
    return metrics


def _trades(count: int = 120) -> list[dict]:
    return [{"netPnl": 25.0 if index % 3 else -10.0} for index in range(count)]


# ── quant.grade ─────────────────────────────────────────────────────────────


def test_grade_returns_a_graded_verdict():
    result = _run("quant.grade", {"metrics": _metrics(), "trades": _trades()})
    verdict = result["verdict"]
    assert verdict["available"] is True
    assert verdict["grade"] in GRADES
    assert 0.0 <= verdict["score"] <= 100.0
    assert set(verdict["components"]) == {"edge", "robustness", "risk", "sample"}
    assert isinstance(result["summary"], str) and result["summary"].startswith("Grade")
    assert isinstance(result["flags"], list)


def test_grade_is_honest_about_the_axes_it_could_not_test():
    result = _run("quant.grade", {"metrics": _metrics()})
    verdict = result["verdict"]
    codes = {flag["code"] for flag in verdict["flags"]}
    # No Monte Carlo and no trades wired: those axes are named, not scored zero.
    assert "ROBUSTNESS_NOT_TESTED" in codes
    assert verdict["components"]["robustness"]["score"] is None
    assert "robustness" not in verdict["assumptions"]["gradedOn"]


def test_monte_carlo_wires_the_robustness_axis():
    monte_carlo = {"probabilityOfLoss": 18.0, "returnPercentiles": {"p5": 2.0}}
    result = _run(
        "quant.grade",
        {"metrics": _metrics(), "trades": _trades(), "monteCarlo": monte_carlo},
    )
    verdict = result["verdict"]
    assert verdict["components"]["robustness"]["score"] is not None
    assert "robustness" in verdict["assumptions"]["gradedOn"]


def test_critical_flags_cap_the_grade():
    result = _run(
        "quant.grade",
        {"metrics": _metrics(profit_factor=0.5, trade_count=3, expectancy=-2.0)},
    )
    verdict = result["verdict"]
    codes = {flag["code"] for flag in verdict["flags"]}
    assert {"PROFIT_FACTOR_BELOW_ONE", "SAMPLE_TOO_SMALL", "EXPECTANCY_NOT_POSITIVE"} <= codes
    # CRITICAL_FLAG_MAX_GRADE is D: a good Sharpe cannot average a critical flag away.
    assert verdict["grade"] in ("D", "E", "F")
    assert verdict["flagCounts"]["critical"] >= 1


def test_grade_reads_the_equity_curve_from_a_result_object():
    # Returns with strong positive autocorrelation -> a fitted, too-smooth curve.
    equity = [100_000.0]
    ret = 0.004
    for _ in range(60):
        ret = 0.0002 + 0.97 * ret
        equity.append(equity[-1] * (1.0 + ret))
    curve = [{"ts": f"2023-01-{index + 1:02d}T00:00:00Z", "equity": value}
             for index, value in enumerate(equity)]
    result = _run(
        "quant.grade",
        {"metrics": _metrics(), "trades": _trades(), "result": {"equityCurve": curve}},
    )
    codes = {flag["code"] for flag in result["verdict"]["flags"]}
    assert "EQUITY_CURVE_SUSPICIOUSLY_SMOOTH" in codes


def test_grade_requires_the_engine_metrics():
    with pytest.raises(ValueError, match="metrics"):
        _run("quant.grade", {})
    with pytest.raises(ValueError, match="metrics"):
        _run("quant.grade", {"metrics": [1, 2, 3]})


def test_grade_rejects_a_non_array_trades_input():
    with pytest.raises(ValueError, match="trades"):
        _run("quant.grade", {"metrics": _metrics(), "trades": "nope"})


# ── quant.benchmark ─────────────────────────────────────────────────────────


def _equity_curve(rows: list[dict], start: float = 100_000.0) -> list[dict]:
    equity = start
    curve = [{"ts": rows[0]["timestamp"], "equity": equity}]
    for index in range(1, len(rows)):
        equity *= 1.0 + 0.0008 + (0.0004 if index % 2 else -0.0002)
        curve.append({"ts": rows[index]["timestamp"], "equity": round(equity, 2)})
    return curve


def test_benchmark_reports_alpha_beta_and_tracking_error():
    rows = F.bull_market("BENCH", n=120)
    result = _run(
        "quant.benchmark",
        {
            "result": {"equityCurve": _equity_curve(rows)},
            "benchmark": {"symbol": "BENCH", "interval": "1d", "rows": rows},
        },
    )
    metrics = result["metrics"]
    assert metrics["available"] is True
    assert metrics["observations"] >= 3
    assert isinstance(metrics["beta"], float)
    assert isinstance(metrics["alpha"], float)
    assert result["summary"].startswith("vs benchmark")


def test_benchmark_requires_an_equity_curve():
    rows = F.bull_market("BENCH", n=60)
    with pytest.raises(ValueError, match="includeSeries"):
        _run(
            "quant.benchmark",
            {"result": {"metrics": {}}, "benchmark": {"rows": rows}},
        )


def test_benchmark_without_overlap_is_unavailable_not_zero():
    equity = [{"ts": f"2019-01-{index + 1:02d}T00:00:00Z", "equity": 100_000.0 + index}
              for index in range(1, 20)]
    rows = F.bull_market("BENCH", n=60)
    result = _run(
        "quant.benchmark",
        {"result": {"equityCurve": equity}, "benchmark": {"rows": rows}},
    )
    assert result["metrics"]["available"] is False
    assert result["metrics"]["reason"]
    assert result["summary"].startswith("not available")


# ── quant.resample ──────────────────────────────────────────────────────────


def test_resample_aggregates_hourly_bars_into_daily_buckets():
    rows = F.bull_market("HOURLY", n=48, interval_min=60)
    result = _run(
        "quant.resample",
        {"series": {"symbol": "HOURLY", "interval": "1h", "rows": rows}},
        {"targetInterval": "1d"},
    )
    series = result["series"]
    assert series["symbol"] == "HOURLY"
    assert series["interval"] == "1d"
    assert series["sourceInterval"] == "1h"
    assert len(series["rows"]) == 2
    assert result["metadata"]["inputBars"] == 48
    assert result["metadata"]["outputBars"] == 2
    assert result["metadata"]["partialBuckets"] == 0

    first = series["rows"][0]
    window = rows[:24]
    assert first["open"] == window[0]["open"]
    assert first["close"] == window[-1]["close"]
    assert first["high"] == max(row["high"] for row in window)
    assert first["low"] == min(row["low"] for row in window)
    assert first["volume"] == pytest.approx(sum(row["volume"] for row in window))
    assert first["bars"] == 24


def test_resample_marks_a_partial_bucket_instead_of_hiding_it():
    rows = F.bull_market(
        "HOURLY", n=23, interval_min=60,
        start_time=dt.datetime(2023, 1, 1, 1, tzinfo=dt.timezone.utc),
    )
    result = _run(
        "quant.resample",
        {"series": {"symbol": "HOURLY", "interval": "1h", "rows": rows}},
        {"targetInterval": "1d"},
    )
    assert result["metadata"]["partialBuckets"] == 1
    assert result["series"]["rows"][0]["partial"] is True
    assert result["series"]["rows"][0]["bars"] == 23


def test_resample_refuses_to_manufacture_finert_bars():
    rows = F.bull_market("DAILY", n=20)
    with pytest.raises(ValueError, match="cannot resample"):
        _run(
            "quant.resample",
            {"series": {"symbol": "DAILY", "interval": "1d", "rows": rows}},
            {"targetInterval": "1h"},
        )


def test_resample_requires_a_series():
    with pytest.raises(ValueError, match="OHLCV"):
        _run("quant.resample", {}, {"targetInterval": "1d"})


# ── quant.robustness ────────────────────────────────────────────────────────


def _series(n: int = 300) -> dict:
    return {"symbol": "TESTUSDT", "interval": "1d", "rows": F.bull_market("TESTUSDT", n=n)}


def test_robustness_returns_a_verdict_and_conclusions():
    config = {
        "preset": "ema_cross",
        "paramSpaceJson": '{"indicators.0.params.period": [5, 12], "indicators.1.params.period": [30, 50]}',
        "costMultipliersJson": "[1, 2]",
        "splits": 2,
    }
    first = _run("quant.robustness", {"series": _series(300)}, config)
    second = _run("quant.robustness", {"series": _series(300)}, config)
    assert first["result"]["kind"] == "robustness"
    assert first["result"]["status"] == "OK"
    assert first["result"]["verdict"] in ("robust", "fragile", "insufficient_evidence")
    assert isinstance(first["conclusions"], list)
    assert "sharpe" in first["metrics"]
    # Deterministic: same series + config => same verdict and conclusions.
    assert first["result"]["verdict"] == second["result"]["verdict"]
    assert first["conclusions"] == second["conclusions"]


def test_robustness_calls_a_small_sample_insufficient_evidence():
    result = _run(
        "quant.robustness",
        {"series": _series(120)},
        {"preset": "ema_cross", "minTrades": 10_000, "costMultipliersJson": "[1]"},
    )
    assert result["result"]["verdict"] == "insufficient_evidence"
    codes = {warning["code"] for warning in result["result"]["warnings"]}
    assert "LOW_SAMPLE_SIZE" in codes


def test_robustness_rejects_a_bad_cost_multiplier_list():
    with pytest.raises(ValueError, match="costMultipliersJson"):
        _run(
            "quant.robustness",
            {"series": _series(120)},
            {"preset": "ema_cross", "costMultipliersJson": "{not json"},
        )
    with pytest.raises(ValueError, match="greater than 0"):
        _run(
            "quant.robustness",
            {"series": _series(120)},
            {"preset": "ema_cross", "costMultipliersJson": "[1, 0]"},
        )


# ── quant.trade_analysis ────────────────────────────────────────────────────


def test_trade_analysis_places_entries_on_their_own_bars():
    backtest = _run(
        "quant.backtest",
        {"series": _series(240)},
        {"preset": "ema_cross", "fast": 5, "slow": 20},
    )
    trades = backtest["trades"]
    assert trades
    analysis = _run(
        "quant.trade_analysis",
        {"trades": trades, "series": _series(240)},
    )["analysis"]
    assert analysis["entryCount"] == len(analysis["entries"])
    assert analysis["coverage"]["unclassifiedEntries"] == 0
    assert analysis["coverage"]["regimeCount"] >= 1
    assert analysis["totals"]["trades"] > 0
    assert analysis["byRegime"]


def test_trade_analysis_without_series_marks_entries_unclassified():
    backtest = _run(
        "quant.backtest",
        {"series": _series(240)},
        {"preset": "ema_cross", "fast": 5, "slow": 20},
    )
    result = _run("quant.trade_analysis", {"trades": backtest["trades"]})
    assert result["analysis"]["coverage"]["unclassifiedEntries"] == len(backtest["trades"])
    codes = {warning["code"] for warning in result["analysis"]["warnings"]}
    assert "TRADE_LOG_ENTRIES_UNCLASSIFIED" in codes


def test_trade_analysis_requires_trades():
    with pytest.raises(ValueError, match="trades"):
        _run("quant.trade_analysis", {"trades": []})


# ── quant.multiple_testing ──────────────────────────────────────────────────


def _result_with_curve(n: int = 120) -> dict:
    rows = F.bull_market("BENCH", n=n)
    return {"equityCurve": _equity_curve(rows)}


def test_multiple_testing_deflates_by_the_trial_count():
    result = _run(
        "quant.multiple_testing",
        {
            "result": _result_with_curve(),
            "trials": [
                {"metrics": {"sharpe": 1.8}},
                {"metrics": {"sharpe": 1.1}},
                {"metrics": {"sharpe": 0.6}},
            ],
        },
    )
    deflated = result["deflated"]
    assert deflated["available"] is True
    assert deflated["trialCount"] == 3
    assert deflated["source"] == "trials"
    assert 0.0 <= deflated["deflatedSharpeRatio"] <= 1.0
    assert result["pbo"]["available"] is False
    assert "returnsMatrixJson" in result["pbo"]["reason"]
    assert result["summary"].startswith("deflated Sharpe")


def test_multiple_testing_computes_pbo_from_a_returns_matrix():
    rows = F.bull_market("BENCH", n=60)
    matrix = [
        [0.01 if (index + row) % 3 else -0.01 for index in range(24)]
        for row in range(4)
    ]
    result = _run(
        "quant.multiple_testing",
        {"result": {"equityCurve": _equity_curve(rows)}},
        {"returnsMatrixJson": json.dumps(matrix), "nSplits": 4},
    )
    pbo = result["pbo"]
    assert pbo["available"] is True
    assert pbo["configurations"] == 4
    assert 0.0 <= pbo["probabilityOfBacktestOverfitting"] <= 1.0
    assert "PBO" in result["summary"]


def test_multiple_testing_names_what_it_needs_when_nothing_is_wired():
    with pytest.raises(ValueError, match="no overfitting statistic"):
        _run("quant.multiple_testing", {})


def test_multiple_testing_accepts_a_trial_sharpe_fallback():
    result = _run(
        "quant.multiple_testing",
        {"result": _result_with_curve()},
        {"trialSharpesJson": "[2.0, 1.5, 0.9, 0.3]"},
    )
    assert result["deflated"]["available"] is True
    assert result["deflated"]["source"] == "trialSharpesJson"
    assert result["deflated"]["trialCount"] == 4


# ── quant.costs ─────────────────────────────────────────────────────────────


def test_costs_computes_the_configured_commission():
    result = _run(
        "quant.costs",
        {"orders": [{"side": "buy", "quantity": 100, "price": 100.0, "symbol": "AAA"}]},
        {
            "kind": "transaction",
            "executionJson": '{"commission": {"type": "percentage", "value": 0.1}}',
        },
    )
    assert result["total"] == pytest.approx(10.0)
    assert result["costs"]["orderCount"] == 1
    assert result["costs"]["orders"][0]["commission"] == pytest.approx(10.0)
    assert result["summary"].startswith("transaction")


def test_costs_default_model_is_frictionless_and_says_so():
    result = _run(
        "quant.costs",
        {"orders": [{"side": "sell", "quantity": 5, "price": 50.0}]},
    )
    assert result["total"] == pytest.approx(0.0)
    assert result["costs"]["frictionless"] is True
    codes = {warning["code"] for warning in result["costs"]["warnings"]}
    assert "COMMISSION_MODEL_NONE" in codes


def test_costs_rejects_a_bad_order_or_execution_block():
    with pytest.raises(ValueError, match="cost simulation failed"):
        _run("quant.costs", {"orders": [{"side": "buy", "price": 10.0}]})
    with pytest.raises(ValueError, match="non-empty orders"):
        _run("quant.costs", {"orders": []})
    with pytest.raises(ValueError, match="executionJson"):
        _run(
            "quant.costs",
            {"orders": [{"side": "buy", "quantity": 1, "price": 10.0}]},
            {"executionJson": "[1, 2]"},
        )


# ── quant.edge_report ───────────────────────────────────────────────────────


def test_edge_report_renders_the_document_charts_and_verdict():
    backtest = _run(
        "quant.backtest",
        {"series": _series(260)},
        {"preset": "ema_cross", "fast": 5, "slow": 20, "includeSeries": True},
    )
    result = _run("quant.edge_report", {"result": backtest["result"]})
    assert result["report"].startswith("# Edge Report")
    assert result["verdict"]["grade"] in ("A", "B", "C", "D", "E", "F")
    assert isinstance(result["charts"], list) and result["charts"]
    assert isinstance(result["verdict"]["summary"], str)


def test_edge_report_requires_the_artifact():
    with pytest.raises(ValueError, match="backtest result"):
        _run("quant.edge_report", {})
