"""Phase 7 G2/G3/G5 — fan-out, the caps (proven), and cancel safety.

`run_delegation` is driven with an injected `run_child`, so no model or runtime
is needed. The caps are asserted by their structured codes, not merely asserted
in prose. A child IS a normal run: the injected seam stands in for `execute_run`.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.delegation import (
    ChildOutcome,
    DelegationChild,
    DelegationError,
    DelegationRequest,
    BUDGET_EXHAUSTED,
    DEPTH_EXCEEDED,
    MAX_CHILDREN,
    MAX_DEPTH,
    WIDTH_EXCEEDED,
    HandleVerifier,
    run_delegation,
)
from harness.skills.permissions import Actor


def _child(goal: str, **kwargs) -> DelegationChild:
    return DelegationChild(goal=goal, **kwargs)


def _parent() -> Actor:
    return Actor(id="parent", operator=False, grants=frozenset({"data.read"}))


async def _ok_runner(record: list[str]):
    async def run_child(child, run_id, allowed, actor):
        record.append(run_id)
        return {"status": "completed", "runId": run_id, "summary": f"looked at {child.goal}", "handles": []}
    return run_child


# ── G2: fan-out completes; each outcome names its runId and terminal status ──


async def test_three_parallel_children_complete():
    record: list[str] = []
    result = await run_delegation(
        DelegationRequest(children=[_child("a"), _child("b"), _child("c")]),
        parent_run_id="run_parent",
        parent_actor=_parent(),
        parent_allowed={"data.read"},
        depth=0,
        run_child=await _ok_runner(record),
    )
    assert len(result.outcomes) == 3
    assert all(o.status == "completed" for o in result.outcomes)
    assert all(o.run_id for o in result.outcomes)
    assert len(record) == 3
    assert result.aggregate
    assert result.workflowId is None


async def test_fan_out_records_a_workflow_id_when_given():
    result = await run_delegation(
        DelegationRequest(children=[_child("a")]),
        parent_run_id="run_parent", parent_actor=_parent(), parent_allowed=None,
        depth=0, run_child=await _ok_runner([]), workflow_id="wf_1",
    )
    assert result.workflowId == "wf_1"
    assert result.to_blob()["workflowId"] == "wf_1"


async def test_one_child_failure_does_not_end_the_others():
    async def run_child(child, run_id, allowed, actor):
        if child.goal == "b":
            raise RuntimeError("boom")
        return {"status": "completed", "runId": run_id, "summary": "ok", "handles": []}

    result = await run_delegation(
        DelegationRequest(children=[_child("a"), _child("b"), _child("c")]),
        parent_run_id="run_parent", parent_actor=_parent(), parent_allowed=None,
        depth=0, run_child=run_child,
    )
    statuses = {o.child_index: o.status for o in result.outcomes}
    assert statuses[0] == "completed" and statuses[2] == "completed"
    assert statuses[1] == "failed"


# ── G3: the caps, proven not asserted ────────────────────────────────────────


async def test_width_exceeded_is_refused():
    children = [_child(f"c{i}") for i in range(MAX_CHILDREN + 1)]
    # The request model itself allows up to 8 so the CAP (not pydantic) refuses.
    request = DelegationRequest(children=children)
    with pytest.raises(DelegationError) as info:
        await run_delegation(
            request, parent_run_id="p", parent_actor=_parent(), parent_allowed=None,
            depth=0, run_child=await _ok_runner([]),
        )
    assert info.value.code == WIDTH_EXCEEDED


async def test_depth_exceeded_is_refused():
    with pytest.raises(DelegationError) as info:
        await run_delegation(
            DelegationRequest(children=[_child("a")]),
            parent_run_id="p", parent_actor=_parent(), parent_allowed=None,
            depth=MAX_DEPTH, run_child=await _ok_runner([]),
        )
    assert info.value.code == DEPTH_EXCEEDED


async def test_unheld_tool_is_refused_for_the_child_not_the_whole_delegation():
    result = await run_delegation(
        DelegationRequest(children=[_child("a", tool_subset=["nope"])]),
        parent_run_id="p", parent_actor=_parent(),
        parent_allowed={"workspace_read"},
        depth=0, run_child=await _ok_runner([]),
    )
    assert result.outcomes[0].status == "refused"
    assert result.outcomes[0].run_id is None


async def test_budget_exhausted_is_refused():
    with pytest.raises(DelegationError) as info:
        await run_delegation(
            DelegationRequest(children=[_child("a"), _child("b")], token_budget=1_500),
            parent_run_id="p", parent_actor=_parent(), parent_allowed=None,
            depth=0, run_child=await _ok_runner([]),
        )
    assert info.value.code == BUDGET_EXHAUSTED


# ── G5: cancel leaves no running child; every child is terminal ──────────────


async def test_cancel_mid_fan_out_leaves_no_running_child():
    started: list[str] = []
    cancelled: list[str] = []

    async def run_child(child, run_id, allowed, actor):
        started.append(run_id)
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled.append(run_id)
            raise
        return {"status": "completed", "runId": run_id, "summary": "ok", "handles": []}

    task = asyncio.create_task(run_delegation(
        DelegationRequest(children=[_child("a"), _child("b")]),
        parent_run_id="p", parent_actor=_parent(), parent_allowed=None,
        depth=0, run_child=run_child, max_in_flight=2,
    ))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert started  # children had begun
    assert set(cancelled) == set(started)  # none left running


async def test_timeout_marks_the_child_timed_out():
    async def run_child(child, run_id, allowed, actor):
        await asyncio.sleep(5)
        return {"status": "completed", "runId": run_id, "summary": "ok", "handles": []}

    result = await run_delegation(
        DelegationRequest(children=[_child("a")]),
        parent_run_id="p", parent_actor=_parent(), parent_allowed=None,
        depth=0, run_child=run_child, child_timeout_s=1,
    )
    assert result.outcomes[0].status == "timed_out"
    assert result.budget.timedOut == 1


# ── events on the existing emitter ───────────────────────────────────────────


# ── the budget is REAL: usage is counted and the gate stops starting work ────


async def test_consumed_tokens_are_reported_from_the_children():
    async def run_child(child, run_id, allowed, actor):
        return {"status": "completed", "runId": run_id, "summary": "ok", "handles": [], "tokens": 1_000}

    result = await run_delegation(
        DelegationRequest(children=[_child("a"), _child("b")], token_budget=10_000),
        parent_run_id="p", parent_actor=_parent(), parent_allowed=None,
        depth=0, run_child=run_child,
    )
    assert result.budget.consumedTokens == 2_000
    assert result.budget.requestedTokens == 10_000


async def test_a_starved_child_is_not_started_and_is_refused_truthfully():
    async def run_child(child, run_id, allowed, actor):
        return {"status": "completed", "runId": run_id, "summary": "ok", "handles": [], "tokens": 2_500}

    result = await run_delegation(
        DelegationRequest(
            children=[_child("a"), _child("b"), _child("c")], token_budget=3_000,
        ),
        parent_run_id="p", parent_actor=_parent(), parent_allowed=None,
        depth=0, run_child=run_child, max_in_flight=1,
    )
    statuses = {o.child_index: o.status for o in result.outcomes}
    assert statuses[0] == "completed"
    assert statuses[1] == "refused" and statuses[2] == "refused"
    assert result.budget.consumedTokens == 2_500


async def test_total_deadline_ends_the_whole_delegation():
    async def run_child(child, run_id, allowed, actor):
        await asyncio.sleep(5)
        return {"status": "completed", "runId": run_id, "summary": "ok", "handles": []}

    result = await run_delegation(
        DelegationRequest(children=[_child("a"), _child("b")]),
        parent_run_id="p", parent_actor=_parent(), parent_allowed=None,
        depth=0, run_child=run_child, child_timeout_s=10, total_timeout_s=1,
        max_in_flight=1,
    )
    assert len(result.outcomes) == 2
    assert all(o.status in ("timed_out", "cancelled") for o in result.outcomes)


# ── the requested aggregation mode is honored ────────────────────────────────


def test_max_in_flight_is_operator_configurable_and_bounded(monkeypatch):
    from harness.delegation import _max_in_flight

    monkeypatch.setenv("HARNESS_DELEGATION_MAX_IN_FLIGHT", "2")
    assert _max_in_flight() == 2
    monkeypatch.setenv("HARNESS_DELEGATION_MAX_IN_FLIGHT", "99")
    assert _max_in_flight() == 8  # clamped — a desktop is not a stampede
    monkeypatch.setenv("HARNESS_DELEGATION_MAX_IN_FLIGHT", "0")
    assert _max_in_flight() == 1
    monkeypatch.setenv("HARNESS_DELEGATION_MAX_IN_FLIGHT", "not-a-number")
    assert _max_in_flight() == 4


def test_aggregate_modes_render_differently():
    from harness.delegation import ChildOutcome, DelegationResult, aggregate

    outcomes = [
        ChildOutcome(child_index=0, run_id="r0", status="completed",
                     summary="AAPL.", claimed=["Revenue rose."]),
        ChildOutcome(child_index=1, run_id="r1", status="completed",
                     summary="MSFT.", claimed=["Revenue rose.", "Margin fell."]),
    ]
    result = DelegationResult(delegationId="d", outcomes=outcomes)

    assert "- Revenue rose." in aggregate(result, "list")
    compared = aggregate(result, "compare")
    assert "Item 1:" in compared and "Item 2:" in compared
    merged = aggregate(result, "merge_claims")
    assert merged.count("- Revenue rose.") == 1  # de-duplicated across parts
    assert "- Margin fell." in merged


async def test_run_delegation_honors_the_requested_mode():
    result = await run_delegation(
        DelegationRequest(children=[_child("a"), _child("b")], aggregate="compare"),
        parent_run_id="p", parent_actor=_parent(), parent_allowed=None,
        depth=0, run_child=await _ok_runner([]),
    )
    assert "Item 1:" in result.aggregate


async def test_started_event_names_the_parts_so_the_ui_can_draw_rows():
    seen: list[tuple[str, dict]] = []

    async def on_event(event_type, data):
        seen.append((event_type, data))

    await run_delegation(
        DelegationRequest(children=[_child("a"), _child("b")]),
        parent_run_id="p", parent_actor=_parent(), parent_allowed=None,
        depth=0, run_child=await _ok_runner([]), on_event=on_event,
    )
    started = next(data for event, data in seen if event == "delegation.started")
    assert started["children"] == 2
    assert [agent["goal"] for agent in started["agents"]] == ["a", "b"]
    assert started["aggregate"] == "list"
    aggregated = next(data for event, data in seen if event == "delegation.aggregated")
    assert "tokens" in aggregated and "wallMs" in aggregated


async def test_events_are_emitted_for_the_delegation_lifecycle():
    seen: list[str] = []

    async def on_event(event_type, data):
        seen.append(event_type)

    await run_delegation(
        DelegationRequest(children=[_child("a"), _child("b")]),
        parent_run_id="p", parent_actor=_parent(), parent_allowed=None,
        depth=0, run_child=await _ok_runner([]), on_event=on_event,
    )
    assert "delegation.started" in seen
    assert seen[-1] == "delegation.aggregated"
    assert seen.count("delegation.child.started") == 2
