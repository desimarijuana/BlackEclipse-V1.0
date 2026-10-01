"""Resume gate (Harness closeout Phase 8.4).

Offline and deterministic. A mid-run KILL fixture: the model raises a
`BaseException` (not caught by the graph, leaving the run `running`), then the run
is resumed. Asserts exactly one terminal status and ZERO duplicate tool
executions — on PERSISTED ROWS, never model prose.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from langchain_core.messages import AIMessage

from .. import graph as graph_module
from ..persistence import AgentMemoryStore
from ..run_lineage import RunLineage
from ..schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from ..tools import DataBridge, ToolDefinition, ToolRegistry


class _Killed(BaseException):
    pass


class _KillModel:
    def __init__(self):
        self._calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self._calls += 1
        if self._calls == 1:
            return AIMessage(content="", tool_calls=[{"id": "c1", "name": "counter", "args": {}}])
        raise _Killed("killed")

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class _ResumeModel:
    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return AIMessage(content="resumed")

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class _Bridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "OK"}


def run_gate() -> None:
    directory = tempfile.mkdtemp(prefix="be-gate-resume-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    counter = {"n": 0}
    registry = ToolRegistry()

    async def handler(args, ctx):
        counter["n"] += 1
        return "counted", {"status": "OK"}

    registry.register(ToolDefinition(
        name="counter", description="c", input_schema={"type": "object", "properties": {}},
        handler=handler, permission="read", risk="low",
    ))
    agent = AgentConfig(id="t", name="t", systemPrompt="s", tools=["counter"], maxSteps=3)

    def request(run_id, **kw):
        return RunRequest(
            runId=run_id, input=RunInput(query="go"), agent=agent,
            modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
            callbackBaseUrl="http://localhost:3000", **kw,
        )

    try:
        graph_module.build_chat_model = lambda settings: _KillModel()
        try:
            asyncio.run(graph_module.execute_run(request("gate_resume"), registry, _Bridge(), store))
        except _Killed:
            pass
        assert counter["n"] == 1, "the tool executed once before the kill"
        checkpoint = RunLineage(store).latest_checkpoint("gate_resume")
        assert checkpoint is not None, "a checkpoint exists at the crash point"

        graph_module.build_chat_model = lambda settings: _ResumeModel()
        asyncio.run(graph_module.execute_run(
            request("gate_resume", resumeFrom=checkpoint["id"]), registry, _Bridge(), store,
        ))

        events = [e["type"] for e in store.list_events("gate_resume")]
        assert events.count("run.completed") == 1, "exactly one terminal completion"
        assert store.get_run("gate_resume")["status"] == "completed"
        # Zero duplicate tool execution: the counter is still 1.
        assert counter["n"] == 1, "resume must not re-execute a completed tool"
        row_count = len([e for e in store.list_tool_executions("gate_resume") if e["name"] == "counter"])
        assert row_count == 1, "exactly one persisted tool row"
    finally:
        store.close()


__all__ = ["run_gate"]
