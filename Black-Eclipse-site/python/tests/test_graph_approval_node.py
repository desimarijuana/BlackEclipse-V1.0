"""Human-approval gate: request, wait, durable deferral and honest failure."""

from __future__ import annotations

import pytest

from harness.graph_runtime import approval_nodes
from harness.graph_runtime.approval_nodes import set_approval_runner
from harness.graph_runtime.model import DeferredWait, ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext

REGISTRY = build_default_registry()


def _exec(config: dict, inputs: dict, *, allow_defer: bool = False, test_run: bool = False,
          should_cancel=None):
    definition = REGISTRY.get("logic.human_approval")
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id="gate", run_id="grun_1", mode=ExecutionMode.RESEARCH,
        inputs=inputs, config=config, allow_defer=allow_defer, test_run=test_run,
        should_cancel=should_cancel or (lambda: False),
    ))


@pytest.fixture()
def approvals():
    state: dict = {"status": "pending", "decisions": [], "args": None}

    def runner(context, args):
        state["args"] = args
        state["decisions"].append(state["status"])
        if state["status"] == "approved":
            return {"status": "approved", "approval": {"id": "appr_1", "decidedBy": "operator"}}
        if state["status"] == "denied":
            return {"status": "denied", "approval": {"id": "appr_1", "decidedBy": "operator"}}
        return {"status": "pending", "approval": {"id": "appr_1", "status": "pending"}}

    set_approval_runner(runner)
    try:
        yield state
    finally:
        set_approval_runner(None)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


def test_approved_gate_passes_the_value_and_names_the_approver(approvals):
    approvals["status"] = "approved"
    result = _exec({"title": "Submit the order?", "risk": "high"}, {"value": {"symbol": "AAPL"}})
    assert result["value"] == {"symbol": "AAPL"}
    assert result["approved"] is True
    assert result["decidedBy"] == "operator"
    assert result["_control"] == ["done"]
    assert approvals["args"]["risk"] == "high"
    assert approvals["args"]["requestKey"] == "graph:grun_1:gate"


def test_denied_gate_fails_the_node_with_the_approver(approvals):
    approvals["status"] = "denied"
    with pytest.raises(ValueError, match="denied by operator"):
        _exec({"title": "Submit?"}, {})


def test_pending_gate_defers_a_durable_run_without_finishing_the_node(approvals):
    with pytest.raises(DeferredWait) as exc:
        _exec({"title": "Submit?", "pollSeconds": 7}, {}, allow_defer=True)
    assert exc.value.rerun is True
    assert exc.value.wake_after_seconds == 7.0
    assert exc.value.outputs == {}


def test_a_synchronous_run_polls_until_the_decision(monkeypatch, approvals):
    clock = _Clock()
    monkeypatch.setattr(approval_nodes, "time", clock)
    approvals["status"] = "pending"

    calls = {"n": 0}

    def runner(context, args):
        calls["n"] += 1
        if calls["n"] >= 3:
            return {"status": "approved", "approval": {"decidedBy": "ops"}}
        return {"status": "pending", "approval": {}}

    set_approval_runner(runner)
    result = _exec({"pollSeconds": 5, "maxWaitS": 60}, {"value": 1})
    assert result["approved"] is True
    assert result["decidedBy"] == "ops"
    assert clock.now == 10.0  # two sleeps of the poll interval


def test_a_synchronous_run_fails_honestly_when_unanswered(monkeypatch, approvals):
    monkeypatch.setattr(approval_nodes, "time", _Clock())
    approvals["status"] = "pending"
    with pytest.raises(ValueError, match="still pending after 10s"):
        _exec({"pollSeconds": 2, "maxWaitS": 10}, {})


def test_a_cancelled_run_stops_waiting(monkeypatch, approvals):
    monkeypatch.setattr(approval_nodes, "time", _Clock())
    approvals["status"] = "pending"
    with pytest.raises(ValueError, match="cancelled while waiting"):
        _exec({"pollSeconds": 2, "maxWaitS": 60}, {}, should_cancel=lambda: True)


def test_a_test_run_never_requests_an_approval(approvals):
    with pytest.raises(ValueError, match="test run never requests one"):
        _exec({}, {}, test_run=True)
    assert approvals["decisions"] == []


def test_the_gate_needs_a_bound_approval_store():
    set_approval_runner(None)
    with pytest.raises(ValueError, match="approval store"):
        _exec({}, {})


def test_request_arguments_are_bounded_and_validated(approvals):
    with pytest.raises(ValueError, match="unsupported risk"):
        _exec({"risk": "nope"}, {})


def test_the_digest_is_stable_for_a_run_and_node_and_changes_otherwise(approvals):
    approvals["status"] = "approved"
    _exec({"title": "T", "message": "M"}, {})
    first = approvals["args"]["digest"]
    _exec({"title": "T", "message": "M"}, {})
    assert approvals["args"]["digest"] == first

    other = NodeExecContext(
        node_id="gate", run_id="grun_2", mode=ExecutionMode.RESEARCH, inputs={}, config={},
    )
    assert approval_nodes._digest(other, "T", "M") != first
