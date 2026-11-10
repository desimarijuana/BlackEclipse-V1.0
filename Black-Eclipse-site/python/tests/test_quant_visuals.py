"""The Quant Figure Kit — deterministic figures from stored artifacts.

Every figure is built from an artifact and validates against the chart engine's
own contract. A missing input is a named absence, never a fabricated chart.
"""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant.store import QuantStore
from harness.quant.tools import register_quant_tools
from harness.quant.visuals import (
    FIGURE_CATALOG,
    build_figure,
    build_figures,
    resolve_figures,
)
from harness.tools import ToolContext, ToolRegistry


def _equity(n: int = 120) -> list[dict]:
    return [
        {"index": i, "ts": f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
         "equity": 100_000.0 + i * 100.0 + (500.0 if i % 9 == 0 else 0.0)}
        for i in range(n)
    ]


def _artifact() -> dict:
    return {
        "metadata": {"strategyId": "ema_cross", "symbols": ["TESTUSDT"], "interval": "1d"},
        "configuration": {"interval": "1d", "randomSeed": 42},
        "metrics": {"sharpe": 1.2},
        "equityCurve": _equity(),
        "drawdownCurve": [
            {"index": i, "ts": f"2026-01-{(i % 28) + 1:02d}",
             "drawdown": -float((i % 17)) / 2.0}
            for i in range(120)
        ],
        "exposure": [
            {"index": i, "ts": f"2026-01-{(i % 28) + 1:02d}",
             "grossExposure": 1_000.0 + i * 10.0, "netExposure": 500.0 + i * 5.0}
            for i in range(120)
        ],
        "monthlyReturns": [
            {"month": "2026-01", "return": 2.5, "endEquity": 100_000.0},
            {"month": "2026-02", "return": -1.2, "endEquity": 98_800.0},
            {"month": "2026-03", "return": 3.1, "endEquity": 101_900.0},
        ],
        "trades": [
            {"id": f"t{i}", "netPnl": (-1 if i % 3 == 0 else 1) * (12.0 + i),
             "barsHeld": 2 + i % 7}
            for i in range(30)
        ],
        "fills": [
            {"commission": 1.5, "slippage": 0.5, "spreadCost": 0.25, "impact": 0.1},
            {"commission": 1.5, "slippage": 0.5, "spreadCost": 0.25, "impact": 0.1},
        ],
        "warnings": [],
    }


def _assert_valid(entry) -> None:
    from harness.charts.spec import ChartSpec

    assert entry.available, (entry.name, entry.reason)
    parsed = ChartSpec.model_validate(entry.spec)
    assert parsed.to_dict()["kind"] == entry.spec["kind"]


def test_presets_expand_and_unknown_names_are_ignored() -> None:
    names = resolve_figures(["core", "nope", "equity"])
    assert names[:4] == ["equity", "underwater", "monthly_returns", "trade_distribution"]
    assert names.count("equity") == 1
    assert set(FIGURE_CATALOG) >= set(names)


@pytest.mark.parametrize(
    "name",
    ["equity", "underwater", "monthly_returns", "exposure", "trade_distribution",
     "trade_scatter", "rolling_risk", "cost_waterfall"],
)
def test_core_and_risk_figures_are_valid(name: str) -> None:
    _assert_valid(build_figure(name, _artifact()))


def test_equity_is_sampled_and_says_so() -> None:
    artifact = _artifact()
    artifact["equityCurve"] = _equity(6000)
    entry = build_figure("equity", artifact)
    assert entry.available
    assert entry.spec
    assert entry.spec["footnote"]
    assert "sampled out" in entry.spec["footnote"]
    _assert_valid(entry)


def test_missing_input_is_named_not_drawn() -> None:
    entry = build_figure("equity", {"metadata": {}})
    assert not entry.available
    assert entry.spec is None
    assert "equity curve" in entry.reason


def test_frictionless_run_has_no_cost_figure() -> None:
    artifact = _artifact()
    artifact["fills"] = [{"commission": 0, "slippage": 0, "spreadCost": 0, "impact": 0}]
    entry = build_figure("cost_waterfall", artifact)
    assert not entry.available
    assert "frictionless" in entry.reason


def test_monte_carlo_figure_uses_the_artifact_numbers() -> None:
    artifact = {
        "returnPercentiles": {"p5": -8.0, "p25": -2.0, "p50": 1.5, "p75": 4.0, "p95": 9.0},
        "returnDistribution": {"bins": [-10, -5, 0, 5, 10], "counts": [2, 10, 30, 8]},
        "method": "trade_reshuffle", "successful": 50,
    }
    entry = build_figure("montecarlo", artifact)
    _assert_valid(entry)
    assert entry.spec["kind"] == "scene"
    assert len(entry.spec["panels"]) == 2


def test_regime_attribution_requires_attribution() -> None:
    entry = build_figure("regime_attribution", _artifact())
    assert not entry.available
    artifact = {"regimeAttribution": {"regimes": {"up|normal": {"netPnl": 120.0},
                                                  "down|high": {"netPnl": -40.0}}}}
    _assert_valid(build_figure("regime_attribution", artifact))


def test_parameter_surface_is_3d_only_when_the_grid_is_complete() -> None:
    complete = {
        "objective": "sharpe",
        "trials": [
            {"params": {"fast": f, "slow": s}, "score": (f + s) / 10.0}
            for f in (5, 10) for s in (20, 30)
        ],
    }
    entry = build_figure("parameter_surface", complete)
    _assert_valid(entry)
    mark = entry.spec["panels"][0]["marks"][0]
    assert mark["type"] == "surface"
    assert mark["matrix"]

    incomplete = {
        "objective": "sharpe",
        "trials": [
            {"params": {"fast": 5, "slow": 20}, "score": 1.0},
            {"params": {"fast": 10, "slow": 30}, "score": 2.0},
            {"params": {"fast": 5, "slow": 40}, "score": 3.0},
            {"params": {"fast": 15, "slow": 20}, "score": 0.5},
        ],
    }
    entry = build_figure("parameter_surface", incomplete)
    _assert_valid(entry)
    assert entry.spec["panels"][0]["marks"][0]["type"] == "scatter3d"
    assert "point cloud" in entry.spec["subtitle"]


def test_parameter_surface_needs_two_varying_parameters() -> None:
    artifact = {
        "objective": "sharpe",
        "trials": [{"params": {"fast": 5}, "score": 1.0} for _ in range(5)],
    }
    entry = build_figure("parameter_surface", artifact)
    assert not entry.available
    assert "two numeric parameters" in entry.reason


def test_walk_forward_figure() -> None:
    artifact = {
        "objective": "sharpe",
        "windows": [
            {"inSample": {"sharpe": 1.4}, "outOfSample": {"sharpe": 0.9}},
            {"inSample": {"sharpe": 1.1}, "outOfSample": {"sharpe": 0.4}},
        ],
        "combinedEquity": [{"index": i, "ts": str(i), "equity": 100 + i} for i in range(20)],
        "divergence": {"ratio": 0.52},
    }
    entry = build_figure("walkforward", artifact)
    _assert_valid(entry)
    assert entry.spec["kind"] == "scene"
    assert "0.52" in (entry.spec["footnote"] or "")


def test_build_figures_returns_an_entry_per_requested_name() -> None:
    entries = build_figures(_artifact(), figures=["core", "nope"])
    assert [entry.name for entry in entries] == [
        "equity", "underwater", "monthly_returns", "trade_distribution",
    ]
    assert all(entry.available for entry in entries)


class _Result:
    status = "OK"
    configuration = {"interval": "1d", "randomSeed": 42}
    metadata = {"strategyId": "ema_cross", "symbols": ["TESTUSDT"], "interval": "1d"}
    metrics = {"sharpe": 1.2}
    warnings: list = []
    observability = {"durationMs": 1}

    def __init__(self, artifact: dict) -> None:
        self.artifact = artifact

    def to_dict(self, include_series: bool = True) -> dict:
        return self.artifact


def test_figure_routes_serve_the_computed_spec(tmp_path, monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import harness.routers.quant as quant_router
    from harness.deps import require_operator
    from harness.routers.quant_reports import router as reports_router

    store = QuantStore(AgentMemoryStore(str(tmp_path / "am.db")),
                       artifact_root=str(tmp_path / "art"))
    experiment_id = store.save_experiment(
        _Result(_artifact()), strategy_id="ema_cross", strategy_version="1.0.0",
        kind="backtest",
    )
    monkeypatch.setattr(quant_router.service, "quant_store", store, raising=False)

    app = FastAPI()
    app.include_router(reports_router)
    app.dependency_overrides[require_operator] = lambda: True
    client = TestClient(app)

    listed = client.get(f"/quant/experiments/{experiment_id}/figures?figures=core")
    assert listed.status_code == 200, listed.text
    names = [figure["name"] for figure in listed.json()["figures"]]
    assert names == ["equity", "underwater", "monthly_returns", "trade_distribution"]

    one = client.get(f"/quant/experiments/{experiment_id}/figures/equity")
    assert one.status_code == 200, one.text
    figure = one.json()["figure"]
    assert figure["available"] is True
    assert figure["spec"]["kind"] == "area"
    assert figure["spec"]["series"][0]["data"]

    missing = client.get(f"/quant/experiments/{experiment_id}/figures/regime_attribution")
    assert missing.status_code == 200
    assert missing.json()["figure"]["available"] is False
    assert "regime" in missing.json()["figure"]["reason"]


@pytest.mark.asyncio
async def test_render_quant_figures_tool_returns_compact_blocks(tmp_path) -> None:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = QuantStore(ams, artifact_root=str(tmp_path / "art"))
    experiment_id = store.save_experiment(
        _Result(_artifact()), strategy_id="ema_cross", strategy_version="1.0.0",
        kind="backtest",
    )
    registry = ToolRegistry()
    register_quant_tools(registry)
    ctx = ToolContext(run_id="t", log=lambda *a, **k: None, quant_store=store)

    result = await registry.execute(
        "render_quant_figures", "c_figures",
        {"experimentId": experiment_id, "figures": ["core"]}, ctx,
    )
    assert result.ok, result.text
    data = result.data
    assert len(data["blocks"]) == 4
    assert all(block["quant"]["experimentId"] == experiment_id for block in data["blocks"])
    assert all("series" not in block for block in data["blocks"])
    # The blocks are tiny and they are also in the TEXT, because the model
    # reads the text (not `data`) and must be able to copy them.
    assert '"quant"' in result.text
    assert len(str(data["blocks"])) < 2_000
