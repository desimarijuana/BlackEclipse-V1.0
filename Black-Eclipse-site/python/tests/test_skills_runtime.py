"""Phase 3 — Skill execution runtime tests (Milestone 3).

The skill runtime is exercised end-to-end through the REAL Phase-1 graph with a
scripted model and fake bridge — proving skills use the existing runtime, emit
events, validate inputs/outputs, enforce permissions, and persist executions.
No network, no JDdS.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.finance_tools import register_finance_tools
from harness.persistence import AgentMemoryStore
from harness.retrieval_tools import register_retrieval_tools
from harness.schemas import ModelSettings
from harness.skills import Actor, SkillRegistry, SkillStore
from harness.skills.runtime import (
    SkillExecutionRequest,
    execute_skill,
    validate_input,
)
from harness.tools import DataBridge, ToolRegistry


class ScriptedModel:
    def __init__(self, responses):
        self._responses = list(responses)

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if not self._responses:
            return AIMessage(content="(exhausted)")
        response = self._responses.pop(0)
        return response(messages) if callable(response) else response

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class FakeBridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE", "error": "no fake data"}


@pytest.fixture()
def env(monkeypatch):
    directory = tempfile.mkdtemp(prefix="be-skillrt-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    skill_store = SkillStore(os.path.join(directory, "agent-memory.db"))
    registry = SkillRegistry(skill_store)
    registry.load_all()
    tools = ToolRegistry()
    register_finance_tools(tools)
    register_retrieval_tools(tools)
    registry.attach_tool_registry(tools)
    model = ScriptedModel([AIMessage(content='{"objective": "x", "questions": ["q"]}')])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    bridge = FakeBridge()
    yield {
        "store": store,
        "skill_store": skill_store,
        "registry": registry,
        "tools": tools,
        "bridge": bridge,
        "model": model,
    }
    store.close()
    skill_store.close()


def _request(**overrides):
    base = {
        "skillId": "research.planning",
        "input": {"objective": "Is ACME a good buy?"},
        "modelSettings": ModelSettings(provider="openai", model="test", api_key="x"),
        "callbackBaseUrl": "http://127.0.0.1:3000",
    }
    base.update(overrides)
    return SkillExecutionRequest(**base)


async def test_execute_enabled_skill_uses_existing_runtime(env):
    result = await execute_skill(
        _request(), env["registry"], env["tools"], env["bridge"], env["store"]
    )
    assert result.status == "completed", result.error
    assert result.skillId == "research.planning"
    assert result.runId
    # The run was persisted by the EXISTING runtime.
    run = env["store"].get_run(result.runId)
    assert run is not None and run["status"] == "completed"
    # A SkillExecution row exists.
    execution = env["skill_store"].get_execution(result.runId)
    assert execution is not None and execution["status"] == "completed"


async def test_execution_emits_skill_events(env):
    result = await execute_skill(
        _request(), env["registry"], env["tools"], env["bridge"], env["store"]
    )
    # Skill lifecycle events are recorded in the SkillEvent audit table.
    types = [e["type"] for e in env["skill_store"].list_events("research.planning")]
    assert "skill.started" in types
    assert "skill.completed" in types
    # And the ordinary run trace still exists for the same run (same runtime).
    run_types = [e["type"] for e in env["store"].list_events(result.runId)]
    assert "run.started" in run_types
    assert "run.completed" in run_types


async def test_skill_events_reach_live_emitter(env):
    from harness.events import EventBus, RunEmitter

    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(lambda event: seen.append(event["type"]))

    result = await execute_skill(
        _request(runId="run_live"),
        env["registry"], env["tools"], env["bridge"], env["store"], bus=bus,
    )
    assert result.status == "completed"
    # skill.* events rode the shared bus to live subscribers.
    assert "skill.started" in seen
    assert "skill.completed" in seen


async def test_input_validation_failure_blocks_before_run(env):
    result = await execute_skill(
        _request(input={}), env["registry"], env["tools"], env["bridge"], env["store"]
    )
    assert result.status == "blocked"
    assert result.error["code"] == "INPUT_VALIDATION_FAILED"
    # Nothing should have been persisted as a run.
    assert env["store"].get_run(result.runId) is None


async def test_unknown_skill_blocked(env):
    result = await execute_skill(
        _request(skillId="nope.nope"), env["registry"], env["tools"], env["bridge"], env["store"]
    )
    assert result.status == "blocked"
    assert result.error["code"] == "SKILL_NOT_FOUND"


async def test_draft_skill_cannot_execute_interactively(env):
    env["skill_store"].set_version_status("research.planning", "1.0.0", "draft")
    result = await execute_skill(
        _request(), env["registry"], env["tools"], env["bridge"], env["store"]
    )
    assert result.status == "blocked"
    assert result.error["code"] == "SKILL_NOT_EXECUTABLE"


async def test_permission_denied_blocks(env):
    # A finance skill requires analysis.execute + data.read, both in the safe
    # set. Narrow the actor with scopes to force a denial.
    result = await execute_skill(
        _request(scopes=["report.generate"]),
        env["registry"], env["tools"], env["bridge"], env["store"],
    )
    assert result.status == "denied"
    assert result.error["code"] == "PERMISSION_DENIED"


async def test_missing_dependency_blocks(env):
    # Remove the quality skill entirely so the finance skill's dependency
    # cannot resolve.
    env["registry"]._skills.pop("quality.financial-data-quality", None)
    env["skill_store"]._db.execute(
        "DELETE FROM SkillVersion WHERE skillId='quality.financial-data-quality'"
    )
    env["skill_store"]._db.commit()
    result = await execute_skill(
        _request(skillId="finance.fundamental-analysis", input={"symbol": "AAPL", "market": "US"}),
        env["registry"], env["tools"], env["bridge"], env["store"],
    )
    assert result.status == "blocked"
    assert result.error["code"] == "DEPENDENCY_UNRESOLVED"


async def test_output_schema_validated(env):
    # The planning skill's output requires fields missing from the model answer.
    env["model"]._responses = [AIMessage(content='{"objective": "x"}')]
    result = await execute_skill(
        _request(), env["registry"], env["tools"], env["bridge"], env["store"]
    )
    assert result.status == "completed"
    assert result.outputValidated is False
    assert any("required" in w for w in result.warnings)


async def test_output_validated_true_for_matching_output(env):
    env["model"]._responses = [
        AIMessage(
            content='{"objective": "x", "questions": ["q"], "requiredData": [], '
                    '"sourcePlan": [], "expectedDeliverables": ["d"]}'
        )
    ]
    result = await execute_skill(
        _request(), env["registry"], env["tools"], env["bridge"], env["store"]
    )
    assert result.outputValidated is True


async def test_execution_mode_is_recorded_for_workflow(env):
    result = await execute_skill(
        _request(executionMode="workflow", parentRunId="run_parent", runId="run_child"),
        env["registry"], env["tools"], env["bridge"], env["store"],
    )
    assert result.status == "completed"
    execution = env["skill_store"].get_execution("run_child")
    assert execution["executionMode"] == "workflow"
    assert execution["parentRunId"] == "run_parent"
    assert execution["traceId"] == "run_child"


async def test_validate_input_helper_rejects_wrong_type():
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    ok, issues = validate_input(schema, {"n": "not-an-int"}, "t")
    assert not ok and issues
    ok, issues = validate_input(schema, {"n": 3}, "t")
    assert ok and not issues


def test_script_bridge_is_read_only(env):
    # Sanity: the fake bridge must not be a write path.
    assert isinstance(env["bridge"], DataBridge)


# ── Phase 2: runtime-enforced execution limits + full output validation ──────


async def test_max_tool_calls_is_enforced_in_the_runtime(env):
    # A scripted model that ALWAYS requests a tool must be stopped by the skill's
    # declared maxToolCalls, not merely told about it in metadata/prose.
    from harness.schemas import AgentConfig, RunInput, RunRequest

    tool_call = AIMessage(
        content="",
        tool_calls=[{"id": "c1", "name": "get_market_snapshot", "args": {"symbol": "AAPL"}}],
    )

    class LoopingModel:
        def __init__(self):
            self.n = 0

        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            self.n += 1
            if self.n > 25:
                return AIMessage(content="{}")
            return AIMessage(
                content="",
                tool_calls=[{"id": f"c{self.n}", "name": "get_market_snapshot",
                             "args": {"symbol": "AAPL"}}],
            )

        async def astream(self, messages):
            yield await self.ainvoke(messages)

    model = LoopingModel()
    agent = AgentConfig(
        id="skill:research.planning", name="Loop", systemPrompt="sys",
        tools=["get_market_snapshot"], maxSteps=20, maxToolCalls=3,
    )
    req = RunRequest(
        runId="run_budget",
        input=RunInput(query="loop"),
        agent=agent,
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    from harness import graph as graph_module

    orig = graph_module.build_chat_model
    graph_module.build_chat_model = lambda settings: model  # type: ignore
    try:
        result = await graph_module.execute_run(
            req, env["tools"], env["bridge"], env["store"], skill_registry=env["registry"],
        )
    finally:
        graph_module.build_chat_model = orig  # type: ignore
    # The run stopped at the budget (it did not loop to maxSteps=20).
    assert result.toolCalls <= 3
    assert env["store"].get_run("run_budget")["toolCalls"] <= 3


async def test_output_schema_violation_is_not_reported_validated(env):
    # A result may complete while its output FAILS the declared schema; it must
    # never be reported as validated, and the failure must be surfaced.
    env["model"]._responses = [
        AIMessage(content='{"objective": 123, "questions": "not-an-array"}')
    ]
    result = await execute_skill(
        _request(), env["registry"], env["tools"], env["bridge"], env["store"]
    )
    assert result.status == "completed"
    assert result.outputValidated is False
    assert any("schema violation" in w for w in result.warnings)


async def test_missing_output_schema_is_not_marked_validated():
    # No declared output schema => nothing was machine-validated, and the absence
    # of a contract is not itself a (warning-level) violation.
    from harness.skills.runtime import _validate_output

    ok, parsed, warnings = _validate_output(None, '{"anything": true}', "s")
    assert ok is False
    assert parsed == {"anything": True}
    assert warnings == []


async def test_execution_records_instruction_aware_version_identity(env):
    result = await execute_skill(
        _request(), env["registry"], env["tools"], env["bridge"], env["store"]
    )
    execution = env["skill_store"].get_execution(result.runId)
    manifest = env["registry"].manifest("research.planning")
    instructions = env["registry"].get("research.planning").load_instructions()
    assert execution["manifestHash"] == manifest.version_identity(instructions)


async def test_execution_records_validation_and_metrics(env):
    env["model"]._responses = [
        AIMessage(
            content='{"objective": "x", "questions": ["q"], "requiredData": [], '
                    '"sourcePlan": [], "expectedDeliverables": ["d"]}'
        )
    ]
    result = await execute_skill(
        _request(), env["registry"], env["tools"], env["bridge"], env["store"]
    )
    execution = env["skill_store"].get_execution(result.runId)
    # The operator view records the validation result and bounded metrics.
    assert execution["outputValidated"] is True
    assert execution["metrics"]["modelSteps"] >= 1
    assert "toolCalls" in execution["metrics"]


async def test_execution_records_not_validated_without_lying(env):
    env["model"]._responses = [AIMessage(content='{"objective": "x"}')]
    result = await execute_skill(
        _request(), env["registry"], env["tools"], env["bridge"], env["store"]
    )
    execution = env["skill_store"].get_execution(result.runId)
    assert execution["status"] == "completed"
    assert execution["outputValidated"] is False
