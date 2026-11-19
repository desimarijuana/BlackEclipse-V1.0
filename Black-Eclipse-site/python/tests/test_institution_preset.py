"""The Institution preset: cast, graph and the scheduled `run_team` dispatch."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.automation.dispatcher import Dispatcher
from harness.automation.model import AutomationDefinition
from harness.institution.cast import ROLES
from harness.institution.preset import (
    agent_configs,
    bot_specs,
    build_team,
    descriptor,
)
from harness.institution.tools import read_run_output
from harness.team.model import TeamDefinition
from harness.team.service import TeamService

from team_helpers import make_host, make_scheduler, completing_executor, drain


def test_cast_is_unique_and_complete():
    ids = [role.agent_id for role in ROLES]
    assert len(ids) == len(set(ids)) == 7
    assert {role.stage for role in ROLES} == {"analysis", "debate", "trader", "risk", "pm"}
    assert all(role.tools for role in ROLES)


def test_bootstrap_registers_the_seats_and_the_handoff_tool(tmp_path):
    from harness.agents import AGENT_PRESETS
    from harness.institution.bootstrap import install_institution_layer

    host = make_host(tmp_path)
    assert install_institution_layer(host) is True
    assert host.institution is not None
    assert host.registry.get("read_run_output") is not None
    for role in ROLES:
        assert role.agent_id in AGENT_PRESETS
        assert host.a2a.registry.get_agent(role.agent_id) is not None


def test_build_team_is_a_valid_committee_graph(tmp_path):
    host = make_host(tmp_path)
    team = build_team("Evaluate NVDA", universe="NVDA", horizon="6 months")

    assert isinstance(team, TeamDefinition)
    assert host.team.validate(team) == []
    assert [s.id for s in team.subtasks] == [
        "analysis", "bull_case", "bear_case", "debate",
        "trade_proposal", "risk_review", "decision",
    ]
    assert team.subtasks[3].depends_on == ["analysis", "bull_case", "bear_case"]
    # Every downstream stage lists the memos it must read DIRECTLY (the task
    # context only renders direct prerequisites, by design).
    assert team.subtasks[4].depends_on == ["analysis", "debate"]
    assert team.subtasks[5].depends_on == ["analysis", "debate", "trade_proposal"]
    assert team.subtasks[6].depends_on == ["analysis", "debate", "trade_proposal", "risk_review"]
    assert team.metadata["presetId"] == "institution"
    assert team.policy.require_review is True


def test_agent_configs_and_bot_specs_share_one_identity():
    configs = {c["id"] for c in agent_configs()}
    bots = {b["agentId"] for b in bot_specs()}
    assert configs == bots == {role.agent_id for role in ROLES}
    assert descriptor()["stages"] == ["analysis", "debate", "trader", "risk", "pm"]


async def test_committee_runs_through_the_task_graph(tmp_path):
    host = make_host(tmp_path)
    run = await host.team.run(build_team("Evaluate a position"))
    scheduler = make_scheduler(host, completing_executor())
    await drain(scheduler, host)
    statuses = host.team._statuses(host.team.get_run(run.id), host.tasks)
    failures = {
        sid: (status.value, host.tasks.get_task(tid).error)
        for sid, tid in run.subtask_task_ids.items()
        for status in [statuses[sid]]
        if status.value != "COMPLETED"
    }
    assert not failures, failures


async def test_read_run_output_returns_the_prerequisite_memo():
    ctx = SimpleNamespace(
        memory_store=SimpleNamespace(get_run=lambda rid: {
            "status": "completed", "output": f"memo for {rid}",
        }),
    )
    text, data = await read_run_output({"runId": "run_123"}, ctx)
    assert data["ok"] is True
    assert "memo for run_123" in text

    missing, data2 = await read_run_output({"runId": "nope"}, SimpleNamespace(
        memory_store=SimpleNamespace(get_run=lambda rid: None),
    ))
    assert data2["code"] == "RUN_NOT_FOUND"
    assert "No run" in missing


class _FakeTeam:
    def __init__(self) -> None:
        self.team = None
        self.model_settings = None

    def validate(self, team):
        return []

    async def run(self, team, *, model_settings=None, **_):
        self.team = team
        self.model_settings = model_settings
        return SimpleNamespace(
            id="teamrun_1", root_run_id="root_1",
            status=SimpleNamespace(value="COMPLETED"),
        )

    async def wait(self, run_id, **_):
        return SimpleNamespace(status=SimpleNamespace(value="COMPLETED"))

    async def finalize(self, run_id, **_):
        return {"status": "COMPLETED", "reviewOutcome": "APPROVED", "conflicts": []}

    def synthesize(self, run_id):
        return "FINAL DECISION: HOLD"


@pytest.mark.asyncio
async def test_run_team_action_dispatches_the_preset():
    fake = _FakeTeam()
    service = SimpleNamespace(team=fake)
    dispatcher = Dispatcher(service)
    definition = AutomationDefinition(
        id="bot_inst", name="Institution PM", version=1, state="active",
        trigger={"type": "manual"},
        action={
            "type": "run_team", "objective": "Evaluate NVDA",
            "config": {"presetId": "institution", "horizon": "6 months"},
        },
        createdAt="2025-01-01T00:00:00.000Z",
        updatedAt="2025-01-01T00:00:00.000Z",
    )

    result = await dispatcher.dispatch(
        definition, execution_id="exec_1", run_id="run_1",
    )

    assert result.state == "completed"
    assert result.run_id == "root_1"
    assert result.output == "FINAL DECISION: HOLD"
    assert result.detail["teamRunId"] == "teamrun_1"
    assert result.detail["presetId"] == "institution"
    assert fake.team is not None
    assert len(fake.team.members) == 7
    assert fake.team.subtasks[-1].id == "decision"


@pytest.mark.asyncio
async def test_run_team_action_refuses_an_unknown_preset():
    service = SimpleNamespace(team=_FakeTeam())
    dispatcher = Dispatcher(service)
    definition = AutomationDefinition(
        id="bot_inst", name="Institution PM", version=1, state="active",
        trigger={"type": "manual"},
        action={"type": "run_team", "objective": "x", "config": {"presetId": "other"}},
        createdAt="2025-01-01T00:00:00.000Z",
        updatedAt="2025-01-01T00:00:00.000Z",
    )
    result = await dispatcher.dispatch(definition, execution_id="e", run_id="r")
    assert result.state == "failed"
    assert result.error_class == "INVALID_CONFIGURATION"
