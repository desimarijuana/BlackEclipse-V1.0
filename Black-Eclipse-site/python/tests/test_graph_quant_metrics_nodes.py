"""Graph runtime — pure risk/return metric nodes.

These nodes must be deterministic and must not dress an undefined ratio up as a
zero. Each expected value below is hand-computable from the input series.
"""

from __future__ import annotations

import math

import pytest

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.executor import GraphExecutor
from harness.graph_runtime.model import ExecutionMode, RunStatus, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext

REGISTRY = build_default_registry()


def _ctx(*, inputs=None, config=None):
    return NodeExecContext(
        node_id="q1",
        run_id="run1",
        mode=ExecutionMode.RESEARCH,
        inputs=inputs or {},
        config=config or {},
    )


def _exec(node_type: str, *, inputs=None, config=None):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(_ctx(inputs=inputs, config=config))


def _indicator(values):
    return {"values": values, "kind": "test"}


# ── Registry contract ───────────────────────────────────────────────────────


def test_metric_nodes_are_registered_and_pure():
    for node_type in ("quant.risk_metrics", "quant.drawdown", "quant.correlation", "quant.beta"):
        definition = REGISTRY.get(node_type)
        assert definition is not None, node_type
        assert definition.executor is not None, node_type
        assert definition.capabilities == ("quant.compute",), node_type
        assert definition.side_effects.value == "none", node_type


# ── Risk metrics ────────────────────────────────────────────────────────────


def test_risk_metrics_are_hand_computable():
    returns = [0.10, -0.05, 0.02, 0.03]
    result = _exec(
        "quant.risk_metrics",
        inputs={"values": _indicator(returns)},
        config={"periodsPerYear": 252, "confidence": 0.95, "riskFreeRate": 0},
    )
    metrics = result["metrics"]
    mean = sum(returns) / len(returns)
    stdev = statistics_stdev(returns)
    assert metrics["observations"] == 4
    assert metrics["mean"] == pytest.approx(mean)
    assert metrics["stdev"] == pytest.approx(stdev)
    assert metrics["annualizedVolatility"] == pytest.approx(stdev * math.sqrt(252))
    assert metrics["sharpe"] == pytest.approx(mean / stdev * math.sqrt(252))
    assert metrics["hitRate"] == pytest.approx(0.75)
    assert metrics["best"] == pytest.approx(0.10)
    assert metrics["worst"] == pytest.approx(-0.05)
    # 5% linear-interpolated percentile of [-0.05, 0.02, 0.03, 0.10].
    assert metrics["var"] == pytest.approx(-0.05 * 0.85 + 0.02 * 0.15)
    assert metrics["cvar"] == pytest.approx(-0.05)
    # Equity 1 → 1.10 → 1.045 → 1.0659 → 1.097877.
    assert metrics["maxDrawdown"] == pytest.approx(1.045 / 1.10 - 1.0)


def test_risk_metrics_accepts_prices_and_converts_to_returns():
    result = _exec(
        "quant.risk_metrics",
        inputs={"values": _indicator([100.0, 110.0, 99.0])},
        config={"inputKind": "prices"},
    )
    metrics = result["metrics"]
    assert metrics["observations"] == 2
    assert metrics["best"] == pytest.approx(0.10)
    assert metrics["worst"] == pytest.approx(-0.10)


def test_a_flat_series_has_no_sharpe_rather_than_zero():
    result = _exec("quant.risk_metrics", inputs={"values": _indicator([0.01, 0.01, 0.01])})
    metrics = result["metrics"]
    assert metrics["sharpe"] is None
    assert metrics["sortino"] is None
    assert any("sharpe" in note for note in metrics["notes"])


def test_risk_metrics_requires_enough_points():
    with pytest.raises(ValueError, match="at least two"):
        _exec("quant.risk_metrics", inputs={"values": _indicator([0.01])})


def test_risk_metrics_accepts_ohlcv_bars_directly():
    rows = [{"close": 100.0}, {"close": 110.0}, {"close": 99.0}]
    result = _exec(
        "quant.risk_metrics",
        inputs={"values": {"rows": rows}},
        # The stored preference is ignored: bars are levels, so they are prices.
        config={"inputKind": "returns"},
    )
    metrics = result["metrics"]
    assert metrics["source"] == "ohlcv"
    assert metrics["inputKind"] == "prices"
    assert metrics["observations"] == 2
    assert metrics["best"] == pytest.approx(0.10)
    assert metrics["worst"] == pytest.approx(-0.10)


# ── Drawdown ────────────────────────────────────────────────────────────────


def test_drawdown_from_an_equity_curve():
    result = _exec(
        "quant.drawdown",
        inputs={"values": _indicator([100.0, 120.0, 90.0, 110.0])},
        config={"inputKind": "equity"},
    )
    drawdowns = result["values"]["values"]
    assert drawdowns == pytest.approx([0.0, 0.0, -0.25, 110 / 120 - 1])
    metrics = result["metrics"]
    assert metrics["maxDrawdown"] == pytest.approx(-0.25)
    assert metrics["currentDrawdown"] == pytest.approx(110 / 120 - 1)
    assert metrics["troughIndex"] == 2
    assert metrics["recovered"] is False


def test_drawdown_accepts_ohlcv_bars_directly():
    rows = [{"close": 100.0}, {"close": 120.0}, {"close": 90.0}, {"close": 110.0}]
    result = _exec(
        "quant.drawdown",
        inputs={"values": {"rows": rows}},
        config={"inputKind": "returns"},
    )
    assert result["metrics"]["source"] == "ohlcv"
    assert result["metrics"]["inputKind"] == "equity"
    assert result["metrics"]["maxDrawdown"] == pytest.approx(-0.25)


def test_drawdown_from_returns_builds_the_equity_curve():
    result = _exec(
        "quant.drawdown",
        inputs={"values": _indicator([0.10, -0.20, 0.05])},
        config={"inputKind": "returns"},
    )
    metrics = result["metrics"]
    assert metrics["maxDrawdown"] == pytest.approx(-0.20)
    assert metrics["currentDrawdown"] == pytest.approx(0.924 / 1.10 - 1)


# ── Correlation ─────────────────────────────────────────────────────────────


def test_correlation_of_a_linear_pair_is_one():
    result = _exec(
        "quant.correlation",
        inputs={"a": _indicator([1, 2, 3, 4]), "b": _indicator([2, 4, 6, 8])},
    )
    payload = result["correlation"]
    assert payload["r"] == pytest.approx(1.0)
    assert payload["r2"] == pytest.approx(1.0)
    assert payload["n"] == 4
    assert payload["rolling"] == []


def test_correlation_reports_a_negative_relationship():
    result = _exec(
        "quant.correlation",
        inputs={"a": _indicator([1, 2, 3, 4]), "b": _indicator([4, 3, 2, 1])},
    )
    assert result["correlation"]["r"] == pytest.approx(-1.0)


def test_spearman_uses_ranks_and_a_rolling_window():
    result = _exec(
        "quant.correlation",
        inputs={"a": _indicator([1, 2, 3, 4, 5]), "b": _indicator([2, 4, 6, 8, 10])},
        config={"method": "spearman", "window": 3},
    )
    payload = result["correlation"]
    assert payload["method"] == "spearman"
    assert payload["r"] == pytest.approx(1.0)
    assert payload["rolling"] == pytest.approx([1.0, 1.0, 1.0])


def test_correlation_drops_warmup_nulls_pairwise():
    result = _exec(
        "quant.correlation",
        inputs={"a": _indicator([None, 2, 3, 4]), "b": _indicator([1, 2, 3, 4])},
    )
    assert result["correlation"]["n"] == 3
    assert result["correlation"]["r"] == pytest.approx(1.0)


# ── Beta / alpha ────────────────────────────────────────────────────────────


def test_beta_of_double_exposure_is_two():
    benchmark = [0.01, 0.02, -0.01, 0.03]
    asset = [value * 2 for value in benchmark]
    result = _exec(
        "quant.beta",
        inputs={"asset": _indicator(asset), "benchmark": _indicator(benchmark)},
    )
    payload = result["beta"]
    assert payload["beta"] == pytest.approx(2.0)
    assert payload["alpha"] == pytest.approx(0.0)
    assert payload["correlation"] == pytest.approx(1.0)
    assert payload["n"] == 4


def test_beta_of_a_flat_benchmark_fails_honestly():
    with pytest.raises(ValueError, match="non-zero variance"):
        _exec(
            "quant.beta",
            inputs={
                "asset": _indicator([0.01, 0.02, 0.03]),
                "benchmark": _indicator([0.01, 0.01, 0.01]),
            },
        )


# ── Graph wiring ────────────────────────────────────────────────────────────


def _node(node_id, node_type, config=None):
    return {
        "id": node_id, "type": node_type, "version": "1.0.0",
        "config": config or {}, "layout": {"x": 0, "y": 0},
    }


def _edge(edge_id, source, source_handle, target, target_handle):
    return {
        "id": edge_id, "source": source, "sourceHandle": source_handle,
        "target": target, "targetHandle": target_handle,
    }


def test_risk_metrics_run_inside_a_test_run():
    graph = WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_quant", "name": "Quant",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            _node("trig", "trigger.manual"),
            _node("vals", "data.value", {
                "dataType": "array",
                "value": "[0.01, -0.02, 0.03, 0.01]",
            }),
            _node("risk", "quant.risk_metrics"),
            _node("out", "output.result"),
        ],
        "edges": [
            _edge("e1", "vals", "value", "risk", "values"),
            _edge("e2", "risk", "metrics", "out", "value"),
        ],
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": [],
    })
    plan = compile_workflow(graph, REGISTRY, RunGrants(test_run=True))
    assert plan.executable, [diagnostic.message for diagnostic in plan.diagnostics]
    run = GraphExecutor(graph, plan, REGISTRY, run_id="grun_quant").execute()
    assert run.status == RunStatus.SUCCEEDED
    by_node = {item.node_id: item for item in run.node_runs}
    assert by_node["risk"].outputs["metrics"]["observations"] == 4


def test_history_series_wires_directly_into_risk_metrics():
    """OHLCV -> risk_metrics compiles without an intermediate indicator node."""
    graph = WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_hist", "name": "History risk",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            _node("trig", "trigger.manual"),
            _node("hist", "finance.history", {"symbol": "AAPL", "interval": "1d", "limit": 250}),
            _node("risk", "quant.risk_metrics"),
            _node("out", "output.result"),
        ],
        "edges": [
            _edge("e1", "trig", "start", "hist", "symbol"),
            _edge("e2", "hist", "series", "risk", "values"),
            _edge("e3", "risk", "metrics", "out", "value"),
        ],
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": [],
    })
    plan = compile_workflow(graph, REGISTRY)
    assert plan.executable, [diagnostic.message for diagnostic in plan.diagnostics]


def statistics_stdev(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))
