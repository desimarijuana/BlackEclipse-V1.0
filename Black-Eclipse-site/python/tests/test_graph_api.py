"""Graph runtime — HTTP surface (/graphs/*): compile, run, poll, cancel."""

from __future__ import annotations

import os
import tempfile
import time

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-graph-api-"), "agent-memory.db"),
)
os.environ.setdefault(
    "HARNESS_ARTIFACT_ROOT",
    os.path.join(tempfile.mkdtemp(prefix="be-graph-files-"), "artifacts"),
)

from fastapi.testclient import TestClient  # noqa: E402

from harness.main import app  # noqa: E402

client = TestClient(app)


def _node(node_id, node_type, config=None):
    return {"id": node_id, "type": node_type, "version": "1.0.0", "config": config or {}, "layout": {"x": 0, "y": 0}}


def _edge(edge_id, source, source_handle, target, target_handle):
    return {"id": edge_id, "source": source, "sourceHandle": source_handle, "target": target, "targetHandle": target_handle}


def _ir(nodes, edges):
    return {
        "irVersion": 1, "id": "wf_api", "name": "API",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges,
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": [],
    }


GOOD_IR = _ir(
    [
        _node("trig", "trigger.manual", {"seed": "10"}),
        _node("v", "data.value", {"dataType": "number", "value": "0"}),
        _node("f", "transform.formula", {"expression": "x * 5"}),
        _node("out", "output.result"),
    ],
    [
        _edge("e1", "trig", "start", "v", "in"),
        _edge("e2", "v", "value", "f", "x"),
        _edge("e3", "f", "result", "out", "value"),
    ],
)


def test_compile_returns_a_plan():
    response = client.post("/graphs/compile", json={"ir": GOOD_IR})
    assert response.status_code == 200, response.text
    plan = response.json()["plan"]
    assert plan["executable"] is True
    assert plan["workflowId"] == "wf_api"
    assert plan["testRun"] is True
    assert plan["layers"][0] == ["trig"]


def test_compile_reports_diagnostics_for_a_cycle():
    cyclic = _ir(
        [_node("a", "logic.merge"), _node("b", "logic.merge")],
        [_edge("e1", "a", "value", "b", "a"), _edge("e2", "b", "value", "a", "a")],
    )
    response = client.post("/graphs/compile", json={"ir": cyclic})
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["executable"] is False
    assert any(d["code"] == "illegal_cycle" for d in plan["diagnostics"])


def test_run_lifecycle_and_listing():
    started = client.post("/graphs/runs", json={"ir": GOOD_IR, "workflowVersion": 7})
    assert started.status_code == 201, started.text
    run = started.json()["run"]
    run_id = run["id"]

    deadline = time.time() + 10
    record = run
    while time.time() < deadline and record["status"] == "running":
        time.sleep(0.02)
        fetched = client.get(f"/graphs/runs/{run_id}")
        assert fetched.status_code == 200
        record = fetched.json()["run"]
    assert record["status"] == "succeeded", record.get("error")
    assert record["workflowVersion"] == 7
    by_node = {n["nodeId"]: n for n in record["nodeRuns"]}
    assert by_node["f"]["outputs"]["result"] == 50.0
    assert by_node["out"]["inputs"]["value"] == 50.0

    listed = client.get("/graphs/runs", params={"workflowId": "wf_api"})
    assert listed.status_code == 200
    assert any(r["id"] == run_id for r in listed.json()["runs"])

    cancelled = client.post(f"/graphs/runs/{run_id}/cancel")  # already finished → no-op
    assert cancelled.status_code == 200
    assert cancelled.json()["run"]["status"] == "succeeded"


def test_run_refuses_a_broken_graph_with_its_plan():
    broken = _ir([_node("trig", "trigger.manual")], [])
    response = client.post("/graphs/runs", json={"ir": broken})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "graph_not_executable"
    assert any(d["code"] == "missing_terminal" for d in detail["plan"]["diagnostics"])


def test_invalid_ir_is_rejected_before_compilation():
    response = client.post("/graphs/compile", json={"ir": {"irVersion": 1}})
    assert response.status_code == 400
    assert "Invalid workflow IR" in response.json()["detail"]


def test_unknown_run_is_404():
    assert client.get("/graphs/runs/grun_missing").status_code == 404
    assert client.post("/graphs/runs/grun_missing/cancel").status_code == 404


FINANCE_IR = _ir(
    [
        _node("trig", "trigger.manual", {"seed": "AAPL"}),
        _node("mkt", "finance.market_data", {"interval": "1d", "lookback": 5}),
        _node("sma", "finance.indicator", {"kind": "sma", "period": 3}),
        _node("out", "output.result"),
    ],
    [
        _edge("e1", "trig", "start", "mkt", "symbol"),
        _edge("e2", "mkt", "series", "sma", "series"),
        _edge("e3", "sma", "values", "out", "value"),
    ],
)


def test_finance_graph_runs_over_stored_bars():
    """The Phase-5 promise end to end: graph → stored bars → tested math."""
    from harness.graph_runtime import finance_nodes
    from harness.market.series_store import SeriesStore
    from harness.persistence import AgentMemoryStore

    store = AgentMemoryStore(os.environ["AGENT_MEMORY_DB_PATH"])
    try:
        bars = SeriesStore(store)
        bars.save_bars("AAPL", "1d", "test", True, [
            {"timestamp": f"2026-02-0{i+1}T00:00:00Z", "open": float(i + 1), "high": float(i + 2),
             "low": float(i), "close": float(i + 1), "volume": 10.0}
            for i in range(5)
        ])
        # Boot must have bound the runtime's series store to THIS database.
        assert finance_nodes._series_store is not None, "graph boot did not wire the series store"  # noqa: SLF001

        started = client.post("/graphs/runs", json={"ir": FINANCE_IR})
        assert started.status_code == 201, started.text
        run_id = started.json()["run"]["id"]

        deadline = time.time() + 15
        record = started.json()["run"]
        while time.time() < deadline and record["status"] == "running":
            time.sleep(0.05)
            record = client.get(f"/graphs/runs/{run_id}").json()["run"]
        assert record["status"] == "succeeded", record.get("error")

        by_node = {n["nodeId"]: n for n in record["nodeRuns"]}
        assert by_node["mkt"]["outputs"]["provenance"]["rows"] == 5
        assert by_node["mkt"]["outputs"]["provenance"]["asOf"] == "2026-02-05T00:00:00Z"
        # closes 1..5 → SMA(3) = [null, null, 2, 3, 4]
        assert by_node["sma"]["outputs"]["values"]["values"] == [None, None, 2.0, 3.0, 4.0]
    finally:
        store.close()


def test_finance_graph_fails_honestly_without_bars():
    empty = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "ZZZZ"}),
            _node("mkt", "finance.market_data"),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "mkt", "symbol"),
            _edge("e2", "mkt", "provenance", "out", "value"),
        ],
    )
    started = client.post("/graphs/runs", json={"ir": empty})
    assert started.status_code == 201, started.text
    run_id = started.json()["run"]["id"]
    deadline = time.time() + 15
    record = started.json()["run"]
    while time.time() < deadline and record["status"] == "running":
        time.sleep(0.05)
        record = client.get(f"/graphs/runs/{run_id}").json()["run"]
    assert record["status"] == "failed"
    assert "no stored" in (record["error"] or "")
    assert "never fabricates" in (record["error"] or "")
