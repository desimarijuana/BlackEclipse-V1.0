"""Team task-graph validation and readiness (Feature C, pure)."""

from __future__ import annotations

from harness.tasks.model import TaskStatus
from harness.team.graph import (
    failed_dependencies,
    is_runnable,
    map_task_status,
    ready_ids,
    topological_layers,
    validate_graph,
)
from harness.team.model import TeamSubtask, TeamSubtaskStatus


def _sub(sid, deps=(), required=True):
    return TeamSubtask(id=sid, objective=f"do {sid}", depends_on=list(deps), required=required)


def test_valid_graph_has_no_errors():
    subs = [_sub("a"), _sub("b", ["a"]), _sub("c", ["a"]), _sub("d", ["b", "c"])]
    assert validate_graph(subs) == []


def test_duplicate_ids_are_rejected():
    errors = validate_graph([_sub("a"), _sub("a")])
    assert any("duplicate" in e for e in errors)


def test_unknown_dependency_is_rejected():
    errors = validate_graph([_sub("a", ["ghost"])])
    assert any("unknown subtask" in e for e in errors)


def test_cycle_is_detected():
    errors = validate_graph([_sub("a", ["b"]), _sub("b", ["c"]), _sub("c", ["a"])])
    assert any("cycle" in e for e in errors)


def test_self_dependency_is_rejected_by_the_contract():
    import pytest

    with pytest.raises(Exception):
        _sub("a", ["a"])


def test_topological_layers_orders_dependencies():
    subs = [_sub("a"), _sub("b", ["a"]), _sub("c", ["a"]), _sub("d", ["b", "c"])]
    layers = topological_layers(subs)
    assert layers[0] == ["a"]
    assert set(layers[1]) == {"b", "c"}
    assert layers[2] == ["d"]


def test_readiness_respects_dependencies():
    subs = [_sub("a"), _sub("b", ["a"])]
    statuses = {"a": TeamSubtaskStatus.COMPLETED, "b": TeamSubtaskStatus.PENDING}
    assert ready_ids(subs, statuses) == ["b"]
    statuses["a"] = TeamSubtaskStatus.FAILED
    assert ready_ids(subs, statuses) == []
    assert failed_dependencies(subs[1], statuses) == ["a"]
    assert not is_runnable(subs[1], statuses)


def test_task_status_projection():
    assert map_task_status(TaskStatus.IN_PROGRESS) is TeamSubtaskStatus.RUNNING
    assert map_task_status(TaskStatus.TODO) is TeamSubtaskStatus.PENDING
    assert map_task_status("COMPLETED") is TeamSubtaskStatus.COMPLETED
    assert map_task_status("BLOCKED") is TeamSubtaskStatus.BLOCKED
