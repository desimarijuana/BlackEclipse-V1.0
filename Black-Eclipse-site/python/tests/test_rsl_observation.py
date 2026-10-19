"""RSL R1 — the observation closure: recurrence, candidates, mining, no activation."""

from __future__ import annotations

import json

import pytest

from harness.code import evolution
from harness.code.evolution_store import EvolutionStore
from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.evaluation.store import EvaluationStore
from harness.learning_review import review_run
from harness.persistence import AgentMemoryStore
from harness.self_improvement.config import RSLConfig
from harness.self_improvement.observer import observe_run


@pytest.fixture()
def run_store(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield store
    store.close()


@pytest.fixture()
def memory(tmp_path):
    service = EclipseMemoryService(
        EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")),
    )
    yield service
    service.close()


def _cfg(mode: str = "observe") -> RSLConfig:
    return RSLConfig(mode=mode)


def _tool(name: str, ok: bool, code: str | None = None):
    class Error:
        def model_dump_json(self) -> str:
            return json.dumps({"code": code})

    class Tool:
        tool_call_id = f"call_{name}_{code or 'ok'}"
        duration_ms = 5
        args = {}
        error = None if ok else Error()

    Tool.name = name
    Tool.ok = ok
    Tool.text = "ok" if ok else f"Tool error ({code})"
    return Tool()


def _failed_run(store: AgentMemoryStore, run_id: str) -> None:
    store.create_run(run_id, "eclipse-agent", {"query": "fetch the price"})
    events = (
        ("run.started", {}),
        ("tool.requested", {"name": "get_market", "args": {"symbol": "AAA"}}),
        ("tool.failed", {"name": "get_market", "code": "TOOL_ERROR"}),
        ("run.failed", {"code": "TOOL_ERROR"}),
    )
    for seq, (event_type, data) in enumerate(events, start=1):
        store.append_event(run_id, event_type, seq, data)
    store.update_run(
        run_id, status="failed", output="", error={"code": "TOOL_ERROR"},
    )


def test_record_mistake_recurrence_is_once_per_run(run_store):
    first = evolution.record_mistake_recurrence(
        run_store, ["timeout", "timeout"], "run-a",
    )
    assert first == {"timeout": 1}
    # Re-analysing the SAME run must not inflate the counter.
    assert evolution.record_mistake_recurrence(run_store, ["timeout"], "run-a") == {
        "timeout": 1,
    }
    assert evolution.record_mistake_recurrence(run_store, ["timeout"], "run-b") == {
        "timeout": 2,
    }


def test_observer_creates_one_inert_candidate_at_threshold(run_store):
    run_store.create_run("r3", "eclipse-agent", {"query": "x"})
    for run_id in ("r1", "r2", "r3"):
        evolution.record_mistake_recurrence(run_store, ["timeout"], run_id)

    result = observe_run("r3", "completed", run_store=run_store, config=_cfg())
    assert result["mode"] == "observe"
    assert result["errors"] == []
    assert len(result["candidates"]) == 1

    candidate = result["candidates"][0]
    assert candidate["sourceCategory"] == "timeout"
    assert candidate["status"] == "inert"
    assert candidate["createdByRunId"] == "r3"
    assert candidate["observedCount"] >= evolution.RECURRENCE_THRESHOLD
    assert EvolutionStore(run_store).list_candidates()[0]["signature"] == candidate["signature"]

    events = [
        event for event in run_store.list_events("r3")
        if event["type"] == "self_improvement.candidate_created"
    ]
    assert len(events) == 1
    assert events[0]["data"]["kind"] == "evolution"
    assert events[0]["data"]["candidateId"] == candidate["id"]

    # Dedupe: the same signature never produces a second candidate.
    second = observe_run("r3", "completed", run_store=run_store, config=_cfg())
    assert second["candidates"] == []
    assert len(EvolutionStore(run_store).list_candidates()) == 1


def test_observe_off_is_a_strict_no_op(run_store):
    _failed_run(run_store, "run_off")
    before = len(run_store.list_events("run_off"))

    result = observe_run(
        "run_off", "failed", run_store=run_store,
        config=RSLConfig.from_env(environ={}),
    )
    assert result == {
        "mode": "off",
        "runId": "run_off",
        "observations": [],
        "candidates": [],
        "mined": None,
        "errors": [],
    }
    assert len(run_store.list_events("run_off")) == before
    assert EvolutionStore(run_store).list_candidates() == []
    assert EvaluationStore(run_store).list_candidates() == []


def test_observe_mines_a_failed_run_once(run_store):
    _failed_run(run_store, "run_fail")

    first = observe_run(
        "run_fail", "failed", run_store=run_store, config=_cfg(),
    )
    assert first["mined"]["created"] is True
    assert first["mined"]["deduplicated"] is False
    assert len(EvaluationStore(run_store).list_candidates()) == 1

    second = observe_run(
        "run_fail", "failed", run_store=run_store, config=_cfg(),
    )
    assert second["mined"]["created"] is False
    assert second["mined"]["deduplicated"] is True
    assert len(EvaluationStore(run_store).list_candidates()) == 1

    events = [
        event for event in run_store.list_events("run_fail")
        if event["type"] == "self_improvement.candidate_created"
    ]
    assert len(events) == 1
    assert events[0]["data"]["kind"] == "mined"


def test_analyze_run_writes_recurrence(memory, run_store):
    run_store.create_run("run_repeat", "eclipse-agent", {"query": "x"})
    run_store.record_tool_execution(
        "run_repeat", _tool("get_fundamentals", False, "TOOL_ERROR"),
    )
    run_store.record_tool_execution(
        "run_repeat", _tool("get_fundamentals", False, "TOOL_ERROR"),
    )
    run_store.update_run("run_repeat", status="failed")

    result = memory.analyze_run("run_repeat", run_store)
    assert "repeated_failure" in result["mistakes"]
    signature = evolution._category_signature("repeated_failure")
    assert run_store.learning_recurrence(signature) == 1

    # Re-analysis is idempotent: already-captured mistakes do not inflate it.
    again = memory.analyze_run("run_repeat", run_store)
    assert again["mistakesCreated"] == 0
    assert run_store.learning_recurrence(signature) == 1


def test_review_run_closes_the_observation_loop(monkeypatch, memory, run_store):
    monkeypatch.setenv("HARNESS_RSL_MODE", "observe")
    for run_id in ("r1", "r2"):
        evolution.record_mistake_recurrence(
            run_store, ["repeated_failure"], run_id,
        )

    run_store.create_run("r3", "eclipse-agent", {"query": "x"})
    run_store.record_tool_execution(
        "r3", _tool("get_fundamentals", False, "TOOL_ERROR"),
    )
    run_store.record_tool_execution(
        "r3", _tool("get_fundamentals", False, "TOOL_ERROR"),
    )
    run_store.update_run("r3", status="failed")

    result = review_run(memory, run_store, "r3")
    assert any(
        outcome.get("payload", {}).get("category") == "evolution"
        for outcome in result["outcomes"]
    )

    candidates = EvolutionStore(run_store).list_candidates()
    assert len(candidates) == 1
    assert candidates[0]["sourceCategory"] == "repeated_failure"
    assert candidates[0]["status"] == "inert"
    assert len(EvaluationStore(run_store).list_candidates()) == 1
