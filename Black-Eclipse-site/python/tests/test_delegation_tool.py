"""Phase 7 — the `delegate` tool: caps at the handler, and a child IS a run.

`execute_run` is patched so no model is needed; the assertion is that each child
goes through the EXISTING runtime with `parentRunId` set — never a second path.
"""

from __future__ import annotations

import asyncio

import pytest

import harness.graph as graph_mod
from harness.code.tools import register_code_tools
from harness.delegation import MAX_DEPTH
from harness.schemas import ModelSettings
from harness.tools import ToolContext, ToolRegistry


class _FakeResult:
    def __init__(self, run_id: str, tokens: int = 0) -> None:
        self._run_id = run_id
        self._tokens = tokens

    def model_dump(self) -> dict:
        return {
            "runId": self._run_id, "status": "completed", "output": "done",
            "error": None, "totalTokens": self._tokens,
        }


def _ctx(**overrides) -> ToolContext:
    base = dict(
        run_id="run_parent",
        log=lambda *_: None,
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(),
        data_bridge=object(),
        memory_store=None,
        allowed={"delegate", "workspace_read"},
        delegation_depth=0,
    )
    base.update(overrides)
    return ToolContext(**base)


def test_delegate_is_registered():
    reg = ToolRegistry()
    register_code_tools(reg)
    assert reg.get("delegate") is not None


def test_delegate_refuses_width_exceeded():
    reg = ToolRegistry()
    register_code_tools(reg)
    tool = reg.get("delegate")
    assert tool is not None
    children = [{"goal": f"c{i}"} for i in range(5)]
    result = asyncio.run(reg.execute("delegate", "c1", {"children": children}, _ctx()))
    assert result.ok is True
    assert result.data["status"] == "refused"
    assert result.data["code"] == "DELEGATION_WIDTH_EXCEEDED"


def test_delegate_refuses_depth_exceeded():
    reg = ToolRegistry()
    register_code_tools(reg)
    ctx = _ctx(delegation_depth=MAX_DEPTH)
    result = asyncio.run(reg.execute("delegate", "c1", {"children": [{"goal": "x"}]}, ctx))
    assert result.data["status"] == "refused"
    assert result.data["code"] == "DELEGATION_DEPTH_EXCEEDED"


def test_delegate_runs_each_child_through_execute_run_with_a_parent_link(monkeypatch):
    seen: list = []

    async def fake_execute_run(request, *args, **kwargs):
        seen.append(request)
        return _FakeResult(request.runId)

    monkeypatch.setattr(graph_mod, "execute_run", fake_execute_run)

    reg = ToolRegistry()
    register_code_tools(reg)
    result = asyncio.run(reg.execute(
        "delegate", "c1",
        {"children": [{"goal": "a"}, {"goal": "b"}]},
        _ctx(),
    ))
    assert result.ok is True
    assert len(seen) == 2
    # A child IS a normal run with this run as its parent — never a second path.
    assert all(r.parentRunId == "run_parent" for r in seen)
    assert all(r.runId.startswith("run_parent_child") for r in seen)
    assert result.data["completed"] == 2


def test_delegate_narrowing_uses_the_parents_allowlist(monkeypatch):
    """A child requesting a tool the parent lacks is refused, not run."""
    seen: list = []

    async def fake_execute_run(request, *args, **kwargs):
        seen.append(request)
        return _FakeResult(request.runId)

    monkeypatch.setattr(graph_mod, "execute_run", fake_execute_run)

    reg = ToolRegistry()
    register_code_tools(reg)
    result = asyncio.run(reg.execute(
        "delegate", "c1",
        {"children": [{"goal": "a", "tool_subset": ["command_run"]}]},
        _ctx(allowed={"delegate", "workspace_read"}),
    ))
    assert seen == []  # the child never ran
    assert result.data["outcomes"][0]["status"] == "refused"


def test_child_token_usage_reaches_the_budget_report(monkeypatch):
    async def fake_execute_run(request, *args, **kwargs):
        return _FakeResult(request.runId, tokens=700)

    monkeypatch.setattr(graph_mod, "execute_run", fake_execute_run)

    reg = ToolRegistry()
    register_code_tools(reg)
    result = asyncio.run(reg.execute(
        "delegate", "c1", {"children": [{"goal": "a"}, {"goal": "b"}]}, _ctx(),
    ))
    assert result.data["budget"]["consumedTokens"] == 1_400


class _RecordingEmitter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit_transient(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))

    async def emit(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


def test_child_events_are_bridged_to_the_parent_stream(monkeypatch):
    """A child runs on its own run id; the bridge still reaches the parent."""
    from harness.events import EventBus

    bus = EventBus()
    emitter = _RecordingEmitter()

    async def fake_execute_run(request, *args, **kwargs):
        bus.publish({
            "runId": request.runId, "type": "run.started",
            "data": {"maxSteps": 4, "provider": "ollama"},
        })
        bus.publish({
            "runId": request.runId, "type": "tool.requested",
            "data": {"name": "workspace_read", "detail": "Reading the filing", "step": 1},
        })
        await asyncio.sleep(0.3)
        return _FakeResult(request.runId)

    monkeypatch.setattr(graph_mod, "execute_run", fake_execute_run)

    reg = ToolRegistry()
    register_code_tools(reg)
    result = asyncio.run(reg.execute(
        "delegate", "c1", {"children": [{"goal": "a"}]},
        _ctx(bus=bus, emitter=emitter),
    ))
    assert result.ok is True
    progress = [data for event, data in emitter.events if event == "delegation.progress"]
    assert progress, "the child's events were not bridged"
    assert progress[-1]["activity"] == "Reading the filing"
    assert progress[-1]["step"] == 1 and progress[-1]["maxSteps"] == 4
    assert progress[-1]["status"] == "completed"
    # The row is keyed by the fan-out and its part, so the UI can place it.
    assert progress[-1]["delegationId"].startswith("dlg_")
    assert progress[-1]["childIndex"] == 0


def test_a_failed_child_gets_a_stop_signal(monkeypatch):
    """A child that dies tells its cooperating tools to stop (cancel_event)."""
    captured: dict = {}

    async def fake_execute_run(request, *args, **kwargs):
        captured["event"] = kwargs.get("cancel_event")
        raise RuntimeError("boom")

    monkeypatch.setattr(graph_mod, "execute_run", fake_execute_run)

    reg = ToolRegistry()
    register_code_tools(reg)
    result = asyncio.run(reg.execute(
        "delegate", "c1", {"children": [{"goal": "a"}]}, _ctx(),
    ))
    assert result.data["outcomes"][0]["status"] == "failed"
    event = captured.get("event")
    assert event is not None and event.is_set()


def test_parent_workflow_id_is_carried_onto_the_delegation():
    from harness.delegation_tools import _parent_workflow_id

    class _Store:
        def get_run(self, _rid):
            return {"workflowId": "wf_parent"}

    assert _parent_workflow_id(_ctx(memory_store=_Store())) == "wf_parent"
    assert _parent_workflow_id(_ctx(memory_store=None)) is None


# -- the parent blob is additive + old-row-safe -------------------------------


def test_delegation_blob_is_persisted_and_old_rows_stay_readable(tmp_path):
    from harness.persistence import AgentMemoryStore
    from harness.delegation_tools import _record_blob

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    store.create_run("run_parent", "eclipse-agent", {"query": "compare five"})
    ctx = _ctx(memory_store=store)

    _record_blob(ctx, {"delegationId": "dlg_1", "children": [], "droppedClaims": []})

    db = store._db  # noqa: SLF001
    cols = {row["name"] for row in db.execute("PRAGMA table_info(HarnessRun)").fetchall()}
    assert "delegation" in cols
    row = db.execute("SELECT delegation FROM HarnessRun WHERE id='run_parent'").fetchone()
    assert row["delegation"] and "dlg_1" in row["delegation"]

    # A run created AFTER the column exists still reads cleanly (old-row-safe).
    store.create_run("run_other", "eclipse-agent", {"query": "x"})
    assert store.get_run("run_other") is not None
    store.close()

def test_a_surface_subagent_prompt_reaches_the_child(monkeypatch):
    """A delegated child inherits the surface's bounded prompt - and nothing else."""
    seen: list = []

    async def fake_execute_run(request, *args, **kwargs):
        seen.append(request)
        return _FakeResult(request.runId)

    monkeypatch.setattr(graph_mod, "execute_run", fake_execute_run)

    from harness.schemas import AgentConfig

    parent = AgentConfig(
        id="eclipse-agent", name="Eclipse", systemPrompt="parent prompt",
        tools=["delegate", "workspace_read"],
        subagentPrompt="Report the numbers and the source of each one.",
    )
    reg = ToolRegistry()
    register_code_tools(reg)
    result = asyncio.run(reg.execute(
        "delegate", "c1", {"children": [{"goal": "a"}]},
        _ctx(agent=parent),
    ))
    assert result.ok is True
    assert len(seen) == 1
    child = seen[0]
    assert child.agent is not None
    assert "Report the numbers and the source of each one." in child.agent.systemPrompt
    # The child's tools are the NARROWED set, not the parent's full allowlist.
    assert child.agent.tools is not None
    assert set(child.agent.tools) <= {"delegate", "workspace_read"}
    from harness.agents import get_agent

    assert len(child.agent.tools) < len(get_agent("eclipse-agent").tools or [])
    # The parent's own prompt is still the base of the child's.
    assert child.agent.systemPrompt.startswith("You are Eclipse Agent")
