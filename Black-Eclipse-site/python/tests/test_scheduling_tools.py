"""Phase 17 scheduling tools — real catalogue → create-disabled → run-refusal.

The scheduling tools are thin wrappers over the ONE AutomationService: the chat
agent may set up a recurring finance job from a FIXED catalogue, always saved
switched off, and may run an already-switched-on job once. The operator's master
switch (`agent_scheduling_enabled`, default OFF) removes the whole surface.

Hermetic: this module builds its own isolated stores and services (no shared app
boot), so it is immune to the process-wide lifespan's connection lifecycle.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

TOOL_NAMES = ("job_list", "job_describe_template", "job_create", "job_run_now")


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """An isolated automation service + memory policy + tool context."""
    from harness.persistence import AgentMemoryStore
    from harness.automation.store import AutomationStore
    from harness.automation.engine import AutomationEngine
    from harness.automation.service import AutomationService
    from harness.automation import tools as bot_tools
    from harness.eclipse_memory.service import EclipseMemoryService
    from harness.eclipse_memory.store import EclipseMemoryStore
    from harness.tools import ToolContext, ToolRegistry

    class _Host:
        """The minimal host surface the automation service reads lazily."""

        registry = ToolRegistry()
        skill_registry = None

        def workflow_store(self):  # pragma: no cover - validation catches it
            raise RuntimeError("no workflow store in this fixture")

    agent_store = AgentMemoryStore(os.path.join(str(tmp_path), "agent-memory.db"))
    automation_store = AutomationStore(agent_store)
    host = _Host()
    automation = AutomationService(host, automation_store, AutomationEngine(host, automation_store))

    memory = EclipseMemoryService(EclipseMemoryStore(os.path.join(str(tmp_path), "eclipse-memory.db")))

    previous = bot_tools.get_automation_service()
    bot_tools.set_automation_service(automation)

    ctx = ToolContext(run_id="test-scheduling", log=lambda *a, **k: None)
    ctx.memory_service = memory
    try:
        yield automation, memory, ctx
    finally:
        bot_tools.set_automation_service(previous)
        memory.close()
        agent_store.close()


def _set_switch(memory, on: bool) -> None:
    memory.policy.set("agent_scheduling_enabled", on)


def test_catalogue_is_consistent_and_has_no_code_or_deploy_shapes():
    from harness.automation.catalogue import SHAPES, catalogue_issues

    assert catalogue_issues() == []
    for shape in SHAPES.values():
        assert "deploy" not in shape.template_id
        assert "build" not in shape.template_id


def test_tools_register_idempotently():
    from harness.automation.scheduling_tools import register_scheduling_tools
    from harness.tools import ToolRegistry

    registry = ToolRegistry()
    assert set(register_scheduling_tools(registry)) == set(TOOL_NAMES)
    assert register_scheduling_tools(registry) == []


def test_switch_off_removes_the_whole_surface():
    from harness.agents import AGENT_PRESETS, CHAT_CODE_TOOLS
    from harness.automation.scheduling_tools import register_scheduling_tools
    from harness.graph import resolve_surface
    from harness.tools import ToolRegistry

    registry = ToolRegistry()
    register_scheduling_tools(registry)
    agent = AGENT_PRESETS["eclipse-agent"]

    allowed_off, _ = resolve_surface(agent, registry, {"agent_scheduling_enabled": False})
    assert allowed_off is not None
    for name in TOOL_NAMES:
        assert name not in allowed_off, name

    allowed_on, _ = resolve_surface(agent, registry, {"agent_scheduling_enabled": True})
    assert allowed_on is not None
    for name in TOOL_NAMES:
        assert name in allowed_on, name

    # The chat code profile carries the same four tools (a coding turn keeps the
    # scheduling surface).
    for name in TOOL_NAMES:
        assert name in CHAT_CODE_TOOLS, name


def test_create_is_always_disabled_tagged_and_run_refused(env):
    automation, memory, ctx = env
    from harness.automation import scheduling_tools as st

    _set_switch(memory, True)
    _, data = run(st._create(
        {"shapeId": "morning_brief", "params": {"tickers": "AAPL, MSFT"}}, ctx,
    ))
    assert data["created"] is True, data
    assert data["state"] == "disabled"
    job_id = data["jobId"]

    job = automation.get(job_id)
    assert job is not None
    assert job.state == "disabled"
    assert st.JOB_TAG in job.tags
    assert "morning_brief" in job.tags
    assert job.next_run_at is None

    _, listed = run(st._list({}, ctx))
    assert any(j["id"] == job_id and j["switchedOn"] is False for j in listed["jobs"])

    _, refused = run(st._run_now({"jobId": job_id}, ctx))
    assert refused["started"] is False
    assert refused["code"] == "NOT_ACTIVE"

    assert automation.delete(job_id) is True


def test_create_refused_when_the_switch_is_off(env):
    automation, memory, ctx = env
    from harness.automation import scheduling_tools as st

    _set_switch(memory, False)
    _, data = run(st._create({"shapeId": "morning_brief", "params": {"tickers": "AAPL"}}, ctx))
    assert data["created"] is False
    assert data["code"] == "AGENT_SCHEDULING_OFF"


def test_shape_and_parameter_refusals(env):
    automation, memory, ctx = env
    from harness.automation import scheduling_tools as st

    _set_switch(memory, True)
    _, unknown = run(st._create({"shapeId": "make_me_rich", "params": {}}, ctx))
    assert unknown["code"] == "UNKNOWN_SHAPE"

    _, missing = run(st._create({"shapeId": "morning_brief", "params": {}}, ctx))
    assert missing["code"] == "MISSING_PARAM"

    _, extra = run(st._create(
        {"shapeId": "morning_brief", "params": {"tickers": "AAPL", "sneaky": "x"}}, ctx,
    ))
    assert extra["code"] == "UNKNOWN_PARAM"


def test_describe_template_names_the_answers(env):
    automation, memory, ctx = env
    from harness.automation import scheduling_tools as st

    _set_switch(memory, True)
    _, view = run(st._describe_template({"shapeId": "morning_brief"}, ctx))
    assert view["id"] == "morning_brief"
    assert view["requiredParams"] == ["tickers"]
    assert view["exampleParams"].get("tickers")

    _, unknown = run(st._describe_template({"shapeId": "nope"}, ctx))
    assert unknown["code"] == "UNKNOWN_SHAPE"
    assert "morning_brief" in unknown["available"]


def test_run_now_of_a_bot_is_refused(env):
    automation, memory, ctx = env
    from harness.automation import scheduling_tools as st
    from harness.automation import tools as bot_tools

    _set_switch(memory, True)
    _, made = run(bot_tools._create(
        {"name": "Not a job", "objective": "say hi", "triggerType": "manual", "state": "draft"},
        ctx,
    ))
    assert made["created"] is True, made
    bot_id = made["bot"]["id"]
    _, refused = run(st._run_now({"jobId": bot_id}, ctx))
    assert refused["started"] is False
    assert refused["code"] == "NOT_A_JOB"
    assert automation.delete(bot_id) is True


def test_unattended_report_contract():
    from harness.automation.delivery import OUTCOME_FIRST_LINE, render_run_report
    from harness.code.policy import PLAIN_LANGUAGE_DENYLIST

    class _Definition:
        name = "report-contract"

    completed = render_run_report(_Definition(), "completed", "The answer body.")
    assert completed.splitlines()[0] == OUTCOME_FIRST_LINE["completed"]
    assert "The answer body." in completed

    limited = render_run_report(
        _Definition(), "failed", "Partial result only.",
        limits=["A source was stale, so its numbers are from yesterday."],
    )
    assert limited.splitlines()[0] == OUTCOME_FIRST_LINE["failed"]
    assert "A source was stale" in limited, limited

    empty = render_run_report(_Definition(), "completed", "")
    assert "produced no result" in empty

    lowered = limited.lower()
    for word in PLAIN_LANGUAGE_DENYLIST:
        assert word not in lowered, f"mechanism word {word!r} leaked into a delivered report"
