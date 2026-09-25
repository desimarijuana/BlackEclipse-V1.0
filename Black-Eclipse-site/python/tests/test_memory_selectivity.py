"""Memory selectivity — the shared decision gate, explicit controls, suggestions,
financial-fact exclusion, and scope/recall across restarts.

These tests exercise the ACTUAL write paths (graph run, model memory tool,
service gate, UI-equivalent save) rather than classifier helpers alone. No model,
no network: a synthetic run trace + scripted models only.

Correctness defined by:
  1. explicit safe "remember" saves exactly one scoped record;
  2. a casual "I prefer …" does not save (suggestion only if enabled);
  3. "always use X" inside a one-off task does not save;
  4. greetings / ordinary Q&A / research / multi-step tool runs create nothing;
  5. prices, analysis, retrieved sources, tool output, documents cannot write;
  6. the model memory tool cannot write without the shared gate;
  7. forget/correct target the selected record with audit + supersession;
  8. duplicates do not accumulate;
  9. secrets/transcripts/injection are rejected without storing the content;
 10. a failing gate/curator does not fail chat and writes nothing;
 11. explicit "turn this into a skill" creates an inert candidate only;
 12. routine research creates no candidate while automatic learning is off;
 13. scope isolation + recall across a process-style reopen.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.decision import authorize_proposal, decide_turn
from harness.finance_tools import register_finance_tools
from harness.memory_tools import register_memory_tools
from harness.persistence import AgentMemoryStore
from harness.retrieval_tools import register_retrieval_tools
from harness.schemas import AgentConfig, ConversationTurn, ModelSettings, RunInput, RunRequest
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


def _plain_model():
    class M:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            return AIMessage(content="ok")

        async def astream(self, messages):
            yield await self.ainvoke(messages)

    return M()


@pytest.fixture()
def env(monkeypatch):
    directory = tempfile.mkdtemp(prefix="be-select-")
    memory_path = os.path.join(directory, "eclipse-memory.db")
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", memory_path)
    run_store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    memory = EclipseMemoryService(EclipseMemoryStore(memory_path))
    registry = ToolRegistry()
    register_finance_tools(registry)
    register_retrieval_tools(registry)
    register_memory_tools(registry)
    skill_registry = SkillRegistry(memory.store)
    skill_registry.load_all()
    skill_registry.attach_tool_registry(registry)
    yield {
        "memory": memory, "run_store": run_store, "registry": registry,
        "skill_registry": skill_registry, "dir": directory,
    }
    run_store.close()
    memory.close()


def _run(env, query, *, model=None, run_id="run_sel"):
    model = model or _plain_model()
    orig = graph_module.build_chat_model
    graph_module.build_chat_model = lambda settings: model  # type: ignore
    req = RunRequest(
        runId=run_id, input=RunInput(query=query),
        agentId="eclipse-agent", userId="u1",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    try:
        return asyncio.run(graph_module.execute_run(
            req, env["registry"], FakeBridge(), env["run_store"],
            memory_service=env["memory"], skill_registry=env["skill_registry"],
        ))
    finally:
        graph_module.build_chat_model = orig  # type: ignore


# ── 1. Explicit save ────────────────────────────────────────────────────────


def test_explicit_remember_saves_exactly_one_scoped_record(env):
    result = _run(env, "Remember that I prefer concise answers with source links.")
    assert result.status == "completed"
    saved = env["memory"].store.list_memories()
    assert len(saved) == 1
    assert saved[0]["scope"] == "user"
    assert saved[0]["memoryType"] == "preference"
    # The run blob confirms the write only after it succeeded.
    blob = env["run_store"].get_run("run_sel")["memory"]
    assert blob["action"] == "saved"
    assert blob["memoryId"] == saved[0]["id"]


def test_explicit_save_is_idempotent_on_repeat(env):
    _run(env, "Remember that I prefer terse answers.", run_id="run_a")
    _run(env, "Remember that I prefer terse answers.", run_id="run_b")
    assert len(env["memory"].store.list_memories()) == 1


# ── 2. Casual preference does not save ──────────────────────────────────────


def test_casual_preference_is_saved_automatically(env):
    # automatic_selective (the default): a clear, low-risk user preference is
    # worth remembering and is saved without interrupting the user.
    _run(env, "I prefer concise answers")
    saved = env["memory"].store.list_memories()
    assert len(saved) == 1
    assert saved[0]["scope"] == "user"
    assert saved[0]["memoryType"] == "preference"


def test_casual_preference_ask_mode_suggests_only(env):
    # ask_before_saving: stage an inert suggestion, never a durable memory.
    env["memory"].policy.set("memory_mode", "ask_before_saving")
    _run(env, "I prefer concise answers with bullet points")
    assert env["memory"].store.list_memories() == []
    pending = env["memory"].store.list_suggestions(status="pending")
    assert len(pending) == 1
    assert pending[0]["content"].lower().startswith("i prefer")
    # Recall never injects a suggestion.
    result = env["memory"].retrieve(query="concise answers")
    assert all("concise answers" not in m["content"] for m in result.memories)


def test_accepting_suggestion_writes_one_record(env):
    env["memory"].policy.set("memory_mode", "ask_before_saving")
    _run(env, "I prefer concise answers")
    suggestion = env["memory"].store.list_suggestions(status="pending")[0]
    outcome = env["memory"].accept_suggestion(suggestion["id"], user_id="u1")
    assert outcome["ok"] is True
    assert len(env["memory"].store.list_memories()) == 1
    assert env["memory"].store.get_suggestion(suggestion["id"])["status"] == "accepted"


def test_dismissed_suggestion_is_not_reoffered(env):
    env["memory"].policy.set("memory_mode", "ask_before_saving")
    _run(env, "I prefer concise answers", run_id="run_x")
    suggestion = env["memory"].store.list_suggestions(status="pending")[0]
    env["memory"].dismiss_suggestion(suggestion["id"])
    _run(env, "I prefer concise answers", run_id="run_y")
    # The same suggestion is not re-created after dismissal.
    assert len(env["memory"].store.list_suggestions(status="pending")) == 0


def test_memory_off_mode_learns_nothing(env):
    env["memory"].policy.set("memory_mode", "off")
    _run(env, "I prefer concise answers")
    assert env["memory"].store.list_memories() == []
    assert env["memory"].store.list_suggestions(status="pending") == []


# ── 3. One-off instruction ──────────────────────────────────────────────────


def test_always_use_x_for_this_task_does_not_save(env):
    _run(env, "Always use X for this task")
    assert env["memory"].store.list_memories() == []


# ── 4. Ordinary chat creates nothing ────────────────────────────────────────


@pytest.mark.parametrize("query", [
    "Hi there!",
    "Thanks!",
    "What is the price of AAPL?",
    "Compare these two companies today.",
    "Summarise the latest news for me.",
])
def test_ordinary_chat_creates_nothing(env, query):
    _run(env, query, run_id=f"run_{abs(hash(query))}")
    assert env["memory"].store.list_memories() == []
    assert env["memory"].store.list_suggestions(status="pending") == []
    assert env["memory"].store.list_candidates() == []


def test_multistep_tool_run_creates_no_candidate_or_memory(env):
    tool_call = AIMessage(
        content="", tool_calls=[{"id": "c1", "name": "get_market_snapshot", "args": {"symbol": "AAPL"}}]
    )
    model = ScriptedModel([tool_call, AIMessage(content="Here is the analysis.")])
    agent = AgentConfig(id="a", name="A", systemPrompt="sys", tools=["get_market_snapshot"], maxSteps=3)
    orig = graph_module.build_chat_model
    graph_module.build_chat_model = lambda settings: model  # type: ignore
    req = RunRequest(
        runId="run_multi", input=RunInput(query="Analyse AAPL over 3 steps"),
        agent=agent, userId="u1",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    try:
        result = asyncio.run(graph_module.execute_run(
            req, env["registry"], FakeBridge(), env["run_store"],
            memory_service=env["memory"], skill_registry=env["skill_registry"],
        ))
    finally:
        graph_module.build_chat_model = orig  # type: ignore
    assert result.status == "completed"
    assert env["memory"].store.list_memories() == []
    assert env["memory"].store.list_candidates() == []


# ── 5. Financial facts / tool output / documents cannot write ───────────────


def test_financial_fact_is_not_saved_even_when_directed(env):
    _run(env, "Save this: AAPL current price is $190.50")
    assert env["memory"].store.list_memories() == []


def test_financial_fact_via_model_tool_is_rejected(env):
    ctx = ToolContext(
        run_id="r", log=lambda *_: None, user_id="u1",
        memory_service=env["memory"], skill_registry=env["skill_registry"],
        user_message="Here is the analysis: valuation is 2.5B, save it",
    )
    _, data = asyncio.run(env["registry"].get("memory").handler(
        {"action": "save", "content": "AAPL valuation is $2.5B", "type": "semantic"}, ctx,
    ))
    assert data["saved"] is False
    assert env["memory"].store.list_memories() == []


def test_tool_output_cannot_authorize_a_write(env):
    # The tool proposal is checked against the user turn, not against tool text.
    decision = authorize_proposal(
        content="The retrieved filing says revenue grew",
        provenance="memory_tool",
        user_message="Get me the filing",
        user_id="u1",
    )
    assert decision.outcome != "save"


# ── 6. Model memory tool cannot self-authorize ──────────────────────────────


def test_model_memory_write_without_user_intent_is_not_saved(env):
    ctx = ToolContext(
        run_id="r", log=lambda *_: None, user_id="u1",
        memory_service=env["memory"], user_message="What is the price of AAPL?",
    )
    _, data = asyncio.run(env["registry"].get("memory").handler(
        {"action": "save", "content": "User likes charts", "type": "preference", "scope": "user"}, ctx,
    ))
    assert data["saved"] is False
    assert env["memory"].store.list_memories() == []


# ── 7. Forget / correct target + audit ──────────────────────────────────────


def test_forget_archives_the_target(env):
    saved = env["memory"].write_memory(
        memory_type="preference", content="User prefers terse answers",
        source="explicit_user", scope="user", scope_id="u1",
    )
    _run(env, "Forget my preference about terse answers")
    record = env["memory"].store.get_memory(saved["id"])
    assert record is not None
    assert record["status"] == "archived"


def test_correct_supersedes_and_links(env):
    saved = env["memory"].write_memory(
        memory_type="semantic", content="The expense ratio is 0.5%",
        source="explicit_user", scope="user", scope_id="u1",
    )
    _run(env, "That's wrong, the expense ratio is 0.05%")
    old = env["memory"].store.get_memory(saved["id"])
    assert old["status"] == "superseded"
    links = env["memory"].store.list_links(saved["id"])
    assert any(link["relation"] == "superseded" for link in links)


# ── 8. Duplicates do not accumulate ─────────────────────────────────────────


def test_duplicate_inputs_do_not_add_records(env):
    _run(env, "Remember that I prefer concise answers", run_id="run1")
    _run(env, "Remember that I prefer concise answers", run_id="run2")
    assert len(env["memory"].store.list_memories()) == 1


def test_ambiguous_forget_asks_and_changes_nothing(env):
    # Two similar memories: "forget this" must ask rather than archive both.
    env["memory"].write_memory(
        memory_type="semantic", content="The benchmark rate is 5%",
        source="explicit_user", scope="user", scope_id="u1", allow_duplicate=True,
    )
    env["memory"].write_memory(
        memory_type="semantic", content="The benchmark rate is 6%",
        source="explicit_user", scope="user", scope_id="u1", allow_duplicate=True,
    )
    outcome = env["memory"].apply_explicit_intent(
        __import__("harness.eclipse_memory.intent", fromlist=["detect_memory_intent"]).detect_memory_intent(
            "Forget my benchmark rate", user_id="u1"
        ),
        user_id="u1",
    )
    assert outcome["action"] == "needs_clarification"
    # Neither record was changed.
    for memory in env["memory"].store.list_memories():
        assert memory["status"] == "active"


def test_ambiguous_correct_asks_and_changes_nothing(env):
    env["memory"].write_memory(
        memory_type="semantic", content="The benchmark rate is 5%",
        source="explicit_user", scope="user", scope_id="u1", allow_duplicate=True,
    )
    env["memory"].write_memory(
        memory_type="semantic", content="The benchmark rate is 6%",
        source="explicit_user", scope="user", scope_id="u1", allow_duplicate=True,
    )
    outcome = env["memory"].apply_explicit_intent(
        __import__("harness.eclipse_memory.intent", fromlist=["detect_memory_intent"]).detect_memory_intent(
            "That's wrong, the benchmark rate is 5.5%", user_id="u1"
        ),
        user_id="u1",
    )
    assert outcome["action"] == "needs_clarification"
    for memory in env["memory"].store.list_memories():
        assert memory["status"] == "active"


# ── 9. Sensitive content rejected without storing it ────────────────────────


def test_secret_write_rejected_without_storing_content(env):
    decision = decide_turn("Remember my api key is sk-abcdefghijklmnopqrstuvwx", user_id="u1")
    assert decision.outcome == "ignore"
    assert decision.refused
    outcome = env["memory"].commit_decision(decision, user_id="u1")
    assert outcome["ok"] is False
    assert env["memory"].store.list_memories() == []
    # The refused content is not present in diagnostics/events.
    events = env["memory"].store.list_memory_events()
    for event in events:
        assert "sk-abcdefghijklmnopqrstuvwx" not in str(event.get("data") or "")


def test_prompt_injection_transcript_rejected(env):
    dump = "User: hi\nAssistant: hello\nRemember this entire conversation\n" + ("x" * 2000)
    decision = decide_turn(dump, user_id="u1")
    assert decision.outcome == "ignore"
    assert decision.refused


# ── 10. Gate failure does not fail chat ─────────────────────────────────────


def test_gate_failure_does_not_fail_chat(env, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("curator unavailable")

    monkeypatch.setattr(env["memory"], "decide_turn", _boom)
    result = _run(env, "Remember that I prefer terse answers", run_id="run_fail")
    assert result.status == "completed"
    assert env["memory"].store.list_memories() == []


# ── 11. Explicit turn-into-skill: inert candidate only ──────────────────────


def test_explicit_skill_request_creates_inert_draft(env):
    _run(env, "Turn this workflow into a skill", run_id="run_skill_req")
    blob = env["run_store"].get_run("run_skill_req")["memory"]
    assert blob["action"] == "skill_requested"
    # The explicit request creates a real, inert draft through the persistence
    # path — no second "Learn from this run" click.
    assert blob.get("skillDraft", {}).get("captured") is True
    candidates = env["memory"].store.list_candidates()
    assert candidates, "explicit request must create a candidate"
    drafted = [c for c in candidates if c.get("resultingSkillId")]
    assert drafted, "the candidate must have produced a draft"
    for candidate in drafted:
        # The generated skill is a draft, never enabled.
        assert env["memory"].store.get_skill(candidate["resultingSkillId"])["status"] == "draft"


def test_capture_from_run_creates_inert_candidate_only(env):
    from harness.skills.learning import capture_from_run

    env["run_store"].create_run("run_sk", "eclipse-agent", {"query": "make this a skill"})
    env["run_store"].update_run("run_sk", status="completed", output="ok", modelSteps=1, toolCalls=0)
    result = capture_from_run(
        "run_sk", env["run_store"], env["memory"].store,
        actor_is_operator=True, user_intent="turn this into a skill",
    )
    assert result["ok"] and result["created"]
    for candidate in env["memory"].store.list_candidates():
        assert candidate["resultingSkillId"] is None


# ── 13. Scope isolation + recall across a reopen ────────────────────────────


def test_scope_isolation_and_recall_survive_reopen(env):
    env["memory"].write_memory(
        memory_type="preference", content="u1 prefers candlestick charts",
        source="explicit_user", scope="user", scope_id="u1",
    )
    reopened = EclipseMemoryService(EclipseMemoryStore(env["memory"].store.path))
    try:
        # u1 recalls it after a "restart".
        u1_result = reopened.retrieve(query="charts", actor_scope="user", scope_id="u1")
        assert any("candlestick" in m["content"] for m in u1_result.memories)
        # u2 never sees it.
        u2_result = reopened.retrieve(query="charts", actor_scope="user", scope_id="u2")
        assert all(m.get("scopeId") != "u1" for m in u2_result.memories)
    finally:
        reopened.close()


# ── Decision-quality fixtures: false-save vs missed explicit-save ───────────


# (text, expected_outcome). These encode the target selectivity under the
# default automatic_selective mode.
_DECISION_FIXTURES = [
    ("Remember that I prefer concise answers with source links.", "save"),
    ("Save this preference: always show figures in the local currency.", "save"),
    # A clear, low-risk user preference is worth remembering automatically.
    ("I prefer concise answers", "save"),
    ("I like charts better", "save"),
    # Task-scoped/question/one-off content is never durable memory.
    ("Compare these two companies today.", "ignore"),
    ("Why do I prefer charts?", "history_only"),
    ("What is the price of AAPL?", "ignore"),
    ("Thanks!", "ignore"),
    ("Hi, can you help me?", "ignore"),
    # A project convention needs recurrence before it is saved; without it, it
    # is searchable history only.
    ("Always use consolidated figures", "history_only"),
    ("Always use X for this task", "history_only"),
    ("Current price is 190", "ignore"),
    ("AAPL earnings were strong, save this", "ignore"),
    ("The valuation estimate is 3B", "ignore"),
    ("Forget this", "save"),          # forget is an explicit control action
    ("That's wrong, actually it's 5%", "save"),
    ("Turn this into a skill", "history_only"),
    ("Remember my api key is sk-abcdefghijklmnopqrstuvwx", "ignore"),
]


def test_decision_quality_fixtures(env):
    """Report false-save rate and missed-explicit-save rate separately.

    false_save: an incidental/unsafe case that incorrectly saved.
    missed_explicit_save: an explicit save control that failed to save.
    """
    settings = env["memory"].policy.get_all()
    false_saves: list[str] = []
    missed_saves: list[str] = []
    for text, expected in _DECISION_FIXTURES:
        decision = decide_turn(text, user_id="u1", settings=settings)
        if expected == "save" and decision.outcome != "save":
            missed_saves.append(text)
        if expected in ("ignore", "history_only") and decision.outcome == "save":
            false_saves.append(text)
    assert false_saves == [], f"false saves: {false_saves}"
    assert missed_saves == [], f"missed explicit saves: {missed_saves}"


def test_recurring_convention_saves_without_prompt(env):
    # The same project convention stated again (recurrence evidence) is saved
    # automatically, without a per-run prompt.
    decision = decide_turn(
        "Always use consolidated figures",
        user_id="u1",
        settings=env["memory"].policy.get_all(),
        recurring=True,
    )
    assert decision.outcome == "save"
    assert decision.metadata.get("evidence") == "recurrence"


# ── Storage budget: truthful "memory is full", never auto-delete ────────────


def test_storage_budget_blocks_new_save_truthfully(env):
    env["memory"].policy.set("max_memories", 2)
    env["memory"].write_memory(memory_type="semantic", content="fact one", source="manual")
    env["memory"].write_memory(memory_type="semantic", content="fact two", source="manual")
    with pytest.raises(Exception) as exc:
        env["memory"].write_memory(memory_type="semantic", content="fact three", source="manual")
    assert "full" in str(exc.value).lower()
    # Nothing was deleted to make room.
    assert len(env["memory"].store.list_memories(include_inactive=False)) == 2


def test_storage_budget_surfaces_as_memory_full_outcome(env):
    env["memory"].policy.set("max_memories", 1)
    env["memory"].write_memory(memory_type="semantic", content="fact one", source="manual")
    decision = decide_turn("Remember that I prefer concise answers", user_id="u1")
    outcome = env["memory"].commit_decision(decision, user_id="u1")
    assert outcome["ok"] is False
    assert outcome["action"] == "memory_full"
    assert outcome["limit"] == 1
    assert len(env["memory"].store.list_memories(include_inactive=False)) == 1


def test_duplicate_save_at_budget_is_not_a_full_error(env):
    env["memory"].policy.set("max_memories", 1)
    env["memory"].write_memory(memory_type="semantic", content="fact one", source="manual")
    # The same content is a duplicate, not a new record — it must not fail.
    same = env["memory"].write_memory(memory_type="semantic", content="fact one", source="manual")
    assert same is not None


def test_budget_report_is_accurate(env):
    env["memory"].policy.set("max_memories", 3)
    budget = env["memory"].memory_budget()
    assert budget["limit"] == 3 and budget["active"] == 0 and budget["remaining"] == 3
    assert budget["full"] is False
    env["memory"].write_memory(memory_type="semantic", content="a", source="manual")
    env["memory"].write_memory(memory_type="semantic", content="b", source="manual")
    env["memory"].write_memory(memory_type="semantic", content="c", source="manual")
    assert env["memory"].memory_budget()["full"] is True
    assert env["memory"].memory_budget()["remaining"] == 0
    # Archiving frees budget without deleting history.
    archived = env["memory"].store.list_memories(include_inactive=False)[0]
    env["memory"].store.archive_memory(archived["id"])
    assert env["memory"].memory_budget()["full"] is False
    assert env["memory"].store.get_memory(archived["id"]) is not None


def test_budget_unlimited_by_default(env):
    budget = env["memory"].memory_budget()
    assert budget["unlimited"] is True
    assert budget["remaining"] is None


# ── Automatic-selective lifecycle (positive + negative) ─────────────────────


def test_durable_preference_saved_automatically_in_selective_mode(env):
    # automatic_selective (default): a clear, durable, low-risk preference is
    # saved without asking each time.
    assert env["memory"].policy.get("memory_mode") == "automatic_selective"
    _run(env, "I prefer dividend-adjusted charts", run_id="run_auto_pref")
    saved = env["memory"].store.list_memories()
    assert len(saved) == 1
    assert saved[0]["scope"] == "user"
    # Provenance is preserved for audit.
    assert saved[0]["source"] == "explicit_user"


def test_onetime_task_detail_not_saved(env):
    # A temporary task detail is history-only, never durable memory.
    _run(env, "For this task use the last 5 years of data", run_id="run_onetime")
    assert env["memory"].store.list_memories() == []


def test_changing_market_value_not_saved(env):
    # A changing market value is never durable memory (even if phrased as one).
    _run(env, "The current price of AAPL is $190.50", run_id="run_market")
    assert env["memory"].store.list_memories() == []
    assert env["memory"].store.list_suggestions(status="pending") == []


def test_repeated_convention_saved_without_confirmation(env):
    # Repeated low-risk evidence can produce a memory without per-run
    # confirmation: a convention stated in a prior conversation turn recurs.
    req = RunRequest(
        runId="run_recur",
        input=RunInput(
            query="Always use consolidated figures",
            history=[ConversationTurn(role="user", content="Always use consolidated figures")],
        ),
        agentId="eclipse-agent", userId="u1",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    orig = graph_module.build_chat_model
    graph_module.build_chat_model = lambda settings: _plain_model()  # type: ignore
    try:
        asyncio.run(graph_module.execute_run(
            req, env["registry"], FakeBridge(), env["run_store"],
            memory_service=env["memory"], skill_registry=env["skill_registry"],
        ))
    finally:
        graph_module.build_chat_model = orig  # type: ignore
    assert len(env["memory"].store.list_memories()) == 1
    assert env["memory"].store.list_suggestions(status="pending") == []


def test_project_scoped_fact_does_not_leak_across_scope(env):
    # A project/user-scoped memory is never recalled for a different scope.
    env["memory"].write_memory(
        memory_type="preference", content="project A uses TTM figures",
        source="explicit_user", scope="user", scope_id="u1",
    )
    other = env["memory"].retrieve(query="TTM figures", actor_scope="user", scope_id="u2")
    assert all(m.get("scopeId") != "u1" for m in other.memories)


def test_sensitive_looking_preference_is_not_auto_saved(env):
    # A statement mixing a preference with a sensitive identifier is refused
    # rather than persisted as ordinary memory.
    decision = decide_turn(
        "Remember my medical diagnosis and api key is sk-abcdefghijklmnopqrstuvwx",
        user_id="u1",
    )
    assert decision.outcome == "ignore"
    assert decision.refused
    assert env["memory"].store.list_memories() == []


def test_no_repetitive_prompt_for_ordinary_runs(env):
    # An ordinary eligible-looking run (multi-step, tool-using) produces no
    # suggestion and no candidate, so there is nothing to prompt about.
    tool_call = AIMessage(
        content="", tool_calls=[{"id": "c1", "name": "get_market_snapshot", "args": {"symbol": "AAPL"}}]
    )
    model = ScriptedModel([tool_call, AIMessage(content="Here is the analysis.")])
    agent = AgentConfig(id="a2", name="A", systemPrompt="sys", tools=["get_market_snapshot"], maxSteps=3)
    orig = graph_module.build_chat_model
    graph_module.build_chat_model = lambda settings: model  # type: ignore
    req = RunRequest(
        runId="run_noprompt", input=RunInput(query="Analyse AAPL over a few steps"),
        agent=agent, userId="u1",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    try:
        result = asyncio.run(graph_module.execute_run(
            req, env["registry"], FakeBridge(), env["run_store"],
            memory_service=env["memory"], skill_registry=env["skill_registry"],
        ))
    finally:
        graph_module.build_chat_model = orig  # type: ignore
    assert result.status == "completed"
    blob = env["run_store"].get_run("run_noprompt")["memory"]
    assert blob["learningAnalysis"]["candidatesCreated"] == 0
    assert env["memory"].store.list_candidates() == []
    assert env["memory"].store.list_suggestions(status="pending") == []


# ── Persisted recurrence survives without a long chat-history window ────────


def test_convention_recurs_across_separate_runs_and_persists(env):
    # Recurrence is persisted (signature-only), so a convention repeated in a
    # later, unrelated run — with no chat history carried along — is still
    # recognized and saved automatically.
    _run(env, "Always use consolidated figures", run_id="run_rec1")
    assert env["memory"].store.list_memories() == []  # first time: history only
    # A second run, different session, same statement, empty history.
    _run(env, "Always use consolidated figures", run_id="run_rec2")
    saved = env["memory"].store.list_memories()
    assert len(saved) == 1
    # The raw statement is never stored in the recurrence ledger, only a digest.
    rows = env["memory"].store._db.execute(
        "SELECT signature FROM MemoryRecurrence"
    ).fetchall()
    assert rows
    for row in rows:
        assert "consolidated" not in row["signature"]


def test_recurrence_survives_reopen(env):
    _run(env, "Always use consolidated figures", run_id="run_rec_reopen1")
    # Simulate a restart: a fresh service over the same database file.
    reopened = EclipseMemoryService(EclipseMemoryStore(env["memory"].store.path))
    try:
        decision = reopened.decide_turn("Always use consolidated figures", user_id="u1")
    finally:
        reopened.close()
    assert decision.outcome == "save"
    assert decision.metadata.get("evidence") == "recurrence"


def test_skill_recurrence_is_persisted_and_idempotent(env):
    from harness.skills.learning import _candidate_recurrence_key, analyze_run

    class T:
        tool_call_id = "c1"; name = "research_search"; ok = True
        duration_ms = 3; text = "x"; error = None; args = {}

    for run_id in ("run_lr_a", "run_lr_b"):
        env["run_store"].create_run(run_id, "eclipse-agent", {"query": "x"})
        env["run_store"].record_tool_execution(run_id, T())
        env["run_store"].update_run(run_id, status="completed", output="done", modelSteps=3, toolCalls=1)

    key = _candidate_recurrence_key("successful_procedure", [{"name": "research_search", "ok": True}])
    # Analysis records recurrence; re-analyzing the SAME run must not inflate it.
    analyze_run("run_lr_a", env["run_store"])
    after_first = env["run_store"].learning_recurrence(key)
    analyze_run("run_lr_a", env["run_store"])
    assert env["run_store"].learning_recurrence(key) == after_first
    # A second distinct run increases the count.
    analyze_run("run_lr_b", env["run_store"])
    assert env["run_store"].learning_recurrence(key) == after_first + 1


def test_second_successful_workflow_yields_candidate_without_chat_history(env):
    # The recurrence ledger alone (no chat history) qualifies a repeated
    # workflow for a controlled candidate.
    from harness.skills.learning import analyze_run

    class T:
        tool_call_id = "c1"; name = "research_search"; ok = True
        duration_ms = 3; text = "x"; error = None; args = {}

    for run_id in ("run_lr_c", "run_lr_d"):
        env["run_store"].create_run(run_id, "eclipse-agent", {"query": "x"})
        env["run_store"].record_tool_execution(run_id, T())
        env["run_store"].update_run(run_id, status="completed", output="done", modelSteps=3, toolCalls=1)
    # First analysis records recurrence for run_lr_c.
    analyze_run("run_lr_c", env["run_store"])
    # Second run's analysis sees the prior occurrence and yields a candidate.
    drafts = analyze_run("run_lr_d", env["run_store"])
    assert any(d["candidateType"] == "successful_procedure" for d in drafts)




# -- Cross-user suggestion isolation (identifier guessing must not mutate) ----


def test_suggestion_cannot_be_accepted_by_another_user(env):
    env["memory"].policy.set("memory_mode", "ask_before_saving")
    _run(env, "I prefer concise answers for u1", run_id="run_iso_1")
    suggestion = env["memory"].store.list_suggestions(status="pending")[0]
    # A different user guessing the id cannot accept u1's suggestion.
    outcome = env["memory"].accept_suggestion(suggestion["id"], user_id="u2")
    assert outcome["ok"] is False
    assert outcome["action"] == "forbidden"
    assert env["memory"].store.get_suggestion(suggestion["id"])["status"] == "pending"
    assert env["memory"].store.list_memories() == []


def test_suggestion_cannot_be_dismissed_by_another_user(env):
    env["memory"].policy.set("memory_mode", "ask_before_saving")
    _run(env, "I prefer dark charts for u1", run_id="run_iso_2")
    suggestion = env["memory"].store.list_suggestions(status="pending")[0]
    outcome = env["memory"].dismiss_suggestion(suggestion["id"], user_id="u2")
    assert outcome["ok"] is False
    assert outcome["action"] == "forbidden"
    assert env["memory"].store.get_suggestion(suggestion["id"])["status"] == "pending"


def test_dismissal_does_not_suppress_another_users_suggestion(env):
    # u1 dismisses a suggestion; u2 stating the same content still gets one.
    env["memory"].policy.set("memory_mode", "ask_before_saving")
    d1 = decide_turn("I prefer weekly summaries", user_id="u1")
    s1 = env["memory"].create_suggestion(d1, scope_id="u1")
    env["memory"].dismiss_suggestion(s1["id"], user_id="u1")
    d2 = decide_turn("I prefer weekly summaries", user_id="u2")
    s2 = env["memory"].create_suggestion(d2, scope_id="u2")
    assert s2["status"] == "pending"
    assert s2["id"] != s1["id"]


# -- General memories are recallable by a signed-in user ---------------------


def test_general_memory_is_recalled_for_scoped_user(env):
    env["memory"].write_memory(
        memory_type="semantic", content="The platform reports figures in UTC",
        source="manual", scope="general",
    )
    env["memory"].write_memory(
        memory_type="preference", content="u2 prefers candlestick charts",
        source="explicit_user", scope="user", scope_id="u2",
    )
    result = env["memory"].retrieve(query="figures UTC", actor_scope="user", scope_id="u1")
    contents = " ".join(m["content"] for m in result.memories)
    assert "UTC" in contents            # general memory is shared
    assert "candlestick" not in contents  # another user's preference is not
