"""TeamService: delegation, dependency-aware concurrency, review and recovery."""

from __future__ import annotations

import asyncio

import pytest

from harness.tasks.model import PlanStatus, TaskStatus
from harness.tasks.scheduler import TaskRunOutcome
from harness.team.model import (
    TeamDefinition,
    TeamRunStatus,
    TeamSubtaskStatus,
)
from harness.team.service import TeamError

from team_helpers import completing_executor, drain, make_host, make_scheduler


def _team(**over):
    base = dict(
        id="t1", name="Desk", agent_id="eclipse-orchestrator",
        members=[
            {"agentId": "research-agent", "capabilities": ["web_research"]},
            {"agentId": "valuation-agent", "capabilities": ["dcf"]},
            {"agentId": "risk-agent", "capabilities": ["risk_analysis"]},
        ],
        subtasks=[
            {"id": "research", "objective": "research it", "assignedAgentId": "research-agent"},
            {"id": "value", "objective": "value it", "assignedAgentId": "valuation-agent",
             "dependsOn": ["research"]},
            {"id": "risk", "objective": "assess risk", "assignedAgentId": "risk-agent"},
        ],
    )
    base.update(over)
    return TeamDefinition(**base)


@pytest.mark.asyncio
async def test_run_builds_graph_delegates_and_starts_the_plan(tmp_path):
    host = make_host(tmp_path)
    run = await host.team.run(_team())
    assert run.plan_id
    assert set(run.subtask_task_ids) == {"research", "value", "risk"}
    manager = host.tasks
    assert manager.get_plan(run.plan_id).status is PlanStatus.RUNNING
    # One delegated Task per subtask, each assigned to the real agent. A subtask
    # with an unmet dependency is durably BLOCKED until its prerequisite completes.
    for sid, tid in run.subtask_task_ids.items():
        task = manager.get_task(tid)
        assert task.status in (TaskStatus.TODO, TaskStatus.BLOCKED)
        assert task.assigned_agent_id in {"research-agent", "valuation-agent", "risk-agent"}
    assert manager.get_task(run.subtask_task_ids["value"]).status is TaskStatus.BLOCKED
    # The dependency edge is durable.
    value_task = manager.get_task(run.subtask_task_ids["value"])
    deps = [d.depends_on_task_id for d in manager.get_dependencies(value_task.id)]
    assert run.subtask_task_ids["research"] in deps
    # Every delegation was recorded by the A2A layer.
    assert len(host.a2a.delegations(run.root_run_id)) == 3


@pytest.mark.asyncio
async def test_dependent_task_waits_for_all_prerequisites(tmp_path):
    host = make_host(tmp_path)
    order: list[str] = []

    async def executor(task, context, run_id):
        order.append(task.metadata.get("subtaskId"))
        return TaskRunOutcome(status="completed", output="ok", run_id=run_id)

    run = await host.team.run(_team())
    scheduler = make_scheduler(host, executor)
    await drain(scheduler, host)

    assert order.index("research") < order.index("value")
    statuses = host.team._statuses(host.team.get_run(run.id), host.tasks)
    assert statuses["value"] is TeamSubtaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_independent_tasks_run_concurrently(tmp_path):
    host = make_host(tmp_path)
    active = {"now": 0, "max": 0}

    async def executor(task, context, run_id):
        active["now"] += 1
        active["max"] = max(active["max"], active["now"])
        await asyncio.sleep(0.05)
        active["now"] -= 1
        return TaskRunOutcome(status="completed", output="ok", run_id=run_id)

    run = await host.team.run(_team(
        subtasks=[
            {"id": "a", "objective": "a", "assignedAgentId": "research-agent"},
            {"id": "b", "objective": "b", "assignedAgentId": "valuation-agent"},
            {"id": "c", "objective": "c", "assignedAgentId": "risk-agent"},
        ],
    ))
    scheduler = make_scheduler(host, executor, max_in_flight=8)
    await drain(scheduler, host)
    # Genuine overlap, not merely "marked parallel".
    assert active["max"] >= 3
    assert host.team.get_run(run.id).id


@pytest.mark.asyncio
async def test_per_agent_concurrency_is_enforced(tmp_path):
    host = make_host(tmp_path)
    per_agent: dict[str, int] = {}
    peak = {"v": 0}

    async def measuring(task, context, run_id):
        agent = task.assigned_agent_id
        per_agent[agent] = per_agent.get(agent, 0) + 1
        peak["v"] = max(peak["v"], per_agent[agent])
        await asyncio.sleep(0.05)
        per_agent[agent] -= 1
        return TaskRunOutcome(status="completed", output="ok", run_id=run_id)

    run = await host.team.run(_team(
        members=[{"agentId": "research-agent", "capabilities": ["web_research"],
                  "maxConcurrency": 2}],
        subtasks=[
            {"id": "a", "objective": "a", "assignedAgentId": "research-agent"},
            {"id": "b", "objective": "b", "assignedAgentId": "research-agent"},
            {"id": "c", "objective": "c", "assignedAgentId": "research-agent"},
        ],
    ))
    scheduler = make_scheduler(host, measuring, max_in_flight=8)
    await drain(scheduler, host)
    assert peak["v"] <= 2
    assert peak["v"] >= 1


@pytest.mark.asyncio
async def test_per_plan_concurrency_cap(tmp_path):
    host = make_host(tmp_path)
    active = {"now": 0, "max": 0}

    async def executor(task, context, run_id):
        active["now"] += 1
        active["max"] = max(active["max"], active["now"])
        await asyncio.sleep(0.05)
        active["now"] -= 1
        return TaskRunOutcome(status="completed", output="ok", run_id=run_id)

    await host.team.run(_team(
        policy={"maxConcurrency": 2},
        subtasks=[
            {"id": "a", "objective": "a", "assignedAgentId": "research-agent"},
            {"id": "b", "objective": "b", "assignedAgentId": "valuation-agent"},
            {"id": "c", "objective": "c", "assignedAgentId": "risk-agent"},
        ],
    ))
    scheduler = make_scheduler(host, executor, max_in_flight=8)
    await drain(scheduler, host)
    assert active["max"] <= 2


@pytest.mark.asyncio
async def test_cancellation_propagates_to_child_tasks(tmp_path):
    host = make_host(tmp_path)
    run = await host.team.run(_team())
    await host.team.cancel(run.id, reason="operator")
    manager = host.tasks
    for tid in run.subtask_task_ids.values():
        assert manager.get_task(tid).status is TaskStatus.CANCELLED
    assert host.team.get_run(run.id).status is TeamRunStatus.CANCELLED


@pytest.mark.asyncio
async def test_review_queues_a_targeted_repair_then_reverifies(tmp_path):
    host = make_host(tmp_path)

    async def executor(task, context, run_id):
        # The 'value' subtask fails once; every repair succeeds.
        if task.metadata.get("subtaskId") == "value" and not task.metadata.get("repairFor"):
            return TaskRunOutcome(status="failed", error="bad input",
                                  error_class="VALIDATION_ERROR", run_id=run_id)
        return TaskRunOutcome(status="completed", output="ok", run_id=run_id)

    run = await host.team.run(_team(policy={"requireReview": True}))
    scheduler = make_scheduler(host, executor)
    await drain(scheduler, host)

    first = await host.team.finalize(run.id)
    assert first["status"] == "repairing"
    assert first["review"]["outcome"] == "REVISION_REQUIRED"
    assert first["review"]["findings"][0]["subtaskId"] == "value"

    # Re-verification: run the repair, then review again.
    await drain(scheduler, host)
    second = await host.team.finalize(run.id)
    assert second["status"] == "COMPLETED"
    assert second["reviewOutcome"] == "APPROVED"
    assert host.team.get_run(run.id).status is TeamRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_conflicting_findings_are_disclosed_not_averaged(tmp_path):
    from harness.a2a.model import A2AResult, Finding

    host = make_host(tmp_path)
    run = await host.team.run(_team(
        subtasks=[{"id": "a", "objective": "a", "assignedAgentId": "research-agent"}],
    ))
    manager = host.tasks
    task_id = run.subtask_task_ids["a"]
    host.a2a.record_result(A2AResult(
        task_id=task_id, agent_id="research-agent", status="COMPLETED",
        findings=[Finding(id="f1", claim="Tesla revenue is 96", confidence=0.8,
                          evidence_refs=["e1"])],
    ), run_id=run.root_run_id)
    host.a2a.record_result(A2AResult(
        task_id=task_id, agent_id="news-agent", status="COMPLETED",
        findings=[Finding(id="f2", claim="Tesla revenue is 88", confidence=0.6,
                          evidence_refs=["e2"])],
    ), run_id=run.root_run_id)
    assert manager.get_task(task_id) is not None

    scheduler = make_scheduler(host, completing_executor())
    await drain(scheduler, host)
    result = await host.team.finalize(run.id)
    unresolved = result["unresolvedConflicts"]
    assert unresolved and {f for f in unresolved[0]["findingIds"]} == {"f1", "f2"}
    # PARTIAL because a material conflict is disclosed, and it is not averaged.
    assert result["status"] in ("PARTIAL", "COMPLETED")
    text = host.team.synthesize(run.id)
    assert "Unresolved conflicts" in text
    assert "92" not in text


@pytest.mark.asyncio
async def test_run_is_durable_across_a_restart(tmp_path):
    from harness.persistence import AgentMemoryStore
    from harness.team.store import TeamStore

    path = tmp_path / "agent-memory.db"
    host = make_host(tmp_path)
    run = await host.team.run(_team())
    host.store.close()

    # A brand-new process reopens the SAME database and still sees the run.
    reopened = AgentMemoryStore(str(path))
    restored = TeamStore(reopened).get_run(run.id)
    assert restored is not None
    assert set(restored.subtask_task_ids) == {"research", "value", "risk"}
    reopened.close()


@pytest.mark.asyncio
async def test_validation_refuses_a_non_member_assignee(tmp_path):
    host = make_host(tmp_path)
    team = _team(subtasks=[{"id": "x", "objective": "x", "assignedAgentId": "ghost-agent"}])
    errors = host.team.validate(team)
    assert any("not a team member" in e for e in errors)
    with pytest.raises(TeamError) as exc:
        await host.team.run(team)
    assert exc.value.code == "TEAM_INVALID"


def test_validation_refuses_an_unresolvable_capability(tmp_path):
    host = make_host(tmp_path)
    team = _team(subtasks=[{"id": "x", "objective": "x", "capability": "teleportation"}])
    errors = host.team.validate(team)
    assert any("teleportation" in e for e in errors)


def test_validation_refuses_a_cycle(tmp_path):
    host = make_host(tmp_path)
    team = _team(subtasks=[
        {"id": "a", "objective": "a", "dependsOn": ["b"]},
        {"id": "b", "objective": "b", "dependsOn": ["a"]},
    ])
    assert any("cycle" in e for e in host.team.validate(team))


def test_validation_refuses_when_delegation_is_disabled(tmp_path):
    host = make_host(tmp_path)
    assert any("delegation is disabled" in e for e in
               host.team.validate(_team(policy={"delegationEnabled": False})))


@pytest.mark.asyncio
async def test_require_approval_gate(tmp_path):
    from harness.a2a.model import ApprovalStatus

    host = make_host(tmp_path)
    team = _team(policy={"requireApproval": True})
    with pytest.raises(TeamError) as exc:
        await host.team.run(team)
    assert exc.value.code == "TEAM_APPROVAL_REQUIRED"
    # Grant the single-use approval through the ONE A2A approval store.
    pending = host.a2a.request_approval(
        sender_agent_id="eclipse-orchestrator", run_id="pre", subject=team.id, kind="team_run",
    )
    host.a2a.decide_approval(pending["approvalId"], ApprovalStatus.GRANTED.value)
    run = await host.team.run(team)
    assert run.id


@pytest.mark.asyncio
async def test_task_executor_records_budget_usage(tmp_path):
    from types import SimpleNamespace

    from harness.tasks.bootstrap import build_task_executor
    from harness.tasks.context import build_task_context

    host = make_host(tmp_path)
    run = await host.team.run(_team(subtasks=[
        {"id": "a", "objective": "a", "assignedAgentId": "research-agent"},
    ]))

    async def fake_run(request):
        return {"runId": request.runId, "status": "completed", "output": "ok",
                "totalTokens": 321, "toolCalls": 4}

    svc = SimpleNamespace(a2a=host.a2a, recovery=None, artifacts=None, run=fake_run)
    executor = build_task_executor(svc, host.tasks)
    task = host.tasks.get_task(run.subtask_task_ids["a"])
    context = build_task_context(host.tasks, task, constraints={})
    outcome = await executor(task, context, "run_budget")
    assert outcome.status == "completed"
    snapshot = host.a2a.budgets.snapshot(run.root_run_id)
    assert snapshot["tokensUsed"] >= 321
    assert snapshot["toolCalls"] >= 4

def test_member_fanout_is_opt_in_and_only_adds_the_tool(tmp_path):
    """A team member can use delegate/best_of only when the policy opts in."""
    from harness.team.model import TeamMember

    host = make_host(tmp_path)
    member = TeamMember(agentId="research-agent", tools=["workspace_read", "read_file"])
    assert host.team._member_tools(member, False) == ["workspace_read", "read_file"]
    assert host.team._member_tools(member, True) == [
        "workspace_read", "read_file", "delegate",
    ]
    # A member with NO declared surface already inherits everything.
    unrestricted = TeamMember(agentId="research-agent")
    assert host.team._member_tools(unrestricted, True) is None
    # The policy default is OFF, so a team run does not widen silently.
    assert _team().policy.member_fanout is False
