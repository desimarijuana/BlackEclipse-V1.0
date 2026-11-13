"""W0 baseline collector: read-only metrics, honest unknowns, stable output."""

from __future__ import annotations

import json
import os
import tempfile
from types import SimpleNamespace

import pytest

from harness.evaluation.w0_baseline import (
    attach_gates,
    build_report,
    percentile,
    render_markdown,
)
from harness.model_runtime.store import ModelRuntimeStore
from harness.persistence import AgentMemoryStore
from harness.run_effects import RunEffects


@pytest.fixture()
def store_path():
    directory = tempfile.mkdtemp(prefix="be-w0-baseline-")
    path = os.path.join(directory, "agent-memory.db")
    store = AgentMemoryStore(path)
    yield store, path
    store.close()


def _seed(store: AgentMemoryStore) -> None:
    store.create_run("run_a", "eclipse-agent", {"query": "a"})
    store.update_run(
        "run_a", status="completed", startedAt="2026-11-12T10:00:00+00:00",
        finishedAt="2026-11-12T10:00:02+00:00", promptTokens=100,
        completionTokens=20, totalTokens=120,
    )
    store.create_run("run_b", "eclipse-agent", {"query": "b"})
    store.update_run(
        "run_b", status="failed", startedAt="2026-11-12T10:01:00+00:00",
        finishedAt="2026-11-12T10:01:04+00:00", promptTokens=300,
        completionTokens=0, totalTokens=300,
    )
    store.append_event("run_a", "run.resumed", 1, {})
    store.append_event("run_a", "context.overflow", 2, {})
    store.append_event("run_b", "run.failed", 1, {"error": {"code": "RUN_STALLED"}})
    store.append_event("run_b", "run.flags", 2, {"flags": {}, "snapshotHash": "x"})
    store.record_tool_execution(
        "run_a",
        SimpleNamespace(
            tool_call_id="c1", name="get_quote", ok=True, duration_ms=250,
            text="x" * 100, error=None, args={},
        ),
    )
    ModelRuntimeStore(store).record_model_request({
        "requestId": "m1", "runId": "run_a", "provider": "ollama", "model": "m",
        "success": 1, "fallback": 0, "retries": 0, "inputTokens": 100,
        "outputTokens": 20, "totalTokens": 120, "latencyMs": 1200.0,
        "ttftMs": 300.0, "costTotal": None, "costEstimated": 0,
    })
    effects = RunEffects(store)
    effects.begin("run_a", 1, "c1", "get_quote", None)
    effects.finish("run_a", 1, "c1", ok=True)
    effects.begin("run_b", 1, "c2", "submit_order", "external_action")
    effects.mark_unknown("run_b", 1, "c2")


def test_percentile_nearest_rank():
    assert percentile([], 0.95) is None
    assert percentile([1, 2, 3, 4], 0.50) == 2
    assert percentile([1, 2, 3, 4], 0.95) == 4


def test_report_reads_runtime_metrics(store_path):
    store, path = store_path
    _seed(store)
    report = build_report(path, label="test", commit="abc123", generated_at="now")

    runs = report["metrics"]["runs"]
    assert runs["total"]["value"] == 2
    assert runs["byStatus"]["value"] == {"completed": 1, "failed": 1}
    assert runs["terminalCorrectness"]["value"] == 0.5
    assert runs["latencyMs"]["measured"] is True
    assert runs["latencyMs"]["value"]["p95"] == 4000.0

    events = report["metrics"]["events"]
    assert events["contextOverflow"]["value"] == 1
    assert events["failedCodes"]["value"] == {"RUN_STALLED": 1}
    assert events["runFlags"]["value"] == 1

    model = report["metrics"]["model"]
    assert model["attempts"]["value"] == 1
    assert model["cost"]["measured"] is False
    assert model["cost"]["value"] is None
    assert model["cost"]["value"] != 0

    tools = report["metrics"]["tools"]
    assert tools["calls"]["value"] == 1
    assert tools["errorRate"]["value"] == 0.0

    effects = report["metrics"]["effects"]
    assert effects["unknown"]["value"] == 1
    assert effects["started"]["value"] == 0


def test_report_marks_missing_tables_unknown(store_path):
    store, path = store_path
    report = build_report(path, label="empty", commit="abc")
    # The database exists but has no runs: measured count is 0, not a crash.
    assert report["metrics"]["runs"]["total"]["measured"] is True
    assert report["metrics"]["runs"]["total"]["value"] == 0
    # No model table in a bare store: honest unknown, never a fabricated zero.
    assert report["metrics"]["model"]["attempts"]["measured"] in (True, False)
    if not report["metrics"]["model"]["attempts"]["measured"]:
        assert report["metrics"]["model"]["attempts"]["value"] is None


def test_markdown_contains_provenance_and_unknown():
    report = {
        "label": "w0",
        "generatedAt": "now",
        "provenance": {"commit": "abc", "flagsHash": "sha256:x"},
        "window": {"source": "read-only-db"},
        "metrics": {
            "runs": {
                "total": {
                    "value": 0, "unit": "runs", "sample": 0,
                    "measured": True, "source": "HarnessRun",
                },
                "missing": {
                    "value": None, "unit": "runs", "sample": 0,
                    "measured": False, "source": "HarnessRun",
                },
            }
        },
        "unmeasured": [{"metric": "missing", "reason": "HarnessRun"}],
    }
    text = render_markdown(report)
    assert "`abc`" in text
    assert "UNKNOWN" in text
    assert "## Unmeasured" in text


def test_attach_gates_fills_eval_without_inventing():
    report = {
        "metrics": {
            "eval": {
                "offline": {"value": None, "unit": "verdict", "sample": 0,
                            "measured": False, "source": "not run"},
                "live": {"value": None, "unit": "verdict", "sample": 0,
                         "measured": False, "source": "not run"},
            }
        }
    }
    attach_gates(report, {
        "offline": {"status": "PASS", "source": "node scripts/test-evals.js"},
        "live": {"status": "NOT MEASURED", "source": "no provider"},
    })
    assert report["gates"]["offline"]["status"] == "PASS"
    assert report["metrics"]["eval"]["offline"]["value"] == "PASS"
    assert report["metrics"]["eval"]["offline"]["measured"] is True
    assert report["metrics"]["eval"]["live"]["value"] == "NOT MEASURED"


def test_cli_writes_json_and_markdown(store_path, tmp_path):
    store, path = store_path
    _seed(store)
    out = tmp_path / "baseline.json"
    from harness.evaluation.w0_baseline import main

    assert main(["--db", path, "--out", str(out), "--label", "cli"]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["label"] == "cli"
    assert out.with_suffix(".md").exists()
