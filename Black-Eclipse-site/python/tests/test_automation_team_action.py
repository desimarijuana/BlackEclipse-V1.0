"""A desk: a saved `run_team` automation with its own TeamDefinition.

Covers the P0 seams: the dispatcher accepts `config.team` (and still the
Institution preset), validation refuses a broken desk at save time, and no team
member can submit an order.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.automation.dispatcher import Dispatcher
from harness.automation.model import AutomationDefinition
from harness.automation.validation import validate_automation
from harness.team.model import TeamDefinition
from harness.team.service import ORDER_SUBMIT_TOOLS

from team_helpers import make_host


def desk_team(*, trader_tools=None, review: bool = True) -> dict:
    return {
        "id": "desk-rates",
        "name": "Rates desk",
        "objective": "Decide whether the rates move justifies a position.",
        "members": [
            {
                "agentId": "desk-analyst",
                "label": "Analyst",
                "role": "analyst",
                "capabilities": ["analysis"],
                "tools": ["research_search", "read_run_output"],
                "instructions": "Build the evidence base. Cite source and as-of.",
            },
            {
                "agentId": "desk-trader",
                "label": "Trader",
                "role": "trader",
                "capabilities": ["proposal"],
                "tools": trader_tools or ["get_quote", "order_preview", "read_run_output"],
                "instructions": "Fully specified proposal. Never claim execution.",
            },
        ],
        "subtasks": [
            {
                "id": "analysis",
                "assignedAgentId": "desk-analyst",
                "objective": "Build the brief.",
                "expectedOutput": {"brief": "string"},
            },
            {
                "id": "proposal",
                "assignedAgentId": "desk-trader",
                "dependsOn": ["analysis"],
                "objective": "Propose the trade.",
                "expectedOutput": {"instrument": "string"},
            },
        ],
        "policy": {
            "delegationEnabled": True,
            "maxConcurrency": 2,
            "requireReview": review,
            "reviewStrictness": "STRICT",
        },
    }


def desk_automation(team: dict | None = None, **overrides) -> AutomationDefinition:
    action = {
        "type": "run_team",
        "objective": "Decide whether the rates move justifies a position.",
        "config": {"team": team if team is not None else desk_team()},
    }
    action.update(overrides.pop("action", {}))
    payload = {
        "id": "bot_desk",
        "name": "Rates desk",
        "version": 1,
        "state": "active",
        "trigger": {"type": "manual"},
        "action": action,
        "createdAt": "2025-01-01T00:00:00.000Z",
        "updatedAt": "2025-01-01T00:00:00.000Z",
    }
    payload.update(overrides)
    return AutomationDefinition(**payload)


def codes(issues) -> set[str]:
    return {issue.code for issue in issues if issue.severity == "error"}


class _FakeTeam:
    def __init__(self) -> None:
        self.team = None

    def validate(self, team):
        return []

    async def run(self, team, *, model_settings=None, **_):
        self.team = team
        return SimpleNamespace(
            id="teamrun_desk", root_run_id="root_desk",
            status=SimpleNamespace(value="COMPLETED"),
        )

    async def wait(self, run_id, **_):
        return SimpleNamespace(status=SimpleNamespace(value="COMPLETED"))

    async def finalize(self, run_id, **_):
        return {"status": "COMPLETED", "reviewOutcome": "APPROVED", "conflicts": []}

    def synthesize(self, run_id):
        return "DECISION: HOLD"


@pytest.mark.asyncio
async def test_desk_team_is_dispatched_from_config_not_the_preset():
    fake = _FakeTeam()
    dispatcher = Dispatcher(SimpleNamespace(team=fake))

    result = await dispatcher.dispatch(
        desk_automation(), execution_id="exec_desk", run_id="run_desk",
    )

    assert result.state == "completed"
    assert result.output == "DECISION: HOLD"
    assert result.detail["teamId"] == "desk-rates"
    assert result.detail["presetId"] is None
    assert fake.team is not None
    assert [s.id for s in fake.team.subtasks] == ["analysis", "proposal"]
    assert fake.team.members[1].agent_id == "desk-trader"


@pytest.mark.asyncio
async def test_an_objective_on_the_action_fills_an_empty_team_objective():
    fake = _FakeTeam()
    team = desk_team()
    team["objective"] = ""
    dispatcher = Dispatcher(SimpleNamespace(team=fake))

    await dispatcher.dispatch(
        desk_automation(team), execution_id="e", run_id="r",
    )

    assert fake.team.objective.startswith("Decide whether")


@pytest.mark.asyncio
async def test_a_malformed_desk_is_refused_before_the_runtime():
    class _RejectingTeam(_FakeTeam):
        def validate(self, team):
            return ["subtask 'analysis' depends on unknown subtask 'nope'"]

    fake = _RejectingTeam()
    dispatcher = Dispatcher(SimpleNamespace(team=fake))
    broken = desk_team()
    broken["subtasks"][0]["dependsOn"] = ["nope"]  # unknown dependency

    result = await dispatcher.dispatch(
        desk_automation(broken), execution_id="e", run_id="r",
    )

    assert result.state == "failed"
    assert result.error_class == "INVALID_CONFIGURATION"
    assert fake.team is None


@pytest.mark.asyncio
async def test_team_validate_refuses_an_order_submitting_member(tmp_path):
    host = make_host(tmp_path)
    team = TeamDefinition(**desk_team(trader_tools=["order_preview", "order_submit"]))

    errors = host.team.validate(team)

    assert any("order_submit" in error for error in errors)
    assert any("execution belongs to a trading bot" in error for error in errors)


@pytest.mark.asyncio
async def test_delegated_surface_strips_order_submit_when_inherited(tmp_path):
    from harness.a2a.model import AgentDefinition, AgentStatus

    host = make_host(tmp_path)
    host.a2a.registry.register_agent(AgentDefinition(
        id="desk-trader", name="Trader", role="trader",
        tools=["get_quote", "order_preview", "order_submit"],
        can_delegate=False, status=AgentStatus.ACTIVE,
    ))
    team = TeamDefinition(**desk_team(trader_tools=None))
    host.team._ensure_member_agent(team.members[1])

    tools = host.team._team_tools(team.members[1], allow_fanout=False)

    assert tools is not None
    assert not ORDER_SUBMIT_TOOLS.intersection(tools)
    assert "order_preview" in tools


def test_validation_accepts_a_valid_desk():
    issues = validate_automation(desk_automation())
    assert codes(issues) == set()


def test_validation_refuses_a_one_member_desk():
    team = desk_team()
    team["members"] = team["members"][:1]
    team["subtasks"] = team["subtasks"][:1]
    issues = validate_automation(desk_automation(team))
    assert "TEAM_TOO_SMALL" in codes(issues)


def test_validation_refuses_an_unroutable_stage():
    team = desk_team()
    team["subtasks"][1]["assignedAgentId"] = "not-a-member"
    issues = validate_automation(desk_automation(team))
    assert "TEAM_UNASSIGNED_STAGE" in codes(issues)


def test_validation_refuses_order_submit_and_warns_when_review_is_off():
    team = desk_team(trader_tools=["order_preview", "order_submit"], review=False)
    issues = validate_automation(desk_automation(team))
    assert "TEAM_ORDER_SUBMIT_REFUSED" in codes(issues)
    assert "TEAM_REVIEW_OFF" in {issue.code for issue in issues}

@pytest.mark.asyncio
async def test_a_declared_lead_is_labelled_unverified_and_only_on_starting_stages():
    class _Automations:
        def history(self, automation_id, limit=1):
            assert automation_id == "bot_news"
            return [{"output": "gold broke 2400", "finishedAt": "2026-11-18T09:00:00Z"}]

    fake = _FakeTeam()
    service = SimpleNamespace(team=fake, automation_service=lambda: _Automations())
    definition = desk_automation()
    definition.action.config["contextAutomationId"] = "bot_news"

    await Dispatcher(service).dispatch(definition, execution_id="e", run_id="r")

    lead = fake.team.subtasks[0].objective
    assert lead.startswith("UNVERIFIED LEAD")
    assert "bot_news" in lead
    assert "NOT evidence" in lead
    assert "gold broke 2400" in lead
    # A dependent stage does not carry the raw lead; it reads the memo by run id.
    assert "gold broke 2400" not in fake.team.subtasks[1].objective


@pytest.mark.asyncio
async def test_a_missing_lead_source_still_runs_and_says_so():
    class _Automations:
        def history(self, automation_id, limit=1):
            return []

    fake = _FakeTeam()
    service = SimpleNamespace(team=fake, automation_service=lambda: _Automations())
    definition = desk_automation()
    definition.action.config["contextAutomationId"] = "bot_news"

    result = await Dispatcher(service).dispatch(definition, execution_id="e", run_id="r")

    assert result.state == "completed"
    assert "no finished run" in fake.team.subtasks[0].objective.lower()


@pytest.mark.asyncio
async def test_bot_create_accepts_an_event_trigger(monkeypatch):
    from harness.automation import tools as automation_tools

    created: dict = {}

    class _Service:
        def create(self, payload, created_by="agent"):
            created.update(payload)
            return SimpleNamespace(public=lambda: {"id": "bot_new"})

    monkeypatch.setattr(automation_tools, "_service", _Service())
    ctx = SimpleNamespace(approvals=None, run_id="run_1")

    text, data = await automation_tools._create(
        {
            "objective": "watch filings",
            "triggerType": "event",
            "eventType": "filing.created",
            "eventFilter": {"ticker": "AAPL"},
        },
        ctx,
    )

    assert data["created"] is True
    assert created["trigger"]["type"] == "event"
    assert created["trigger"]["eventType"] == "filing.created"
    assert created["trigger"]["eventFilter"] == {"ticker": "AAPL"}

def test_team_validate_refuses_an_inherited_order_submit(tmp_path):
    host = make_host(tmp_path)
    team = TeamDefinition(
        id="t", name="T",
        members=[{"agentId": "eclipse-agent"}],  # no declared surface
        subtasks=[{"id": "s", "objective": "x", "assignedAgentId": "eclipse-agent"}],
    )
    errors = host.team.validate(team)
    assert any("inherits order-submitting tool" in error for error in errors)


def test_a_new_member_with_no_declared_tools_is_registered_without_order_submit(tmp_path):
    from harness.team.model import TeamMember
    from harness.tools import ToolDefinition

    host = make_host(tmp_path)
    host.registry.register(ToolDefinition(
        name="order_submit", description="submit", input_schema={"type": "object"},
        handler=lambda _a, _c: ("sent", {"ok": True}),
    ))
    host.registry.register(ToolDefinition(
        name="order_preview", description="preview", input_schema={"type": "object"},
        handler=lambda _a, _c: ("preview", {"ok": True}),
    ))

    host.team._ensure_member_agent(TeamMember(agent_id="desk-new", label="New"))

    agent = host.a2a.registry.get_agent("desk-new")
    assert agent.tools and "order_submit" not in agent.tools
    assert "order_preview" in agent.tools

@pytest.mark.asyncio
async def test_a_desk_runs_through_the_real_team_runtime(tmp_path):
    """The dispatcher path end to end: real TeamService, real task graph, only the
    model scripted. This is what `run_team` does for a saved desk."""
    import asyncio

    from team_helpers import completing_executor, drain, make_scheduler

    host = make_host(tmp_path)
    from harness.tasks.bootstrap import install_task_layer

    assert install_task_layer(host) is True
    dispatcher = Dispatcher(host)
    definition = desk_automation()

    run = asyncio.create_task(
        dispatcher.dispatch(definition, execution_id="exec_desk", run_id="run_desk")
    )
    scheduler = make_scheduler(host, completing_executor())
    for _ in range(200):
        await scheduler.tick()
        await scheduler.wait_idle()
        if run.done():
            break
        await asyncio.sleep(0.02)

    result = await asyncio.wait_for(run, timeout=20)

    assert result.state == "completed", result.error
    assert result.detail["teamId"] == "desk-rates"
    assert result.detail["teamStatus"] == "COMPLETED"
    assert result.output.startswith("Team: Rates desk")
    assert "analysis" in result.output and "proposal" in result.output

@pytest.mark.asyncio
async def test_a_desk_approval_is_matched_by_its_subtask_run(tmp_path):
    from harness.tasks.bootstrap import install_task_layer

    host = make_host(tmp_path)
    assert install_task_layer(host) is True
    run = await host.team.run(TeamDefinition(**desk_team()), autostart=False)
    host.tasks.start_task(run.subtask_task_ids["proposal"], run_id="run_subtask_proposal")

    class _Brokers:
        def list_approvals(self, status=None, limit=50):
            return [
                {"id": "ap_stage", "requestedByRunId": "run_subtask_proposal",
                 "actionSummary": "BUY 1 NVDA", "risk": "medium"},
                {"id": "ap_other", "requestedByRunId": "run_elsewhere",
                 "actionSummary": "SELL 1 AAPL", "risk": "medium"},
            ]

    dispatcher = Dispatcher(SimpleNamespace(team=host.team, tasks=host.tasks, brokers=_Brokers()))
    pending = dispatcher._pending_trade_approvals(run.root_run_id)

    assert [row["approvalId"] for row in pending] == ["ap_stage"]
    assert pending[0]["summary"] == "BUY 1 NVDA"
