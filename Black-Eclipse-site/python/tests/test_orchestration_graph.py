"""Orchestration graph validation, analysis and the state machine."""

from __future__ import annotations

import pytest

from harness.orchestration.graph import (
    GraphValidationError,
    Readiness,
    can_add_edge,
    can_add_node,
    critical_path,
    detect_cycle,
    evaluate_readiness,
    ready_node_ids,
    topological_layers,
    validate_graph,
)
from harness.orchestration.models import (
    ExecutionGraph,
    ExecutionNode,
    JoinConfig,
    JoinPolicy,
    NodeKind,
    Priority,
    TaskStatus,
)
from harness.orchestration.state import (
    InvalidTransition,
    can_transition_task,
    is_task_terminal,
    require_task_transition,
)


def _node(node_id: str, deps=(), **kw) -> ExecutionNode:
    node = ExecutionNode(id=node_id, kind=NodeKind.FUNCTION, **kw)
    node.dependencies = list(deps)
    return node


def _graph(nodes) -> ExecutionGraph:
    graph = ExecutionGraph(id="g")
    for node in nodes:
        graph.nodes[node.id] = node
    for node in nodes:
        for dep in node.dependencies:
            if dep in graph.nodes:
                graph.nodes[dep].dependents.append(node.id)
    return graph


# ── validation ───────────────────────────────────────────────────────────────


def test_valid_graph_passes():
    validate_graph(_graph([_node("a"), _node("b"), _node("c", ["a", "b"])]))


def test_missing_dependency_is_rejected_with_a_named_reason():
    with pytest.raises(GraphValidationError) as info:
        validate_graph(_graph([_node("c", ["missing"])]))
    assert any("missing node" in e for e in info.value.errors)


def test_self_dependency_is_rejected():
    with pytest.raises(GraphValidationError) as info:
        validate_graph(_graph([_node("a", ["a"])]))
    assert any("depends on itself" in e for e in info.value.errors)


def test_cycle_is_detected():
    nodes = {
        "a": _node("a", ["c"]),
        "b": _node("b", ["a"]),
        "c": _node("c", ["b"]),
    }
    cycle = detect_cycle(nodes)
    assert cycle is not None and len(cycle) >= 3
    with pytest.raises(GraphValidationError) as info:
        validate_graph(_graph(list(nodes.values())))
    assert any("cycle" in e for e in info.value.errors)


def test_empty_graph_is_rejected():
    with pytest.raises(GraphValidationError):
        validate_graph(ExecutionGraph(id="empty"))


def test_duplicate_node_is_rejected_on_insert():
    graph = _graph([_node("a")])
    with pytest.raises(GraphValidationError) as info:
        can_add_node(graph, _node("a"))
    assert "already exists" in info.value.errors[0]


def test_add_edge_that_would_cycle_is_rejected():
    graph = _graph([_node("a", ["b"]), _node("b")])
    with pytest.raises(GraphValidationError):
        can_add_edge(graph, "a", "b")  # would create b -> a -> b


# ── analysis ─────────────────────────────────────────────────────────────────


def test_topological_layers_are_the_concurrency_waves():
    graph = _graph([
        _node("a"), _node("b"), _node("c", ["a", "b"]),
        _node("d", ["b"]), _node("e", ["c", "d"]),
    ])
    assert topological_layers(graph.nodes) == [["a", "b"], ["c", "d"], ["e"]]


def test_critical_path_is_weighted_and_real():
    graph = _graph([
        _node("a", metadata={"estimatedMs": 100}),
        _node("b", metadata={"estimatedMs": 10}),
        _node("c", ["a"], metadata={"estimatedMs": 50}),
        _node("d", ["b"], metadata={"estimatedMs": 1}),
        _node("e", ["c", "d"], metadata={"estimatedMs": 5}),
    ])
    path, total = critical_path(graph)
    assert path == ["a", "c", "e"]
    assert total == 155


def test_ready_and_readiness_rules():
    graph = _graph([_node("a"), _node("b", ["a"])])
    assert ready_node_ids(graph) == ["a"]
    graph.nodes["a"].status = TaskStatus.COMPLETED
    assert ready_node_ids(graph) == ["b"]
    graph.nodes["b"].status = TaskStatus.PENDING
    graph.nodes["a"].status = TaskStatus.FAILED
    assert evaluate_readiness(graph.nodes["b"], graph) is Readiness.SKIPPED


def test_first_success_join_runs_early():
    graph = _graph([
        _node("a"), _node("b"),
        _node("c", ["a", "b"], join=JoinConfig(policy=JoinPolicy.FIRST_SUCCESS)),
    ])
    graph.nodes["a"].status = TaskStatus.COMPLETED
    graph.nodes["b"].status = TaskStatus.RUNNING
    assert evaluate_readiness(graph.nodes["c"], graph) is Readiness.READY


def test_quorum_waits_for_threshold():
    graph = _graph([
        _node("a"), _node("b"), _node("c"),
        _node("j", ["a", "b", "c"], join=JoinConfig(policy=JoinPolicy.QUORUM, threshold=2)),
    ])
    graph.nodes["a"].status = TaskStatus.COMPLETED
    assert evaluate_readiness(graph.nodes["j"], graph) is Readiness.WAITING
    graph.nodes["b"].status = TaskStatus.COMPLETED
    assert evaluate_readiness(graph.nodes["j"], graph) is Readiness.READY


def test_allow_partial_join_runs_with_failures_as_data():
    graph = _graph([
        _node("a"), _node("b"),
        _node("agg", ["a", "b"], join=JoinConfig(policy=JoinPolicy.ALL, allow_partial=True)),
    ])
    graph.nodes["a"].status = TaskStatus.COMPLETED
    graph.nodes["b"].status = TaskStatus.FAILED
    assert evaluate_readiness(graph.nodes["agg"], graph) is Readiness.READY


# ── state machine ────────────────────────────────────────────────────────────


def test_only_valid_task_transitions_are_allowed():
    assert can_transition_task(TaskStatus.PENDING, TaskStatus.READY)
    assert not can_transition_task(TaskStatus.PENDING, TaskStatus.RUNNING)
    assert not can_transition_task(TaskStatus.COMPLETED, TaskStatus.RUNNING)
    with pytest.raises(InvalidTransition):
        require_task_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)


def test_terminal_states_have_no_normal_edges():
    assert is_task_terminal(TaskStatus.COMPLETED)
    assert not can_transition_task(TaskStatus.COMPLETED, TaskStatus.READY)


def test_failed_can_be_retried_but_not_arbitrarily():
    # The one controlled retry edge, and nothing else.
    assert can_transition_task(TaskStatus.FAILED, TaskStatus.PENDING)
    assert not can_transition_task(TaskStatus.FAILED, TaskStatus.RUNNING)
