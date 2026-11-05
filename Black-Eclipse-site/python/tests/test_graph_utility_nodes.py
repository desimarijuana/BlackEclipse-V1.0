"""Pure utility nodes + the two memory adapters."""

from __future__ import annotations

import pytest

from harness.eclipse_memory.store import MEMORY_TYPES as STORE_MEMORY_TYPES
from harness.graph_runtime.memory_nodes import (
    MEMORY_TYPES,
    set_memory_recall_runner,
    set_memory_remember_runner,
)
from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext

REGISTRY = build_default_registry()


def _exec(node_type: str, config: dict, inputs: dict, *, test_run: bool = False):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.RESEARCH,
        inputs=inputs, config=config, test_run=test_run,
    ))


# ── logic.assert ─────────────────────────────────────────────────────────────

def test_assert_passes_and_forwards_the_value():
    result = _exec("logic.assert", {"expect": "truthy"}, {"value": 3})
    assert result["value"] == 3
    assert result["_control"] == ["done"]


def test_assert_fails_with_the_configured_message():
    with pytest.raises(ValueError, match="need at least one row"):
        _exec("logic.assert", {"expect": "truthy", "message": "need at least one row"}, {"value": 0})


def test_assert_message_from_the_wire_wins_and_defaults_honestly():
    with pytest.raises(ValueError, match="wired message"):
        _exec("logic.assert", {"message": "configured"}, {"value": None, "message": "wired message"})
    with pytest.raises(ValueError, match="expected the value to be truthy"):
        _exec("logic.assert", {}, {"value": None})


def test_assert_falsy_and_present_semantics():
    assert _exec("logic.assert", {"expect": "falsy"}, {"value": 0})["value"] == 0
    assert _exec("logic.assert", {"expect": "present"}, {"value": {"a": 1}})["value"] == {"a": 1}
    # present treats an empty container as absent — the logic.merge rule.
    with pytest.raises(ValueError):
        _exec("logic.assert", {"expect": "present"}, {"value": {}})
    with pytest.raises(ValueError):
        _exec("logic.assert", {"expect": "present"}, {"value": ""})


def test_assert_rejects_an_unknown_expectation():
    with pytest.raises(ValueError, match="unsupported assert expectation"):
        _exec("logic.assert", {"expect": "maybe"}, {"value": True})


# ── logic.fallback ───────────────────────────────────────────────────────────

def test_fallback_returns_the_first_present_input():
    result = _exec("logic.fallback", {}, {"in1": "", "in2": None, "in3": "third"})
    assert result["value"] == "third"
    assert result["source"] == "in3"


def test_fallback_prefers_the_earliest_present_input():
    result = _exec("logic.fallback", {}, {"in1": 0, "in2": "second"})
    # 0 is PRESENT (only null/''/[]/{} are absent).
    assert result["value"] == 0
    assert result["source"] == "in1"


def test_fallback_all_absent_is_null_not_zero():
    result = _exec("logic.fallback", {}, {})
    assert result["value"] is None
    assert result["source"] == ""


# ── data.extract ─────────────────────────────────────────────────────────────

def test_extract_reads_a_nested_path_and_a_list_index():
    payload = {"data": {"items": [{"price": 12.5}]}}
    result = _exec("data.extract", {"path": "data.items.0.price"}, {"value": payload})
    assert result["value"] == 12.5
    assert result["found"] is True


def test_extract_missing_path_returns_found_false_or_fails():
    result = _exec("data.extract", {"path": "data.nope"}, {"value": {"data": {}}})
    assert result == {"value": None, "found": False, "_control": ["done"]}
    with pytest.raises(ValueError, match="no value at 'nope'"):
        _exec("data.extract", {"path": "data.nope", "onMissing": "error"}, {"value": {"data": {}}})


def test_extract_out_of_range_and_non_numeric_segments_are_missing():
    assert _exec("data.extract", {"path": "rows.5"}, {"value": {"rows": [1]}})["found"] is False
    assert _exec("data.extract", {"path": "rows.x"}, {"value": {"rows": [1]}})["found"] is False
    assert _exec("data.extract", {"path": "a.b"}, {"value": {"a": 7}})["found"] is False


def test_extract_requires_a_path():
    with pytest.raises(ValueError, match="needs a path"):
        _exec("data.extract", {}, {"value": {}})


# ── memory ───────────────────────────────────────────────────────────────────

def test_memory_types_mirror_the_store():
    assert set(MEMORY_TYPES) == set(STORE_MEMORY_TYPES)


@pytest.fixture()
def memory_runners():
    state: dict = {"recall": None, "remember": None, "recall_args": None, "remember_args": None}

    def recall(context, args):
        state["recall_args"] = args
        return state["recall"] or {"memories": [], "context": ""}

    def remember(context, args):
        state["remember_args"] = args
        return state["remember"] or {"memory": {"id": "mem_1", "memoryType": "observation"}}

    set_memory_recall_runner(recall)
    set_memory_remember_runner(remember)
    try:
        yield state
    finally:
        set_memory_recall_runner(None)
        set_memory_remember_runner(None)


def test_recall_projects_memories_and_count(memory_runners):
    memory_runners["recall"] = {"memories": [{"id": "m1", "content": "likes gold"}], "context": "## memory"}
    result = _exec("memory.recall", {"types": "semantic, preference", "limit": 3, "scope": "user"},
                   {"query": "gold"})
    assert result["count"] == 1
    assert result["context"] == "## memory"
    assert memory_runners["recall_args"] == {
        "query": "gold", "types": ["semantic", "preference"], "limit": 3, "scope": "user",
    }


def test_recall_requires_a_query_and_a_bound_service(memory_runners):
    with pytest.raises(ValueError, match="needs a query"):
        _exec("memory.recall", {}, {})
    set_memory_recall_runner(None)
    with pytest.raises(ValueError, match="memory service"):
        _exec("memory.recall", {"query": "gold"}, {})


def test_recall_rejects_an_unknown_memory_type(memory_runners):
    with pytest.raises(ValueError, match="unknown memory type"):
        _exec("memory.recall", {"query": "gold", "types": "vibes"}, {})


def test_remember_writes_and_projects_the_record(memory_runners):
    result = _exec("memory.remember", {
        "memoryType": "preference", "scope": "user", "subject": "gold", "importance": 0.9,
    }, {"content": "prefers XAUUSD"})
    assert result["written"] is True
    assert result["memory"]["id"] == "mem_1"
    assert memory_runners["remember_args"] == {
        "content": "prefers XAUUSD", "memoryType": "preference",
        "scope": "user", "subject": "gold", "importance": 0.9,
    }


def test_remember_refuses_a_test_run(memory_runners):
    with pytest.raises(ValueError, match="test run never writes memory"):
        _exec("memory.remember", {}, {"content": "note"}, test_run=True)


def test_remember_validates_content_type_and_importance(memory_runners):
    with pytest.raises(ValueError, match="needs content"):
        _exec("memory.remember", {}, {})
    with pytest.raises(ValueError, match="unknown memory type"):
        _exec("memory.remember", {"memoryType": "vibes"}, {"content": "note"})
    with pytest.raises(ValueError, match="between 0 and 1"):
        _exec("memory.remember", {"importance": 1.5}, {"content": "note"})


def test_remember_fails_when_the_service_did_not_confirm(memory_runners):
    memory_runners["remember"] = {"memory": {}}
    with pytest.raises(ValueError, match="did not confirm"):
        _exec("memory.remember", {}, {"content": "note"})
