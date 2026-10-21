"""Tests for the Edge Report — the document that binds the verdict, the
evidence and the figures together."""

from __future__ import annotations

import pytest

from harness.quant.edge_report import MAX_POINTS, EdgeReportError, build_edge_report


def _artifact(n=180, trades=120):
    return {
        "metadata": {
            "strategyId": "ema_cross", "strategyVersion": "1.0.0",
            "symbols": ["TESTUSDT"], "interval": "1d", "engineVersion": "1",
        },
        "configuration": {
            "start": "2024-01-01", "end": "2024-06-01",
            "initialCapital": 100_000, "randomSeed": 42,
        },
        "metrics": {
            "total_return": 42.0, "cagr": 22.0, "volatility": 18.0, "sharpe": 1.8,
            "sortino": 2.2, "calmar": 1.4, "max_drawdown": -12.0, "ulcer_index": 4.0,
            "var_95": -1.2, "cvar_95": -2.0, "profit_factor": 1.9, "expectancy": 220.0,
            "win_rate": 55.0, "trade_count": trades,
        },
        "trades": [{"id": f"t{i}", "symbol": "TESTUSDT", "netPnl": 220.0,
                    "entryTs": "2024-01-01T00:00:00Z"} for i in range(trades)],
        "equityCurve": [{"index": i, "ts": f"2024-01-{(i % 28) + 1:02d}T00:00:00Z",
                         "equity": 100_000 + i * 300 + (i % 7) * 40} for i in range(n)],
        "drawdownCurve": [{"index": i, "ts": "x", "drawdown": -abs(i % 11) * 0.7}
                          for i in range(n)],
    }


def _monte_carlo():
    return {
        "method": "regime_block_bootstrap",
        "returnPercentiles": {"p5": 4.0, "p25": 12.0, "p50": 22.0, "p75": 33.0,
                               "p95": 55.0},
        "probabilityOfLoss": 8.0, "probabilityOfRuin": 0.0, "successful": 500,
        "returnDistribution": {"bins": [0.0, 5.0, 10.0, 15.0],
                                "counts": [12, 120, 250, 118]},
        "regimeAttribution": {"regimes": {
            "up_normal": {"trades": 80, "netPnl": 14_000.0},
            "flat_normal": {"trades": 40, "netPnl": 3_000.0},
        }},
    }


def test_the_report_grades_the_evidence_and_names_its_grade():
    report = build_edge_report(_artifact(), _monte_carlo())
    assert report.verdict["grade"] in ("A", "B", "C", "D", "E", "F")
    assert report.verdict["score"] > 0
    assert "Grade" in report.verdict["summary"]


def test_the_report_draws_one_chart_per_panel_it_has_data_for():
    report = build_edge_report(_artifact(), _monte_carlo())
    names = [c["name"] for c in report.charts]
    assert names == ["equity", "drawdown", "monte-carlo", "distribution", "regimes"]
    for chart in report.charts:
        assert chart["spec"]["kind"]
        assert chart["spec"]["source"].endswith("computed")


def test_a_report_without_a_monte_carlo_says_so_instead_of_scoring_it():
    report = build_edge_report(_artifact(), None)
    names = [c["name"] for c in report.charts]
    assert names == ["equity", "drawdown"]
    codes = {w["code"] for w in report.warnings}
    assert "EDGE_REPORT_WITHOUT_MONTE_CARLO" in codes
    assert "robustness" in report.verdict["assumptions"]["notGradedOn"]


def test_every_chart_spec_is_valid_for_the_chart_engine():
    from harness.charts.spec import ChartSpec

    report = build_edge_report(_artifact(), _monte_carlo())
    for chart in report.charts:
        spec = ChartSpec.model_validate(chart["spec"])
        assert spec.kind
        assert spec.series or spec.values or spec.points or spec.matrix


def test_a_long_series_is_sampled_to_fit_the_chart_engine_and_says_so():
    artifact = _artifact(n=MAX_POINTS + 500)
    report = build_edge_report(artifact, None)
    equity = next(c for c in report.charts if c["name"] == "equity")
    assert len(equity["spec"]["series"][0]["data"]) <= MAX_POINTS
    assert equity["spec"]["footnote"]
    assert "sampled out" in equity["spec"]["footnote"]


def test_the_markdown_report_carries_the_grade_the_numbers_and_the_caveats():
    report = build_edge_report(_artifact(), _monte_carlo())
    markdown = report.markdown
    assert "# Edge Report" in markdown
    assert "## The axes" in markdown
    assert "## Measured" in markdown
    assert "## Under uncertainty" in markdown
    assert "## Where the P&L came from" in markdown
    assert "## What this report does not say" in markdown
    assert "It is not investment advice" in markdown
    assert "ema_cross" in markdown


def test_a_report_without_an_artifact_is_refused():
    with pytest.raises(EdgeReportError):
        build_edge_report({})


def test_the_flags_of_a_bad_strategy_reach_the_report():
    artifact = _artifact(trades=5)
    artifact["metrics"]["profit_factor"] = 0.8
    artifact["metrics"]["expectancy"] = -5.0
    report = build_edge_report(artifact, None)
    codes = {f["code"] for f in report.verdict["flags"]}
    assert "SAMPLE_TOO_SMALL" in codes
    assert "EXPECTANCY_NOT_POSITIVE" in codes
    assert "PROFIT_FACTOR_BELOW_ONE" in codes
    assert report.verdict["grade"] in ("D", "E", "F")


# ── the tool, end to end ─────────────────────────────────────────────────────

@pytest.fixture()
def store(tmp_path):
    from harness.persistence import AgentMemoryStore
    from harness.quant.store import QuantStore

    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return QuantStore(ams, artifact_root=str(tmp_path / "art"))


def _stored_backtest(store):
    from harness.quant.research import ResearchResult

    artifact = _artifact()
    result = ResearchResult(
        kind="backtest", status="OK",
        metadata=artifact["metadata"], configuration=artifact["configuration"],
        metrics=artifact["metrics"],
        payload={"trades": artifact["trades"], "equityCurve": artifact["equityCurve"],
                 "drawdownCurve": artifact["drawdownCurve"]},
    )
    return store.save_experiment(result, strategy_id="ema_cross",
                                 strategy_version="1.0.0", kind="backtest")


async def test_the_tool_grades_a_stored_experiment_and_draws_the_figures(store):
    from types import SimpleNamespace

    from harness.quant.advanced_tools import generate_edge_report

    experiment_id = _stored_backtest(store)
    ctx = SimpleNamespace(quant_store=store, run_id="run_1", artifact_service=None)
    text, data = await generate_edge_report({"experimentId": experiment_id}, ctx)

    assert data["status"] == "OK"
    assert data["verdict"]["grade"] in ("A", "B", "C", "D", "E", "F")
    names = [chart["name"] for chart in data["charts"]]
    assert "equity" in names
    drawn = [chart for chart in data["charts"] if chart.get("figure")]
    assert drawn, "the figures should be drawn"
    assert drawn[0]["figure"]["label"] == "computed"
    assert drawn[0]["figure"]["isEvidence"] is False


async def test_the_tool_refuses_without_an_experiment(store):
    from types import SimpleNamespace

    from harness.quant.advanced_tools import generate_edge_report

    ctx = SimpleNamespace(quant_store=store, run_id="run_1", artifact_service=None)
    text, data = await generate_edge_report({}, ctx)
    assert data["status"] == "ERROR"
    assert data["error"]["code"] == "EDGE_REPORT_INPUT_REQUIRED"
