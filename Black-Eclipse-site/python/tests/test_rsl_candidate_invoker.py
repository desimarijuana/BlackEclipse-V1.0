"""RSL R3 — a candidate snapshot runs on the real graph, isolated from production."""

from __future__ import annotations

import asyncio

import pytest

from harness.evaluation.candidate_invoker import CandidateAgentInvoker, SnapshotError
from harness.evaluation.environments import build_environment
from harness.evaluation.runner import EvaluationRunner
from harness.evaluation.store import EvaluationStore
from harness.evaluation.tasks import EvaluationTask
from harness.persistence import AgentMemoryStore
from harness.self_improvement.models import HarnessSnapshot


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


def _base(tools: tuple[str, ...] = ("eval_fs_write", "eval_fs_read", "eval_memory_write", "eval_memory_read")):
    return HarnessSnapshot(
        systemPrompt="You are Eclipse.",
        toolNames=tools,
        maxSteps=8,
        maxToolCalls=8,
    )


def _snapshot(tools: tuple[str, ...], *, prompt: str = "You are a candidate."):
    return HarnessSnapshot(
        systemPrompt=prompt, toolNames=tools, maxSteps=8, maxToolCalls=8,
    )


def _write_task(task_id: str = "rsl.write") -> EvaluationTask:
    return EvaluationTask.from_dict({
        "id": task_id, "category": "tools", "difficulty": "easy",
        "input": {"prompt": "write f"},
        "environment": {"type": "filesystem"},
        "expected_state": {"files": {"f.txt": {"contains": "hi"}}},
        "expected_tools": ["eval_fs_write"],
        "graders": [{"name": "state"}],
        "metadata": {
            "agent_script": [
                {"type": "tool", "calls": [{"name": "eval_fs_write", "args": {"path": "f.txt", "content": "hi"}}]},
                {"type": "final", "content": "done"},
            ],
        },
    })


def _memory_task(task_id: str, value: str) -> EvaluationTask:
    return EvaluationTask.from_dict({
        "id": task_id, "category": "memory", "difficulty": "easy",
        "input": {"prompt": "remember"},
        "environment": {"type": "memory"},
        "metadata": {
            "agent_script": [
                {"type": "tool", "calls": [
                    {"name": "eval_memory_write", "args": {"key": "k", "value": value}},
                ]},
                {"type": "tool", "calls": [{"name": "eval_memory_read", "args": {"key": "k"}}]},
                {"type": "final", "content": "done"},
            ],
        },
    })


def _environment(task: EvaluationTask):
    environment = build_environment(task.environment or {})
    environment.reset(task.initial_state or {})
    return environment


@pytest.mark.asyncio
async def test_candidate_snapshot_changes_the_trial(store):
    task = _write_task()
    base = _base()
    invoker_a = CandidateAgentInvoker(
        store, _snapshot(("eval_fs_write", "eval_fs_read"), prompt="candidate A"), base=base,
    )
    invoker_b = CandidateAgentInvoker(store, _snapshot((), prompt="candidate B"), base=base)
    env_a, env_b = _environment(task), _environment(task)
    try:
        result_a = await invoker_a.invoke(task, "a", env_a)
        result_b = await invoker_b.invoke(task, "b", env_b)

        assert result_a.run_id != result_b.run_id
        assert result_a.status == "completed"
        assert result_b.status == "completed"
        assert env_a.read("f.txt") == "hi"
        assert not any(
            event["type"] == "tool.failed"
            and event["data"].get("code") == "TOOL_FORBIDDEN"
            for event in result_a.events
        )
        assert any(
            event["type"] == "tool.failed"
            and event["data"].get("code") == "TOOL_FORBIDDEN"
            for event in result_b.events
        )
    finally:
        env_a.teardown()
        env_b.teardown()


@pytest.mark.asyncio
async def test_candidate_runs_through_the_runner_and_is_graded(store):
    task = _write_task("rsl.graded")
    invoker = CandidateAgentInvoker(
        store, _snapshot(("eval_fs_write", "eval_fs_read")), base=_base(),
    )
    runner = EvaluationRunner(
        store, invoker=invoker, eval_store=EvaluationStore(store),
    )
    result = await runner.run_task(task, trials=1, persist=False)
    trial = result.trials[0]
    assert trial.unmeasured is False
    assert trial.passed is True
    assert trial.score.passed is True
    assert "f.txt" in trial.env_state["paths"]


@pytest.mark.asyncio
async def test_a_candidate_run_never_writes_the_production_store(store):
    store.create_run("prod-run", "eclipse-agent", {"query": "production"})
    before_runs = len(store.list_runs())
    before_events = len(store.list_events("prod-run"))

    task = _write_task()
    invoker = CandidateAgentInvoker(
        store, _snapshot(("eval_fs_write", "eval_fs_read")), base=_base(),
    )
    environment = _environment(task)
    try:
        await invoker.invoke(task, "isolated", environment)
    finally:
        environment.teardown()

    assert len(store.list_runs()) == before_runs
    assert len(store.list_events("prod-run")) == before_events


@pytest.mark.asyncio
async def test_concurrent_candidate_trials_do_not_see_each_other(store):
    task_a = _memory_task("rsl.memory.a", "A")
    task_b = _memory_task("rsl.memory.b", "B")
    invoker = CandidateAgentInvoker(
        store, _snapshot(("eval_memory_write", "eval_memory_read")), base=_base(),
    )
    env_a, env_b = _environment(task_a), _environment(task_b)
    try:
        result_a, result_b = await asyncio.gather(
            invoker.invoke(task_a, "a", env_a),
            invoker.invoke(task_b, "b", env_b),
        )
        assert result_a.run_id != result_b.run_id
        assert env_a.inspect_state()["entries"] == {"k": "A"}
        assert env_b.inspect_state()["entries"] == {"k": "B"}
    finally:
        env_a.teardown()
        env_b.teardown()


@pytest.mark.asyncio
async def test_unregistered_tool_is_a_structured_failure(store):
    task = _write_task()
    base = _base(("eval_fs_write", "not_registered"))
    invoker = CandidateAgentInvoker(
        store, _snapshot(("eval_fs_write", "not_registered")), base=base,
    )
    environment = _environment(task)
    try:
        result = await invoker.invoke(task, "unknown", environment)
    finally:
        environment.teardown()
    assert result.status == "failed"
    assert result.error is not None
    assert result.error["code"] == "CANDIDATE_UNKNOWN_TOOL"


def test_live_bridge_is_refused_in_r3(store):
    with pytest.raises(SnapshotError) as exc:
        CandidateAgentInvoker(
            store, _snapshot(("eval_fs_write",)), base=_base(),
            allow_live_bridge=True,
        )
    assert exc.value.code == "CANDIDATE_LIVE_BRIDGE_UNAVAILABLE"
