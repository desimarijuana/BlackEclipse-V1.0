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
    import re

    from harness.agents import ECLIPSE_AGENT
    from harness.prompts import ECLIPSE_AGENT_SYSTEM_PROMPT as prompt

    for phantom in ("skill_manage", "terminal", "read_file", "search_files",
                    "execute_code", "available_skills", "MEDIA:", "::preview"):
        assert phantom not in prompt, f"prompt still promises {phantom!r}"

    # No tool that LOOKS like an invocation may be named unless it is in the
    # agent's allowlist (a namespaced `mcp__…` name is a user-directed surface).
    allowed = set(ECLIPSE_AGENT.tools)
    for token in re.findall(r"`([a-z][a-z0-9_]*)\(", prompt):
        assert token in allowed or token.startswith("mcp_"), (
            f"prompt invokes tool {token!r} which is not in the agent allowlist"
        )
    for token in re.findall(r"\b([a-z][a-z0-9_]{3,})\(", prompt):
        if token.endswith(("_get", "_search", "_view", "_invoke", "_list",
                           "_run", "_apply", "_read", "_open", "_source")):
            assert token in allowed, (
                f"prompt names tool-like {token!r} not in the agent allowlist"
            )


def test_prompt_char_ceiling():
    """The finance-harness prompt stays under its ceiling (a size ratchet).

    The ceiling was raised repeatedly by concurrent work (Phase 7 `delegate`,
    Phase 9 `scaffold_kit`, the Browser runtime, the Web Research Engine, the
    Computer Use Engine — to 23300). Phase S.2 instead LOWERED it, by trimming a
    redundant worked example, so the ratchet bites again rather than being widened.
    It may only shrink from here unless a new capability genuinely requires more.

    Raised to 23725 by the Task / Plan runtime: a durable, hierarchical plan whose
    steps are dispatched through the run path is a genuinely new capability that
    needs one guidance paragraph. Re-pinned to the measured size; the ratchet bites
    again from here.

    Raised to 25217 by the Eclipse UI authoring capability: the `ui_*` tools let
    the agent compose pages/widgets and file engineering tasks for Eclipse's own
    interface — a genuinely new capability that needs one guidance paragraph.
    Re-pinned to the measured size; the ratchet bites again from here.

    Raised to 26410 by the Interactive Response Engine: the agent may emit one
    fenced `eclipse-response` block (metric grids, tables, charts, diagrams,
    timelines, citations, controls) — a genuinely new output capability that needs
    one guidance paragraph. Re-pinned to the measured size; it may only shrink
    from here.

    Raised to 27445 by the Learning-Research capability: the agent may build a
    prerequisite-aware learning path with `learning_path_build` and render it with
    the interactive `learning_map` block (completion controls that persist) — a
    genuinely new output capability that needs one guidance paragraph. (The
    measured size had already drifted past the pin before this change; this
    re-pins to the real, measured size and the ratchet bites again from here.)
    """
    from harness.prompts import ECLIPSE_AGENT_SYSTEM_PROMPT as prompt

    assert len(prompt) <= 27445, f"prompt grew to {len(prompt)} chars"


def test_prompt_market_data_semantics_present():
    """M1: the finance comparability rules are present."""
    from harness.prompts import ECLIPSE_AGENT_SYSTEM_PROMPT as prompt

    assert "# Market data semantics" in prompt
    for rule in ("Session state", "Price basis", "Period basis",
                 "Corporate actions", "Point-in-time vs restated", "FX"):
        assert rule in prompt, f"market-data rule missing: {rule}"


def test_prompt_inputs_authority_and_attachments_present():
    """M2: the attached-document rule and the precedence table are present."""
    from harness.prompts import ECLIPSE_AGENT_SYSTEM_PROMPT as prompt

    assert "# Inputs and authority" in prompt
    assert "[attached:" in prompt
    assert "system policy" in prompt
    assert "conversation history" in prompt
    # Gap 2: the never-populated `run instructions` rank is gone.
    assert "run instructions" not in prompt


# ── gap 5: guards that apply to BOTH presets ────────────────────────────────


def _presets():
    from harness.agents import CODE_NAVIGATOR, ECLIPSE_AGENT
    from harness.prompts import CODE_NAVIGATOR_SYSTEM_PROMPT, ECLIPSE_AGENT_SYSTEM_PROMPT

    return (
        ("eclipse-agent", ECLIPSE_AGENT_SYSTEM_PROMPT, ECLIPSE_AGENT),
        ("code-navigator", CODE_NAVIGATOR_SYSTEM_PROMPT, CODE_NAVIGATOR),
    )


def _named_tools(prompt: str) -> set[str]:
    import re

    from harness.agents import CODE_NAVIGATOR, ECLIPSE_AGENT

    known = set(ECLIPSE_AGENT.tools) | set(CODE_NAVIGATOR.tools)
    return set(re.findall(r"`([a-z][a-z0-9_]+)`", prompt)) & known


def test_every_prompt_tool_name_is_in_its_allowlist():
    """Gap 5: every tool a prompt names as its own is in that preset's allowlist.

    This is the test that would have caught Gap 1 (the navigator prompt named
    only five of its nine tools but described a false surface).
    """
    for agent_id, prompt, agent in _presets():
        allowed = set(agent.tools)
        for name in _named_tools(prompt):
            assert name in allowed, (
                f"{agent_id} prompt names tool {name!r} not in its allowlist"
            )


def test_prompt_may_not_deny_a_capability_its_allowlist_contains():
    """Gap 5: a prompt may not assert it cannot do what its allowlist permits."""
    for agent_id, prompt, agent in _presets():
        allowed = set(agent.tools)
        if "command_run" in allowed:
            for denial in ("cannot run any command", "You cannot run any command"):
                assert denial not in prompt, (
                    f"{agent_id} allowlist has command_run but prompt denies it"
                )


def test_prompt_does_not_enumerate_only_a_subset_of_its_allowlist():
    """Gap 5: a prompt that claims to enumerate its tools must name all of them."""
    import re

    for agent_id, prompt, agent in _presets():
        if re.search(r"tools are exactly", prompt):
            named = _named_tools(prompt)
            missing = set(agent.tools) - named
            assert not missing, (
                f"{agent_id} claims to enumerate its tools but omits {sorted(missing)}"
            )


def test_has_no_duplicated_rule_sentences():
    """Gap 5: no rule sentence (>40 chars) is repeated, in EITHER preset."""
    import re

    for agent_id, prompt, _agent in _presets():
        sentences = [
            re.sub(r"\s+", " ", s).strip()
            for s in re.split(r"(?<=[.!?])\s+", prompt)
            if len(s.strip()) > 40
        ]
        duplicates = {s for s in sentences if sentences.count(s) > 1}
        assert not duplicates, f"{agent_id} duplicated rule text: {duplicates}"


def test_navigator_prompt_char_ceiling():
    """Gap 5: the navigator prompt has a size ratchet too."""
    from harness.prompts import CODE_NAVIGATOR_SYSTEM_PROMPT as prompt

    assert len(prompt) <= 3000, f"navigator prompt grew to {len(prompt)} chars"


def test_navigator_prompt_matches_its_real_surface():
    """Gap 1: the navigator prompt no longer understates or denies its surface."""
    from harness.agents import CODE_NAVIGATOR
    from harness.prompts import CODE_NAVIGATOR_SYSTEM_PROMPT as prompt

    # The false "exactly five read tools" enumeration is gone...
    assert "Your tools are exactly" not in prompt
    # ...and the genuinely-unavailable set is narrower and true.
    assert "cannot run an arbitrary program or shell command" in prompt
    assert "there is no tool that accepts a program or a command from you" in prompt
    # command_run is acknowledged as a real, allowlisted surface.
    assert "command_run" in prompt and "command_run" in CODE_NAVIGATOR.tools


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
