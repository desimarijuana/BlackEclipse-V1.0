"""Graph runtime — Phase 5 finance/quant nodes: real math from the quant engine,
honest failure when no bars exist, and provenance on every payload."""

from __future__ import annotations

import math

import pytest

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.executor import GraphExecutor
from harness.graph_runtime.finance_nodes import (
    SeriesUnavailable,
    series_rows,
    set_series_provider,
    set_series_store,
)
from harness.graph_runtime.model import RunStatus, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry

REGISTRY = build_default_registry()


def _node(node_id, node_type, config=None):
    return {"id": node_id, "type": node_type, "version": "1.0.0", "config": config or {}, "layout": {"x": 0, "y": 0}}


def _edge(edge_id, source, source_handle, target, target_handle):
    return {"id": edge_id, "source": source, "sourceHandle": source_handle, "target": target, "targetHandle": target_handle}


def _ir(nodes, edges):
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_fin", "name": "Fin",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges,
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": [],
    })


# Six bars with closes 1..6 so SMA(3)/returns are hand-checkable.
BARS = [
    {"timestamp": f"2026-01-0{i+1}T00:00:00Z", "open": float(i + 1), "high": float(i + 2),
     "low": float(i), "close": float(i + 1), "volume": 100.0 + i}
    for i in range(6)
]


@pytest.fixture()
def stub_provider():
    def provider(symbol, interval, limit):
        return {
            "symbol": symbol, "interval": interval, "adjusted": True,
            "provider": "stub", "retrievedAt": "2026-01-02T00:00:00Z",
            "rows": BARS[-limit:],
        }

    set_series_provider(provider)
    try:
        yield provider
    finally:
        set_series_provider(None)


def _run(ir, grants=None):
    plan = compile_workflow(ir, REGISTRY, grants)
    assert plan.executable, [d.message for d in plan.diagnostics]
    return GraphExecutor(ir, plan, REGISTRY, run_id="grun_fin").execute()


def _by_node(run):
    return {r.node_id: r for r in run.node_runs}


def _market_graph(indicator_config=None, extra_nodes=None, extra_edges=None):
    nodes = [
        _node("trig", "trigger.manual", {"seed": "AAPL"}),
        _node("mkt", "finance.market_data", {"lookback": 6}),
        _node("ind", "finance.indicator", indicator_config or {"kind": "sma", "period": 3}),
        _node("out", "output.result"),
    ]
    edges = [
        _edge("e1", "trig", "start", "mkt", "symbol"),
        _edge("e2", "mkt", "series", "ind", "series"),
        _edge("e3", "ind", "values", "out", "value"),
    ]
    return _ir(nodes + (extra_nodes or []), edges + (extra_edges or []))


def test_market_data_without_a_store_fails_honestly():
    # The store binding is PROCESS state (boot wires it), so restore it — a test
    # that leaves it None would silently break every later finance test.
    from harness.graph_runtime import finance_nodes

    saved_store = finance_nodes._series_store  # noqa: SLF001 - deliberate save/restore
    set_series_store(None)
    set_series_provider(None)
    try:
        run = _run(_market_graph())
        node = _by_node(run)["mkt"]
        assert run.status == RunStatus.FAILED
        assert node.status == "failed"
        assert "no market-data store is configured" in (node.error or "")
        # Nothing downstream ran — no fabricated price reached the graph.
        assert _by_node(run)["ind"].status == "skipped"
        assert _by_node(run)["out"].status == "skipped"
    finally:
        set_series_store(saved_store)


def test_market_data_requires_a_symbol():
    run = _run(_ir(
        [_node("trig", "trigger.manual"), _node("mkt", "finance.market_data"), _node("out", "output.result")],
        [_edge("e1", "mkt", "provenance", "out", "value")],
    ))
    node = _by_node(run)["mkt"]
    assert run.status == RunStatus.FAILED
    assert "no symbol" in (node.error or "")


def test_market_data_reads_bars_and_reports_provenance(stub_provider):
    run = _run(_market_graph())
    assert run.status == RunStatus.SUCCEEDED
    market = _by_node(run)["mkt"]
    series = market.outputs["series"]
    assert series["symbol"] == "AAPL"
    assert [row["close"] for row in series["rows"]] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    provenance = market.outputs["provenance"]
    assert provenance["provider"] == "stub"
    assert provenance["rows"] == 6
    assert provenance["asOf"] == "2026-01-06T00:00:00Z"
    assert provenance["retrievedAt"] == "2026-01-02T00:00:00Z"


def test_sma_matches_hand_computed_values(stub_provider):
    run = _run(_market_graph({"kind": "sma", "period": 3}))
    payload = _by_node(run)["ind"].outputs["values"]
    # closes 1..6 → SMA(3) = [null, null, 2, 3, 4, 5]
    assert payload["values"] == [None, None, 2.0, 3.0, 4.0, 5.0]
    assert payload["warmup"] == 2
    assert payload["last"] == 5.0
    assert payload["length"] == 6


def test_bollinger_bands_and_macd_are_consistent(stub_provider):
    bands = _run(_market_graph({"kind": "bollinger", "period": 3}))
    outputs = _by_node(bands)["ind"].outputs["values"]["outputs"]
    middle = outputs["bollinger_middle"]
    upper = outputs["bollinger_upper"]
    lower = outputs["bollinger_lower"]
    # Window [1,2,3]: mean 2, population std 0.816..., band ±2σ.
    expected_std = math.sqrt(((1 - 2) ** 2 + (2 - 2) ** 2 + (3 - 2) ** 2) / 3)
    assert middle[2] == pytest.approx(2.0)
    assert upper[2] == pytest.approx(2.0 + 2 * expected_std)
    assert lower[2] == pytest.approx(2.0 - 2 * expected_std)

    macd = _run(_market_graph({"kind": "macd"}))
    macd_out = _by_node(macd)["ind"].outputs["values"]["outputs"]
    assert {"macd", "macd_signal", "macd_hist"}.issubset(macd_out)
    line, signal, hist = macd_out["macd"], macd_out["macd_signal"], macd_out["macd_hist"]
    for index, value in enumerate(hist):
        if value is None:
            continue
        assert value == pytest.approx(line[index] - signal[index])


def test_returns_zscore_and_volatility(stub_provider):
    graph = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "AAPL"}),
            _node("mkt", "finance.market_data", {"lookback": 6}),
            _node("ret", "quant.returns", {"kind": "simple", "period": 1}),
            _node("z", "quant.zscore", {"period": 3}),
            _node("vol", "quant.volatility", {"period": 3}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "mkt", "symbol"),
            _edge("e2", "mkt", "series", "ret", "values"),
            _edge("e3", "ret", "values", "z", "values"),
            _edge("e4", "z", "values", "vol", "values"),
            _edge("e5", "vol", "values", "out", "value"),
        ],
    )
    # `quant.returns` consumes the BAR PAYLOAD's primary series? No — it takes an
    # INDICATOR payload, so feed it from the indicator node in real graphs. Here
    # the market series (OHLCV) is not an indicator, so the compile must reject
    # that edge instead of silently accepting it.
    plan = compile_workflow(graph, REGISTRY)
    assert plan.executable is False
    assert "incompatible_ports" in [d.code for d in plan.diagnostics]


def test_returns_math_from_an_indicator_series(stub_provider):
    graph = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "AAPL"}),
            _node("mkt", "finance.market_data", {"lookback": 6}),
            _node("sma", "finance.indicator", {"kind": "sma", "period": 1}),
            _node("ret", "quant.returns", {"kind": "simple", "period": 1}),
            _node("z", "quant.zscore", {"period": 2}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "mkt", "symbol"),
            _edge("e2", "mkt", "series", "sma", "series"),
            _edge("e3", "sma", "values", "ret", "values"),
            _edge("e4", "ret", "values", "z", "values"),
            _edge("e5", "z", "values", "out", "value"),
        ],
    )
    run = _run(graph)
    assert run.status == RunStatus.SUCCEEDED
    returns = _by_node(run)["ret"].outputs["values"]["values"]
    # SMA(1) = the closes; simple returns of 1..6 = null, 1.0, 0.5, 1/3, 0.25, 0.2
    assert returns[0] is None
    assert returns[1] == pytest.approx(1.0)
    assert returns[2] == pytest.approx(0.5)
    assert returns[3] == pytest.approx(1 / 3)
    assert returns[4] == pytest.approx(0.25)
    assert returns[5] == pytest.approx(0.2)


def test_indicator_rejects_a_broken_series(stub_provider):
    run = _run(_ir(
        [
            _node("trig", "trigger.manual"),
            _node("v", "data.value", {"dataType": "array", "value": '[{"close": 1}, {"close": 2}]'}),
            _node("ind", "finance.indicator", {"kind": "sma", "period": 2}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "v", "value", "ind", "series"),
            _edge("e2", "ind", "values", "out", "value"),
        ],
    ))
    node = _by_node(run)["ind"]
    assert run.status == RunStatus.FAILED
    assert "missing open" in (node.error or "") or "missing" in (node.error or "")


def test_lookback_is_bounded_by_the_config_schema():
    graph = _market_graph(extra_nodes=[_node("mkt2", "finance.market_data", {"lookback": 999_999})])
    plan = compile_workflow(graph, REGISTRY)
    assert "invalid_config" in [d.code for d in plan.diagnostics]


def test_test_run_grants_read_only_capabilities():
    graph = _market_graph()
    plan = compile_workflow(graph, REGISTRY, RunGrants(test_run=True))
    # market.read + quant.compute are implicitly granted to a test run…
    assert plan.executable is True
    assert "capability_denied" not in [d.code for d in plan.diagnostics]
    # …but an effectful node still is not.
    effectful = _ir(
        [_node("trig", "trigger.manual"), _node("http", "integration.http")],
        [],
    )
    denied = compile_workflow(effectful, REGISTRY, RunGrants(test_run=True))
    assert "permission_denied" in [d.code for d in denied.diagnostics]


def test_series_rows_accepts_both_payload_shapes():
    assert len(series_rows(BARS)) == 6
    assert len(series_rows({"rows": BARS})) == 6
    with pytest.raises(ValueError):
        series_rows({"rows": []})
