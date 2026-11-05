"""The live control plane for an in-editor assistant turn.

These tests cover the state machine only; the tool loop is covered by
``test_graph_assistant.py``. Pause must be cooperative (it never interrupts a
tool result) and cancel must be sticky so a woken waiter cannot continue.
"""

import asyncio

import pytest

from harness.graph_runtime import assistant_runs
from harness.graph_runtime.assistant_runs import AssistantRunCancelled


@pytest.fixture(autouse=True)
def _clean_registry():
    assistant_runs._RUNS.clear()
    yield
    assistant_runs._RUNS.clear()


def test_pause_and_resume_transition_status():
    run = assistant_runs.create_run(workflow_id="w1")
    assert run.status == "running"

    paused = assistant_runs.pause_run(run.id)
    assert paused is not None and paused["status"] == "paused"

    resumed = assistant_runs.resume_run(run.id)
    assert resumed is not None and resumed["status"] == "running"


def test_cancel_is_terminal_and_wakes_a_paused_waiter():
    async def scenario():
        run = assistant_runs.create_run(workflow_id="w1")
        run.pause()

        waiter = asyncio.create_task(run.wait_until_resumed())
        await asyncio.sleep(0)
        assert not waiter.done()

        assistant_runs.cancel_run(run.id)
        with pytest.raises(AssistantRunCancelled):
            await waiter
        assert assistant_runs.get_run(run.id).status == "cancelled"

    asyncio.run(scenario())


def test_resume_releases_a_paused_waiter():
    async def scenario():
        run = assistant_runs.create_run(workflow_id="w1")
        run.pause()
        waiter = asyncio.create_task(run.wait_until_resumed())
        await asyncio.sleep(0)
        assistant_runs.resume_run(run.id)
        await waiter  # returns without raising
        assert run.status == "running"

    asyncio.run(scenario())


def test_terminal_run_ignores_late_controls():
    run = assistant_runs.create_run(workflow_id="w1")
    run.finish("completed")
    assert assistant_runs.pause_run(run.id)["status"] == "completed"
    assert assistant_runs.resume_run(run.id)["status"] == "completed"
    assert assistant_runs.cancel_run(run.id)["status"] == "completed"


def test_unknown_run_returns_none():
    assert assistant_runs.get_run("missing") is None
    assert assistant_runs.pause_run("missing") is None
    assert assistant_runs.resume_run("missing") is None
    assert assistant_runs.cancel_run("missing") is None
