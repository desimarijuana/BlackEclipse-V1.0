"""Phase 1: idempotent resume — no duplicate tool execution, exact terminal.

Assertions are on PERSISTED ROWS and structured error codes, never on model
prose. The model is a scripted fake; the data bridge counts real tool fetches.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.run_lineage import RunLineage
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolRegistry, ToolDefinition
from harness.finance_tools import register_finance_tools


class ScriptedModel:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if not self._responses:
            return AIMessage(content="done")
        return self._responses.pop(0)

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class ProcessKilled(BaseException):
    """A non-`Exception` error, like a signal/interpreter death.

    The graph's recovery paths catch `Exception` only, so this propagates and the
    run row is left `running` — faithfully modelling a process killed mid-run.
    """


class KillModel:
    """Step 1 emits a tool call; step 2 raises a `BaseException` (a hard kill)."""

    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[{"id": "c1", "name": "counting_tool", "args": {"x": 1}}],
            )
        raise ProcessKilled("simulated process kill")

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class ResumedModel:
    """After a crash, the resumed run continues: step 2 answers with no tools."""

    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        return AIMessage(content="resumed answer")

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class CountingBridge(DataBridge):
    """A bridge whose fetch records how many real upstream calls happened."""

    def __init__(self, counter):
        self._counter = counter

    async def fetch(self, capability, params):
        self._counter["fetches"] += 1
        return {"status": "OK"}


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-resume-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def _registry(counter):
    reg = ToolRegistry()

    async def counting_tool(args, ctx):
        counter["executed"] += 1
        return "counted", {"status": "OK"}

    reg.register(ToolDefinition(
        name="counting_tool", description="counts", input_schema={
            "type": "object", "properties": {"x": {"type": "integer"}},
        }, handler=counting_tool, permission="read", risk="low",
    ))
    return reg


def _req(run_id: str, **kwargs) -> RunRequest:
    return RunRequest(
        runId=run_id,
        input=RunInput(query="run the tool"),
        # An explicit agent whose allowlist includes the counting tool. maxSteps=3
        # leaves room for the crash + resume to complete.
        agent=AgentConfig(
            id="resume-test", name="Resume", systemPrompt="sys",
            tools=["counting_tool"], maxSteps=3,
        ),
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
        **kwargs,
    )


# ── Resume safety: no duplicate tool execution ───────────────────────────────


@pytest.mark.asyncio
async def test_resume_after_crash_does_not_reexecute_completed_tool(store, monkeypatch):
    counter = {"executed": 0, "fetches": 0}
    registry = _registry(counter)

    # 1) A run is killed AFTER the tool executed (step 2 raises BaseException,
    #    which the graph does not catch — the run row is left `running`).
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: KillModel())
    with pytest.raises(BaseException):
        await graph_module.execute_run(_req("run_crash"), registry, CountingBridge(counter), store)
    assert store.get_run("run_crash")["status"] == "running"
    assert counter["executed"] == 1
    # The tool result was persisted once.
    execs = store.list_tool_executions("run_crash")
    assert len([e for e in execs if e["name"] == "counting_tool"]) == 1

    # 2) Resume: the SAME run continues and must NOT re-run counting_tool.
    lineage = RunLineage(store)
    checkpoint = lineage.latest_checkpoint("run_crash")
    assert checkpoint is not None
    # Round 5 / C2: the checkpoint names a cursor into the durable message log.
    assert checkpoint["payload"].get("messageSeq") is not None
    assert lineage.load_messages("run_crash")
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: ResumedModel())
    resumed = await graph_module.execute_run(
        _req("run_crash", resumeFrom=checkpoint["id"]), registry, CountingBridge(counter), store,
    )
    assert resumed.status == "completed"
    assert resumed.output == "resumed answer"
    # Exactly one execution — the resume reused the recorded result.
    assert counter["executed"] == 1
    execs = store.list_tool_executions("run_crash")
    assert len([e for e in execs if e["name"] == "counting_tool"]) == 1


@pytest.mark.asyncio
async def test_resume_yields_exactly_one_terminal_status(store, monkeypatch):
    counter = {"executed": 0, "fetches": 0}
    registry = _registry(counter)
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: KillModel())
    with pytest.raises(BaseException):
        await graph_module.execute_run(_req("run_term"), registry, CountingBridge(counter), store)
    checkpoint = RunLineage(store).latest_checkpoint("run_term")
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: ResumedModel())
    await graph_module.execute_run(
        _req("run_term", resumeFrom=checkpoint["id"]), registry, CountingBridge(counter), store,
    )
    events = [e["type"] for e in store.list_events("run_term")]
    assert events.count("run.completed") == 1
    assert store.get_run("run_term")["status"] == "completed"


# ── Structured resume errors ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resume_with_no_checkpoint_returns_checkpoint_not_found(store, monkeypatch):
    store.create_run("run_nockpt", "eclipse-agent", {"query": "x"})
    result = await graph_module.execute_run(
        _req("run_nockpt", resumeFrom="ckpt_missing"), _registry({"executed": 0}), CountingBridge({"fetches": 0}), store,
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "CHECKPOINT_NOT_FOUND"
    # The run's real status is untouched — no fresh run started in its place.
    assert store.get_run("run_nockpt")["status"] == "created"


@pytest.mark.asyncio
async def test_resume_of_terminal_run_returns_resume_conflict(store, monkeypatch):
    model = ScriptedModel([AIMessage(content="done")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    await graph_module.execute_run(_req("run_done"), _registry({"executed": 0}), CountingBridge({"fetches": 0}), store)
    assert store.get_run("run_done")["status"] == "completed"
    result = await graph_module.execute_run(
        _req("run_done", resumeFrom="whatever"), _registry({"executed": 0}), CountingBridge({"fetches": 0}), store,
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "RESUME_CONFLICT"
    # Still exactly one terminal status persisted.
    assert store.get_run("run_done")["status"] == "completed"
