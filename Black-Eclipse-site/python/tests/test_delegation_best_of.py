"""`best_of`: N attempts at the SAME task, chosen by evidence not by vote.

The selection rule is deterministic: confirmed claims and verified handles win,
unconfirmed claims are a penalty, a non-empty answer breaks ties, then fewer
tokens. Only a completed attempt can win; when none finished the answer is None.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.delegation import (
    ChildOutcome,
    DelegationChild,
    DelegationRequest,
    HandleVerifier,
    WIDTH_EXCEEDED,
    aggregate_best_of,
    run_delegation,
    select_best,
)
from harness.skills.permissions import Actor


def _parent() -> Actor:
    return Actor(id="parent", operator=False, grants=frozenset({"data.read"}))


def _verifier() -> HandleVerifier:
    return HandleVerifier(
        run_exists=lambda rid: rid.startswith("run_"),
        ledger_has=lambda cid: cid == "cmd_ok",
        artifact_exists=lambda _d: False,
    )


async def _runner(child, run_id, allowed, actor):
    if "_child0_" in run_id:
        return {
            "status": "completed", "runId": run_id, "summary": "All tests pass.",
            "handles": [{"kind": "check_record_id", "value": "cmd_ok"}], "tokens": 500,
        }
    if "_child1_" in run_id:
        return {
            "status": "completed", "runId": run_id, "summary": "All tests pass.",
            "handles": [], "tokens": 100,
        }
    return {"status": "failed", "runId": run_id, "summary": "", "handles": [], "reason": "boom"}


# ── the selector ─────────────────────────────────────────────────────────────


def test_a_verified_claim_beats_a_louder_unverified_one():
    outcomes = [
        ChildOutcome(child_index=0, status="completed", summary="All tests pass.",
                     claimed=[], dropped=["All tests pass."], tokens=10),
        ChildOutcome(child_index=1, status="completed", summary="All tests pass.",
                     claimed=["All tests pass."], dropped=[], tokens=900),
    ]
    assert select_best(outcomes) == 1


def test_fewer_tokens_breaks_a_tie():
    outcomes = [
        ChildOutcome(child_index=0, status="completed", summary="done", tokens=800),
        ChildOutcome(child_index=1, status="completed", summary="done", tokens=200),
    ]
    assert select_best(outcomes) == 1


def test_an_empty_answer_does_not_beat_a_real_one():
    outcomes = [
        ChildOutcome(child_index=0, status="completed", summary=""),
        ChildOutcome(child_index=1, status="completed", summary="Here is the answer."),
    ]
    assert select_best(outcomes) == 1


def test_only_a_completed_attempt_can_win():
    outcomes = [
        ChildOutcome(child_index=0, status="failed", summary="All tests pass."),
        ChildOutcome(child_index=1, status="timed_out", summary="All tests pass."),
    ]
    assert select_best(outcomes) is None


# ── end to end (the injected runner stands in for execute_run) ───────────────


async def test_best_of_selects_the_strongest_attempt_and_quotes_only_it():
    result = await run_delegation(
        DelegationRequest(
            children=[DelegationChild(goal="Fix checkout") for _ in range(3)],
            strategy="best_of",
        ),
        parent_run_id="run_parent",
        parent_actor=_parent(),
        parent_allowed=None,
        depth=0,
        run_child=_runner,
        verifier=_verifier(),
    )
    assert result.strategy == "best_of"
    assert result.winner == 0
    assert "Best of 3" in result.aggregate
    assert "attempt 1" in result.aggregate
    assert "All tests pass." in result.aggregate
    assert result.outcomes[1].dropped  # the unverified claim was dropped
    assert "not repeated as fact" in result.aggregate


async def test_best_of_with_no_finished_attempt_names_no_winner():
    async def failed(child, run_id, allowed, actor):
        return {"status": "failed", "runId": run_id, "summary": "", "handles": [], "reason": "boom"}

    result = await run_delegation(
        DelegationRequest(
            children=[DelegationChild(goal="Fix checkout") for _ in range(2)],
            strategy="best_of",
        ),
        parent_run_id="run_parent", parent_actor=_parent(), parent_allowed=None,
        depth=0, run_child=failed, verifier=_verifier(),
    )
    assert result.winner is None
    assert "None of the 2 attempts finished" in result.aggregate


async def test_best_of_is_labelled_on_the_started_event():
    seen: list[tuple[str, dict]] = []

    async def on_event(event_type, data):
        seen.append((event_type, data))

    await run_delegation(
        DelegationRequest(
            children=[
                DelegationChild(
                    goal="Fix checkout", model="phi3", approach="mock the API",
                ),
            ],
            strategy="best_of",
        ),
        parent_run_id="run_parent", parent_actor=_parent(), parent_allowed=None,
        depth=0, run_child=_runner, verifier=_verifier(), on_event=on_event,
    )
    started = next(data for event, data in seen if event == "delegation.started")
    assert started["strategy"] == "best_of"
    assert started["agents"][0]["model"] == "phi3"
    assert started["agents"][0]["approach"] == "mock the API"
    aggregated = next(data for event, data in seen if event == "delegation.aggregated")
    assert aggregated["winner"] == 0


def test_aggregate_best_of_handles_an_empty_run():
    from harness.delegation import DelegationResult

    result = DelegationResult(delegationId="dlg", strategy="best_of", outcomes=[])
    assert aggregate_best_of(result) == "I didn't have anything to compare."


# ── the tool builds the N parts from one goal ────────────────────────────────


class _FakeResult:
    def __init__(self, run_id: str) -> None:
        self._run_id = run_id

    def model_dump(self) -> dict:
        return {"runId": self._run_id, "status": "completed", "output": "done", "error": None, "totalTokens": 0}


def test_the_tool_builds_count_parts_with_the_same_goal(monkeypatch):
    import harness.graph as graph_mod
    from harness.code.tools import register_code_tools
    from harness.delegation_tools import delegate_handler
    from harness.schemas import ModelSettings
    from harness.tools import ToolContext, ToolRegistry

    seen: list = []

    async def fake_execute_run(request, *args, **kwargs):
        seen.append(request)
        return _FakeResult(request.runId)

    monkeypatch.setattr(graph_mod, "execute_run", fake_execute_run)

    reg = ToolRegistry()
    register_code_tools(reg)
    ctx = ToolContext(
        run_id="run_parent", log=lambda *_: None,
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(), data_bridge=object(), memory_store=None,
        allowed={"delegate"}, delegation_depth=0,
    )
    result = asyncio.run(reg.execute(
        "delegate", "c1",
        {"strategy": "best_of", "goal": "Fix the flaky checkout test", "count": 3},
        ctx,
    ))
    assert result.ok is True
    assert len(seen) == 3
    assert {r.input.query for r in seen} == {"Fix the flaky checkout test"}
    assert result.data["strategy"] == "best_of"
    assert result.data["winner"] == 0  # equal attempts, earliest wins deterministically


def test_best_of_can_try_a_different_model_per_attempt(monkeypatch):
    import harness.graph as graph_mod
    from harness.code.tools import register_code_tools
    from harness.schemas import ModelSettings
    from harness.tools import ToolContext, ToolRegistry

    seen: list = []

    async def fake_execute_run(request, *args, **kwargs):
        seen.append(request)
        return _FakeResult(request.runId)

    monkeypatch.setattr(graph_mod, "execute_run", fake_execute_run)

    reg = ToolRegistry()
    register_code_tools(reg)
    ctx = ToolContext(
        run_id="run_parent", log=lambda *_: None,
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(), data_bridge=object(), memory_store=None,
        allowed={"delegate"}, delegation_depth=0,
    )
    result = asyncio.run(reg.execute(
        "delegate", "c1",
        {
            "strategy": "best_of", "goal": "Fix it", "count": 2,
            "models": ["llama3.1", "phi3"],
            "temperatures": [0.2, 1.1],
            "approaches": ["retry with backoff", "mock the API"],
            "contexts": ["read the failing test", "read the network log"],
        },
        ctx,
    ))
    assert result.ok is True
    assert [r.modelSettings.model for r in seen] == ["llama3.1", "phi3"]
    assert [r.modelSettings.temperature for r in seen] == [0.2, 1.1]
    assert "Approach: retry with backoff" in seen[0].input.query
    assert "Approach: mock the API" in seen[1].input.query
    # Each attempt gets ONLY its own background, never another's.
    assert "read the failing test" in seen[0].input.query
    assert "read the network log" not in seen[0].input.query
    assert "read the network log" in seen[1].input.query
    # The provider (and therefore the credential) never changes.
    assert {r.modelSettings.provider for r in seen} == {"ollama"}


def test_the_tool_refuses_a_one_attempt_best_of():
    from harness.code.tools import register_code_tools
    from harness.schemas import ModelSettings
    from harness.tools import ToolContext, ToolRegistry

    reg = ToolRegistry()
    register_code_tools(reg)
    ctx = ToolContext(
        run_id="run_parent", log=lambda *_: None,
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(), data_bridge=object(), memory_store=None,
        allowed={"delegate"}, delegation_depth=0,
    )
    result = asyncio.run(reg.execute(
        "delegate", "c1", {"strategy": "best_of", "goal": "Fix it", "count": 1}, ctx,
    ))
    assert result.data["status"] == "refused"
    assert result.data["code"] == WIDTH_EXCEEDED


def test_the_tool_refuses_mixing_children_with_best_of():
    from harness.code.tools import register_code_tools
    from harness.schemas import ModelSettings
    from harness.tools import ToolContext, ToolRegistry

    reg = ToolRegistry()
    register_code_tools(reg)
    ctx = ToolContext(
        run_id="run_parent", log=lambda *_: None,
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(), data_bridge=object(), memory_store=None,
        allowed={"delegate"}, delegation_depth=0,
    )
    result = asyncio.run(reg.execute(
        "delegate", "c1",
        {"strategy": "best_of", "goal": "Fix it", "children": [{"goal": "a"}]}, ctx,
    ))
    assert result.data["status"] == "refused"
    assert result.data["code"] == "DELEGATION_INVALID"
