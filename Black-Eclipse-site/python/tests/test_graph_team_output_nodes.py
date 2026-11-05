"""Committee, output and evidence-ranking nodes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from harness.graph_runtime import research_nodes
from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.output_nodes import set_notify_runner
from harness.graph_runtime.registry import NodeExecContext
from harness.graph_runtime.team_nodes import set_team_runner

REGISTRY = build_default_registry()


def _exec(node_type: str, config: dict, inputs: dict, *, test_run: bool = False):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.RESEARCH,
        inputs=inputs, config=config, test_run=test_run,
    ))


# ── agent.team ───────────────────────────────────────────────────────────────

def _team_result(status="COMPLETED", **overrides):
    payload = {
        "status": status,
        "teamRunId": "team_1",
        "decision": {"reviewOutcome": "APPROVED", "conflicts": []},
        "synthesis": "Buy-side case is stronger on margins.",
        "error": None,
    }
    payload.update(overrides)
    return payload


def test_team_returns_decision_and_synthesis():
    captured = {}

    def runner(context, args):
        captured.update(args)
        return _team_result()

    set_team_runner(runner)
    try:
        result = _exec("agent.team", {"universe": "AAPL", "horizon": "3m", "timeoutS": 120},
                       {"objective": "Is AAPL a buy?"})
    finally:
        set_team_runner(None)
    assert result["status"] == "COMPLETED"
    assert result["synthesis"].startswith("Buy-side")
    assert result["decision"]["reviewOutcome"] == "APPROVED"
    assert captured == {"objective": "Is AAPL a buy?", "universe": "AAPL", "horizon": "3m", "timeoutS": 120}


def test_team_accepts_partial_and_fails_other_statuses():
    set_team_runner(lambda _c, _a: _team_result("PARTIAL"))
    try:
        assert _exec("agent.team", {}, {"objective": "x"})["status"] == "PARTIAL"
    finally:
        set_team_runner(None)

    set_team_runner(lambda _c, _a: _team_result("FAILED", error="committee could not agree"))
    try:
        with pytest.raises(ValueError, match="committee could not agree"):
            _exec("agent.team", {}, {"objective": "x"})
    finally:
        set_team_runner(None)


def test_team_refuses_a_test_run_and_requires_objective_and_runtime():
    set_team_runner(lambda _c, _a: _team_result())
    try:
        with pytest.raises(ValueError, match="test run"):
            _exec("agent.team", {}, {"objective": "x"}, test_run=True)
        with pytest.raises(ValueError, match="needs an objective"):
            _exec("agent.team", {}, {})
    finally:
        set_team_runner(None)
    set_team_runner(None)
    with pytest.raises(ValueError, match="team runtime"):
        _exec("agent.team", {}, {"objective": "x"})


# ── output.chart ─────────────────────────────────────────────────────────────

def test_chart_builds_a_spec_from_a_number_list():
    result = _exec("output.chart", {"kind": "bar", "title": "Revenue"}, {"series": [1, 2, 3]})
    assert result["spec"]["kind"] == "bar"
    assert result["spec"]["title"] == "Revenue"
    assert result["spec"]["categories"] == ["0", "1", "2"]
    assert result["spec"]["series"][0]["data"] == [1.0, 2.0, 3.0]
    assert result["rendered"] == (result["figure"] is not None)


def test_chart_accepts_values_and_rows_payloads():
    from_values = _exec("output.chart", {}, {"series": {"values": [2, 4], "categories": ["a", "b"]}})
    assert from_values["spec"]["categories"] == ["a", "b"]

    rows = [{"month": "Jan", "rev": 10}, {"month": "Feb", "rev": 12}, {"month": "Mar", "rev": None}]
    from_rows = _exec("output.chart", {"xField": "month", "yField": "rev"}, {"series": {"rows": rows}})
    assert from_rows["spec"]["categories"] == ["Jan", "Feb", "Mar"]
    assert from_rows["spec"]["series"][0]["data"] == [10.0, 12.0, None]


def test_chart_passes_a_full_spec_through():
    spec = {"kind": "line", "title": "P", "categories": ["a"], "series": [{"name": "S", "data": [1]}]}
    result = _exec("output.chart", {}, {"series": spec})
    assert result["spec"]["title"] == "P"


def test_chart_names_bad_payloads_and_configs():
    with pytest.raises(ValueError, match="needs a payload"):
        _exec("output.chart", {}, {})
    with pytest.raises(ValueError, match="X field and Y field"):
        _exec("output.chart", {}, {"series": {"rows": [{"a": 1}]}})
    with pytest.raises(ValueError, match="not a number"):
        _exec("output.chart", {}, {"series": {"values": ["x"]}})
    with pytest.raises(ValueError, match="unsupported chart kind"):
        _exec("output.chart", {"kind": "candlestick"}, {"series": [1]})
    with pytest.raises(ValueError, match="invalid chart spec"):
        _exec("output.chart", {}, {"series": {"kind": "line", "series": "nope"}})


# ── output.notify ────────────────────────────────────────────────────────────

def test_notify_sends_through_the_runner():
    captured = {}

    def runner(context, args):
        captured.update(args)
        return {"ok": True, "messageId": "m1"}

    set_notify_runner(runner)
    try:
        result = _exec("output.notify", {"channel": "telegram", "destination": "-100", "title": "Daily"},
                       {"message": "AAPL up 2%", "data": {"symbol": "AAPL"}})
    finally:
        set_notify_runner(None)
    assert result["delivered"] is True
    assert captured["channel"] == "telegram"
    assert captured["destination"] == "-100"
    assert captured["message"].startswith("Daily")
    assert "AAPL up 2%" in captured["message"]
    assert '"symbol": "AAPL"' in captured["message"]


def test_notify_failure_fails_the_node_with_the_reason():
    set_notify_runner(lambda _c, _a: {"ok": False, "reason": "chat not linked"})
    try:
        with pytest.raises(ValueError, match="chat not linked"):
            _exec("output.notify", {"channel": "slack", "destination": "C1"}, {"message": "hi"})
    finally:
        set_notify_runner(None)


def test_notify_refuses_a_test_run_and_requires_configuration():
    set_notify_runner(lambda _c, _a: {"ok": True})
    try:
        with pytest.raises(ValueError, match="operator run"):
            _exec("output.notify", {"channel": "slack", "destination": "C1"}, {"message": "hi"}, test_run=True)
        with pytest.raises(ValueError, match="needs a channel"):
            _exec("output.notify", {}, {"message": "hi"})
        with pytest.raises(ValueError, match="needs a destination"):
            _exec("output.notify", {"channel": "slack"}, {"message": "hi"})
        with pytest.raises(ValueError, match="needs a message"):
            _exec("output.notify", {"channel": "slack", "destination": "C1"}, {})
    finally:
        set_notify_runner(None)


# ── research.source_rank ─────────────────────────────────────────────────────

def test_source_rank_orders_by_confidence_and_freshness(monkeypatch):
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(research_nodes, "_now", lambda: now)
    items = [
        {"evidenceId": "old", "confidence": 0.9, "publishedAt": (now - timedelta(days=120)).isoformat()},
        {"evidenceId": "fresh", "confidence": 0.5, "publishedAt": (now - timedelta(days=1)).isoformat()},
        {"evidenceId": "none"},
    ]
    result = _exec("research.source_rank", {"halfLifeDays": 30}, {"evidence": items})
    assert [item["evidenceId"] for item in result["evidence"]] == ["fresh", "old", "none"]
    assert result["summary"] == {"count": 3, "scored": 2, "insufficient": 1, "halfLifeDays": 30}
    ranks = {entry["index"]: entry for entry in result["ranking"]}
    assert ranks[2]["score"] is None
    assert ranks[2]["rank"] == 3
    assert "no confidence or date recorded" in ranks[2]["reasons"]
    assert ranks[1]["freshness"] > ranks[0]["freshness"]


def test_source_rank_accepts_an_evidence_wrapper_and_requires_items(monkeypatch):
    monkeypatch.setattr(research_nodes, "_now", lambda: datetime(2026, 11, 1, tzinfo=timezone.utc))
    result = _exec("research.source_rank", {}, {"evidence": {"evidence": [{"confidence": 1.0}]}})
    assert result["summary"]["count"] == 1
    with pytest.raises(ValueError, match="needs evidence items"):
        _exec("research.source_rank", {}, {"evidence": []})


def test_source_rank_rejects_a_bad_half_life(monkeypatch):
    monkeypatch.setattr(research_nodes, "_now", lambda: datetime(2026, 11, 1, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="Half-life"):
        _exec("research.source_rank", {"halfLifeDays": "soon"}, {"evidence": [{"confidence": 1}]})
