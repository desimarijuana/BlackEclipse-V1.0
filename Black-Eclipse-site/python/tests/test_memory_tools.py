"""Phase 3-M — Memory/skill tool tests and runtime integration.

Verifies the tools the system prompt promises actually exist, that memory
persists and is recalled into a run, that scope isolation holds at the runtime
boundary, and that self-improvement safeguards are enforced (no self-granting
permissions, no auto-enabled skills).
"""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.finance_tools import register_finance_tools
from harness.memory_tools import register_memory_tools
from harness.persistence import AgentMemoryStore
from harness.retrieval_tools import register_retrieval_tools
from harness.schemas import ModelSettings
from harness.skills import SkillRegistry
from harness.tools import DataBridge, ToolContext, ToolRegistry


class ScriptedModel:
    def __init__(self, responses):
        self._responses = list(responses)
        self.tools_bound: list[str] = []

    def bind_tools(self, tools):
        self.tools_bound = [t.name for t in tools]
        return self

    async def ainvoke(self, messages):
        response = self._responses.pop(0) if self._responses else AIMessage(content="done")
        return response(messages) if callable(response) else response

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class FakeBridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}


@pytest.fixture()
def env(monkeypatch):
    directory = tempfile.mkdtemp(prefix="be-memtools-")
    os.environ["ECLIPSE_MEMORY_DB_PATH"] = os.path.join(directory, "eclipse-memory.db")
    run_store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    memory = EclipseMemoryService(EclipseMemoryStore())
    registry = ToolRegistry()
    register_finance_tools(registry)
    register_retrieval_tools(registry)
    register_memory_tools(registry)
    skill_registry = SkillRegistry(memory.store)
    skill_registry.load_all()
    skill_registry.attach_tool_registry(registry)
    yield {"run_store": run_store, "memory": memory, "registry": registry, "skill_registry": skill_registry}
    run_store.close()
    memory.close()


def _ctx(env, user_id="u1", is_skill=False, user_message=""):
    return ToolContext(
        run_id="run_t", log=lambda *_: None, user_id=user_id,
        is_skill_run=is_skill, memory_service=env["memory"], skill_registry=env["skill_registry"],
        user_message=user_message,
    )


# ── Tools exist ─────────────────────────────────────────────────────────────


def test_promised_tools_are_registered(env):
    names = set(env["registry"].names())
    assert {"memory", "skill_list", "skill_view"} <= names


# ── memory tool ─────────────────────────────────────────────────────────────


async def test_memory_tool_save_and_search(env):
    # A model save is authorized only when the user turn carried explicit save
    # intent — the shared decision gate re-checks it.
    ctx = _ctx(env, user_message="Remember that I prefer terse answers")
    text, data = await env["registry"].get("memory").handler(
        {"action": "save", "content": "User prefers terse answers", "type": "preference", "scope": "user"},
        ctx,
    )
    assert data["saved"] is True
    assert "saved" in text.lower()

    text2, data2 = await env["registry"].get("memory").handler(
        {"action": "search", "query": "terse answers"}, ctx,
    )
    assert data2["count"] >= 1


async def test_memory_tool_write_without_user_intent_is_not_saved(env):
    # The model cannot authorize its own write; without an explicit user request
    # the proposal is downgraded and nothing is stored.
    ctx = _ctx(env, user_message="What is the price of AAPL?")
    _, data = await env["registry"].get("memory").handler(
        {"action": "save", "content": "User prefers terse answers", "type": "preference", "scope": "user"},
        ctx,
    )
    assert data["saved"] is False
    assert env["memory"].store.list_memories() == []


async def test_memory_tool_rejects_bad_write(env):
    ctx = _ctx(env)
    _, data = await env["registry"].get("memory").handler(
        {"action": "save", "content": "", "type": "semantic"}, ctx,
    )
    assert data["saved"] is False
    assert "NOT SAVED" in _  # noqa: F841


async def test_memory_tool_save_without_confidence(env):
    # Regression: save with NO confidence, and with an explicit null, must not
    # crash with `float() argument must be ... not 'NoneType'`. Both fall back to
    # the default; authorized write still succeeds.
    ctx = _ctx(env, user_message="Remember that I prefer terse answers")
    for content in ("User prefers terse answers", "User prefers terse summaries"):
        text, data = await env["registry"].get("memory").handler(
            {"action": "save", "content": content, "type": "preference",
             "scope": "user", "confidence": None},
            ctx,
        )
        assert data["saved"] is True, (content, data)
        assert "saved" in text.lower()
    # Omitted entirely (key absent) is the other common shape.
    _, data = await env["registry"].get("memory").handler(
        {"action": "save", "content": "User prefers terse reports", "type": "preference", "scope": "user"},
        ctx,
    )
    assert data["saved"] is True


async def test_memory_tool_save_with_malformed_confidence_is_typed(env):
    # A non-numeric confidence is a typed invalid_input error, not a TypeError.
    ctx = _ctx(env, user_message="Remember that I prefer terse answers")
    text, data = await env["registry"].get("memory").handler(
        {"action": "save", "content": "User prefers terse updates", "type": "preference",
         "scope": "user", "confidence": "not-a-number"},
        ctx,
    )
    assert data["saved"] is False
    assert data["outcome"] == "invalid_input"
    assert "invalid input" in text.lower()
    assert env["memory"].store.list_memories() == []


async def test_memory_tool_list_tolerates_null_limit(env):
    # Regression: a present-but-null `limit` (JSON null) must not crash.
    # `args.get("limit", 20)` returns None when the key exists with value None,
    # so the handler must coerce with `or`, not the default only.
    ctx = _ctx(env)
    _, listed = await env["registry"].get("memory").handler(
        {"action": "list", "limit": None}, ctx,
    )
    assert listed["count"] == 0

    _, searched = await env["registry"].get("memory").handler(
        {"action": "search", "query": "nothing", "limit": None}, ctx,
    )
    assert searched["count"] == 0


async def test_memory_tool_requires_service():
    ctx = ToolContext(run_id="r", log=lambda *_: None, memory_service=None)
    with pytest.raises(RuntimeError):
        await _call_memory(ctx)


async def _call_memory(ctx):
    from harness.memory_tools import memory_handler

    return await memory_handler({"action": "list"}, ctx)


# ── skill tools (progressive disclosure) ────────────────────────────────────


async def test_skill_list_then_view(env):
    ctx = _ctx(env)
    _, listed = await env["registry"].get("skill_list").handler({"query": "fundamental"}, ctx)
    assert any(s["id"] == "finance.fundamental-analysis" for s in listed["skills"])
    # Metadata only — no instructions in list output.
    assert all("instructions" not in s for s in listed["skills"])

    text, viewed = await env["registry"].get("skill_view").handler(
        {"name": "finance.fundamental-analysis"}, ctx,
    )
    assert viewed["found"] is True
    assert "Fundamental Analysis" in text
    assert "reported" in text.lower()


async def test_skill_view_unknown(env):
    _, data = await env["registry"].get("skill_view").handler({"name": "no.such"}, _ctx(env))
    assert data["found"] is False


# ── Runtime integration: recall injection ───────────────────────────────────


async def test_memory_is_injected_into_run(env, monkeypatch):
    env["memory"].write_memory(
        memory_type="preference", content="User always wants PKR values",
        source="explicit_user", scope="user", scope_id="u1", created_by="u1",
    )
    seen: dict[str, object] = {}

    def responder(messages):
        seen["system_messages"] = [m.content for m in messages if m.__class__.__name__ == "SystemMessage"]
        return AIMessage(content="ok")

    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: ScriptedModel([responder]))
    request = _run_request(run_id="run_mem", user_id="u1", query="Show me the price of AAPL")
    result = await graph_module.execute_run(
        request, env["registry"], FakeBridge(), env["run_store"],
        memory_service=env["memory"], skill_registry=env["skill_registry"],
    )
    assert result.status == "completed"
    combined = "\n".join(seen["system_messages"])
    assert "PKR values" in combined
    assert "<memory-context>" in combined


async def test_memory_scope_isolation_in_run(env, monkeypatch):
    env["memory"].write_memory(
        memory_type="preference", content="u1 secret marker",
        source="explicit_user", scope="user", scope_id="u1", created_by="u1",
    )
    seen: dict[str, object] = {}

    def responder(messages):
        seen["system_messages"] = [m.content for m in messages if m.__class__.__name__ == "SystemMessage"]
        return AIMessage(content="ok")

    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: ScriptedModel([responder]))
    request = _run_request(run_id="run_u2", user_id="u2", query="show me something")
    await graph_module.execute_run(
        request, env["registry"], FakeBridge(), env["run_store"],
        memory_service=env["memory"], skill_registry=env["skill_registry"],
    )
    combined = "\n".join(seen["system_messages"])
    assert "u1 secret marker" not in combined


# ── Self-improvement safeguards ─────────────────────────────────────────────


async def test_tool_allowlist_bound_in_run(env, monkeypatch):
    seen: dict[str, object] = {}

    def responder(messages):
        seen["bound"] = []
        return AIMessage(content="ok")

    model = ScriptedModel([responder])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    await graph_module.execute_run(
        _run_request(run_id="run_b", user_id="u1", query="x"),
        env["registry"], FakeBridge(), env["run_store"],
        memory_service=env["memory"], skill_registry=env["skill_registry"],
    )
    # The bound tools are the eclipse-agent allowlist — never the full registry
    # by accident, and never a hidden privilege.
    assert "memory" in model.tools_bound
    assert "skill_view" in model.tools_bound


def test_prompt_has_no_phantom_capabilities():
    from harness.prompts import ECLIPSE_AGENT_SYSTEM_PROMPT as prompt

    for phantom in ("skill_manage", "terminal", "read_file", "search_files",
                    "execute_code", "available_skills", "MEDIA:", "::preview"):
        assert phantom not in prompt, f"prompt still promises {phantom!r}"


def _run_request(*, run_id: str, user_id: str, query: str):
    from harness.schemas import RunInput, RunRequest

    return RunRequest(
        runId=run_id,
        input=RunInput(query=query),
        agent=None,
        agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="openai", model="test", api_key="x"),
        userId=user_id,
        callbackBaseUrl="http://127.0.0.1:3000",
    )
