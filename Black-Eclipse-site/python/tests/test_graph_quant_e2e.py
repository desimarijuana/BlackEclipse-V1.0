"""End-to-end: the quant pack through the real HTTP surface.

The unit suites prove each executor in isolation and the parity suite proves the
two registries agree. Neither proves that a graph the editor can build actually
compiles, authorizes, runs and returns validated payloads through `/graphs/runs`.
This module does: one graph wires the finance read path into every quant node
added in this work, and the run is driven exactly like the app drives it.

The bar provider is a deterministic fixture, installed through the SAME seam the
runtime uses (`finance_nodes.set_series_provider`), so nothing is fabricated and
no network is touched.
"""

from __future__ import annotations

import os
import tempfile
import time

os.environ["AGENT_MEMORY_DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="be-quant-e2e-"), "agent-memory.db",
)
os.environ["HARNESS_ARTIFACT_ROOT"] = os.path.join(
    tempfile.mkdtemp(prefix="be-quant-e2e-files-"), "artifacts",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from harness.graph_runtime import finance_nodes  # noqa: E402
from harness.main import app  # noqa: E402
from harness.quant import fixtures as F  # noqa: E402

client = TestClient(app)

SYMBOL = "TESTUSDT"


@pytest.fixture(scope="module", autouse=True)
def _isolated_graph_service():
    """Same isolation the graph API suite uses (see test_graph_api.py)."""
    import harness.routers.graphs as graphs_router
    from harness.service import AgenticService

    fresh = AgenticService()
    previous = graphs_router.service
    graphs_router.service = fresh
    try:
        yield fresh
    finally:
        graphs_router.service = previous
        try:
            fresh.close()
        except Exception:  # noqa: BLE001 - teardown must not fail the module
            pass


@pytest.fixture(scope="module", autouse=True)
def _fixture_bars():
    def provider(symbol: str, interval: str, limit: int) -> dict:
        count = max(60, min(int(limit or 400), 400))
        return {
            "symbol": symbol,
            "interval": interval,
            "adjusted": True,
            "provider": "fixture",
            "retrievedAt": "2026-01-01T00:00:00Z",
            "rows": F.bull_market(symbol, n=count),
        }

    finance_nodes.set_series_provider(provider)
    try:
        yield
    finally:
        finance_nodes.set_series_provider(None)


def _node(node_id: str, node_type: str, config: dict | None = None) -> dict:
    return {
        "id": node_id, "type": node_type, "version": "1.0.0",
        "config": config or {}, "layout": {"x": 0, "y": 0},
    }


def _edge(edge_id: str, source: str, source_handle: str, target: str, target_handle: str) -> dict:
    return {
        "id": edge_id, "source": source, "sourceHandle": source_handle,
        "target": target, "targetHandle": target_handle,
    }


LEGS = (
    '[{"type": "call", "strike": 490, "quantity": 1, "premium": 12},'
    ' {"type": "call", "strike": 510, "quantity": -1, "premium": 5}]'
)
ORDERS = '[{"side": "buy", "quantity": 100, "price": 100, "symbol": "TESTUSDT"}]'

NODES = [
    _node("trig", "trigger.manual"),
    _node("market", "finance.market_data", {"symbol": SYMBOL, "interval": "1d", "lookback": 400}),
    _node("backtest", "quant.backtest", {"preset": "ema_cross", "fast": 5, "slow": 20, "includeSeries": True}),
    _node("grade", "quant.grade"),
    _node("regime", "quant.regime"),
    _node("resample", "quant.resample", {"targetInterval": "1w"}),
    _node("robustness", "quant.robustness", {
        "preset": "ema_cross", "fast": 5, "slow": 20,
        "paramSpaceJson": '{"indicators.0.params.period": [5, 12]}',
        "costMultipliersJson": "[1, 2]", "splits": 2,
    }),
    _node("benchmark", "quant.benchmark", {"interval": "1d"}),
    _node("trades", "quant.trade_analysis"),
    _node("overfitting", "quant.multiple_testing", {"trialSharpesJson": "[1.5, 1.1, 0.7]"}),
    _node("report", "quant.edge_report"),
    _node("price", "data.value", {"dataType": "number", "value": "190"}),
    _node("stop", "data.value", {"dataType": "number", "value": "5"}),
    _node("size", "quant.position_size", {
        "method": "percent_risk", "value": 1, "equity": 100_000,
    }),
    _node("legs", "data.value", {"dataType": "array", "value": LEGS}),
    _node("options", "quant.options_strategy", {"spotMin": 450, "spotMax": 550}),
    _node("orders", "data.value", {"dataType": "array", "value": ORDERS}),
    _node("costs", "quant.costs", {
        "kind": "transaction",
        "executionJson": '{"commission": {"type": "percentage", "value": 0.1}}',
    }),
    _node("out_grade", "output.result", {"label": "Grade"}),
    _node("out_regime", "output.result", {"label": "Regime"}),
    _node("out_resample", "output.result", {"label": "Resampled"}),
    _node("out_robustness", "output.result", {"label": "Robustness"}),
    _node("out_benchmark", "output.result", {"label": "Benchmark"}),
    _node("out_trades", "output.result", {"label": "Trades"}),
    _node("out_overfitting", "output.result", {"label": "Overfitting"}),
    _node("out_report", "output.result", {"label": "Report"}),
    _node("out_size", "output.result", {"label": "Size"}),
    _node("out_options", "output.result", {"label": "Options"}),
    _node("out_costs", "output.result", {"label": "Costs"}),
]

EDGES = [
    _edge("e1", "trig", "start", "market", "symbol"),
    _edge("e2", "market", "series", "backtest", "series"),
    _edge("e3", "backtest", "metrics", "grade", "metrics"),
    _edge("e4", "backtest", "trades", "grade", "trades"),
    _edge("e5", "backtest", "result", "grade", "result"),
    _edge("e6", "market", "series", "regime", "series"),
    _edge("e7", "market", "series", "resample", "series"),
    _edge("e8", "market", "series", "robustness", "series"),
    _edge("e9", "backtest", "result", "benchmark", "result"),
    _edge("e10", "market", "series", "benchmark", "benchmark"),
    _edge("e11", "backtest", "trades", "trades", "trades"),
    _edge("e12", "market", "series", "trades", "series"),
    _edge("e13", "backtest", "result", "overfitting", "result"),
    _edge("e14", "backtest", "result", "report", "result"),
    _edge("e15", "price", "value", "size", "price"),
    _edge("e16", "stop", "value", "size", "stop"),
    _edge("e17", "legs", "value", "options", "legs"),
    _edge("e18", "orders", "value", "costs", "orders"),
    _edge("e19", "grade", "summary", "out_grade", "value"),
    _edge("e20", "regime", "summary", "out_regime", "value"),
    _edge("e21", "resample", "series", "out_resample", "value"),
    _edge("e22", "robustness", "conclusions", "out_robustness", "value"),
    _edge("e23", "benchmark", "metrics", "out_benchmark", "value"),
    _edge("e24", "trades", "analysis", "out_trades", "value"),
    _edge("e25", "overfitting", "deflated", "out_overfitting", "value"),
    _edge("e26", "report", "report", "out_report", "value"),
    _edge("e27", "size", "size", "out_size", "value"),
    _edge("e28", "options", "analysis", "out_options", "value"),
    _edge("e29", "costs", "costs", "out_costs", "value"),
]

IR = {
    "irVersion": 1,
    "id": "wf_quant_e2e",
    "name": "Quant end-to-end",
    "meta": {"createdAt": "", "updatedAt": "", "tags": []},
    "nodes": NODES,
    "edges": EDGES,
    "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 2, "timeoutMs": 0},
    "requiredCapabilities": [],
}


def _run_to_completion(ir: dict, *, timeout: float = 120.0) -> dict:
    started = client.post("/graphs/runs", json={"ir": ir, "workflowVersion": 1})
    assert started.status_code == 201, started.text
    run_id = started.json()["run"]["id"]
    deadline = time.time() + timeout
    record: dict = {}
    while time.time() < deadline:
        fetched = client.get(f"/graphs/runs/{run_id}")
        assert fetched.status_code == 200, fetched.text
        record = fetched.json()["run"]
        if record["status"] in ("succeeded", "failed", "cancelled"):
            return record
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish in {timeout}s: {record.get('status')}")


def test_the_quant_pack_runs_end_to_end_through_the_graph_api():
    record = _run_to_completion(IR)
    by_node = {node["nodeId"]: node for node in record["nodeRuns"]}

    assert record["status"] == "succeeded", (
        record.get("error"), {k: v.get("error") for k, v in by_node.items() if v["status"] != "succeeded"}
    )
    for node_id in (
        "market", "backtest", "grade", "regime", "resample", "robustness",
        "benchmark", "trades", "overfitting", "report", "size", "options", "costs",
    ):
        assert by_node[node_id]["status"] == "succeeded", (node_id, by_node[node_id].get("error"))

    # Every quant node produced a checkpoint (its validated output), and the
    # preview exists for the UI.
    quant_nodes = (
        "market", "backtest", "grade", "regime", "resample", "robustness",
        "benchmark", "trades", "overfitting", "report", "size", "options", "costs",
    )
    for node_id in quant_nodes:
        checkpoint = by_node[node_id].get("outputs")
        assert checkpoint, node_id

    # Assertions use the SMALL ports on purpose: a checkpoint larger than the
    # preview bound is stored as `{_truncated, preview}` (see executor._preview),
    # so a big object port is checked through the summary/metadata beside it.
    assert by_node["grade"]["outputs"]["summary"].startswith("Grade")
    assert isinstance(by_node["grade"]["outputs"]["flags"], list)

    assert by_node["regime"]["outputs"]["summary"].startswith(SYMBOL)

    metadata = by_node["resample"]["outputs"]["metadata"]
    assert metadata["targetInterval"] == "1w"
    assert metadata["outputBars"] > 0
    assert metadata["sourceInterval"] == "1d"

    assert isinstance(by_node["robustness"]["outputs"]["conclusions"], list)
    assert by_node["benchmark"]["outputs"]["metrics"]["available"] is True
    assert "analysed entries" in by_node["trades"]["outputs"]["summary"]
    assert by_node["overfitting"]["outputs"]["deflated"]["available"] is True
    assert by_node["report"]["outputs"]["verdict"]["grade"] in ("A", "B", "C", "D", "E", "F")
    assert by_node["size"]["outputs"]["quantity"] > 0
    assert by_node["options"]["outputs"]["summary"].startswith("2 leg(s)")
    assert by_node["costs"]["outputs"]["total"] == pytest.approx(10.0)


def test_a_large_quant_output_is_checkpointed_as_a_bounded_preview():
    """A big port is not silently dropped: it is stored with an explicit marker.

    This is the runtime's contract for every node, asserted here for a new one so
    a future change to the quant payloads cannot quietly break run previews.
    """
    record = _run_to_completion(IR)
    by_node = {node["nodeId"]: node for node in record["nodeRuns"]}
    payload = by_node["regime"]["outputs"]["regimes"]
    if isinstance(payload, dict) and payload.get("_truncated"):
        assert isinstance(payload.get("preview"), str) and payload["preview"]
    else:
        # Small enough to keep whole: still the real per-symbol map.
        assert SYMBOL in payload


def test_a_quant_node_failure_is_reported_on_its_node_run():
    broken = {
        **IR,
        "id": "wf_quant_e2e_bad",
        "nodes": [
            _node("trig", "trigger.manual"),
            _node("bad", "quant.grade", {}),
            _node("out", "output.result"),
        ],
        "edges": [
            _edge("e1", "trig", "start", "bad", "metrics"),
            _edge("e2", "bad", "summary", "out", "value"),
        ],
    }
    record = _run_to_completion(broken)
    assert record["status"] == "failed"
    by_node = {node["nodeId"]: node for node in record["nodeRuns"]}
    assert by_node["bad"]["status"] == "failed"
    assert "metrics" in (by_node["bad"].get("error") or "")
