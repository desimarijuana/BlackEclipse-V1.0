"""Unit tests for the pure task-graph math: cycles, runnability, roll-ups."""

from __future__ import annotations

from harness.tasks.dag import (
    all_dependencies_satisfied,
    derive_parent_progress,
    derive_parent_status,
    detect_cycle,
    topological_layers,
    unmet_dependencies,
)
from harness.tasks.model import FailurePolicy, TaskStatus


def test_detect_cycle_none_for_a_dag():
    edges = [("D", "A"), ("D", "B"), ("B", "C")]
    assert detect_cycle(edges) is None


def test_detect_cycle_finds_a_back_edge():
    edges = [("A", "B"), ("B", "C"), ("C", "A")]
    cycle = detect_cycle(edges)
    assert cycle is not None
    assert cycle[0] == cycle[-1]


def test_detect_cycle_self_edge():
    assert detect_cycle([("A", "A")]) is not None


def test_unmet_dependencies():
    deps = [("A", TaskStatus.COMPLETED), ("B", TaskStatus.IN_PROGRESS)]
    assert unmet_dependencies(deps) == ["B"]
    assert not all_dependencies_satisfied(deps)
    assert all_dependencies_satisfied([("A", TaskStatus.COMPLETED)])
    # A failed prerequisite is unmet (the dependent is blocked, not runnable).
    assert unmet_dependencies([("A", TaskStatus.FAILED)]) == ["A"]


def test_parent_status_all_completed():
    children = [(TaskStatus.COMPLETED, True, FailurePolicy.FAIL_FAST)] * 3
    assert derive_parent_status(children) == TaskStatus.COMPLETED


def test_parent_status_mixed_running_and_todo_is_in_progress():
    children = [
        (TaskStatus.IN_PROGRESS, True, FailurePolicy.FAIL_FAST),
        (TaskStatus.TODO, True, FailurePolicy.FAIL_FAST),
    ]
    assert derive_parent_status(children) == TaskStatus.IN_PROGRESS


def test_parent_status_all_blocked_is_blocked():
    children = [
        (TaskStatus.BLOCKED, True, FailurePolicy.FAIL_FAST),
        (TaskStatus.BLOCKED, True, FailurePolicy.FAIL_FAST),
    ]
    assert derive_parent_status(children) == TaskStatus.BLOCKED


def test_parent_status_one_blocked_one_todo_is_in_progress():
    children = [
        (TaskStatus.BLOCKED, True, FailurePolicy.FAIL_FAST),
        (TaskStatus.TODO, True, FailurePolicy.FAIL_FAST),
    ]
    assert derive_parent_status(children) == TaskStatus.IN_PROGRESS


def test_parent_status_failed_under_fail_fast():
    children = [
        (TaskStatus.FAILED, True, FailurePolicy.FAIL_FAST),
        (TaskStatus.TODO, True, FailurePolicy.FAIL_FAST),
    ]
    assert derive_parent_status(children) == TaskStatus.FAILED


def test_parent_status_continue_policy_ignores_a_failed_child():
    # A non-required (optional) failed child does not fail the parent.
    children = [
        (TaskStatus.FAILED, False, FailurePolicy.CONTINUE),
        (TaskStatus.IN_PROGRESS, True, FailurePolicy.CONTINUE),
    ]
    assert derive_parent_status(children) == TaskStatus.IN_PROGRESS


def test_parent_status_waiting_only():
    children = [(TaskStatus.WAITING, True, FailurePolicy.FAIL_FAST)]
    assert derive_parent_status(children) == TaskStatus.WAITING


def test_parent_status_no_children_is_none():
    assert derive_parent_status([]) is None


def test_weighted_progress():
    # Two of four equally weighted, two complete -> 50%.
    children = [
        (0, 1.0, TaskStatus.TODO),
        (0, 1.0, TaskStatus.TODO),
        (100, 1.0, TaskStatus.COMPLETED),
        (100, 1.0, TaskStatus.COMPLETED),
    ]
    assert derive_parent_progress(children) == 50


def test_weighted_progress_respects_weights():
    # A heavy completed child dominates.
    children = [
        (0, 9.0, TaskStatus.TODO),
        (100, 1.0, TaskStatus.COMPLETED),
    ]
    assert derive_parent_progress(children) == 10


def test_progress_clamps_impossible_values():
    children = [(250, 1.0, TaskStatus.TODO), (100, 1.0, TaskStatus.TODO)]
    value = derive_parent_progress(children)
    assert 0 <= value <= 100


def test_topological_layers():
    nodes = ["A", "B", "C", "D"]
    edges = [("D", "A"), ("D", "B"), ("D", "C")]
    layers = topological_layers(nodes, edges)
    assert layers is not None
    assert set(layers[0]) == {"A", "B", "C"}
    assert layers[1] == ["D"]


def test_topological_layers_none_on_cycle():
    assert topological_layers(["A", "B"], [("A", "B"), ("B", "A")]) is None
