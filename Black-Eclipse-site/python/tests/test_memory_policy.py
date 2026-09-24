"""Phase 3-M (next) — policy, mistake analysis, and auto-detection tests.

Covers the configurable policy layer (safe bounds, locked values, persistence)
and the deterministic mistake-analysis service, plus policy-gated automatic
candidate detection. No model, no network.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.mistakes import analyze_run_for_mistakes, capture_mistakes
from harness.eclipse_memory.policy import PolicyError
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def env():
    directory = tempfile.mkdtemp(prefix="be-mem-policy-")
    memory = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    run_store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield {"memory": memory, "run_store": run_store}
    memory.close()
    run_store.close()


# ── Policy ──────────────────────────────────────────────────────────────────


def test_policy_defaults(env):
    settings = env["memory"].policy.get_all()
    # Routine automatic capture, automatic candidate detection and automatic
    # suggestions are OFF by default: completing a run is not proof of a
    # reusable lesson, and incidental preferences are not silently saved.
    # Explicit "remember/forget/correct" commands still work (separate path).
    assert settings["auto_candidate_detection"] is False
    assert settings["auto_capture_enabled"] is False
    assert settings["auto_suggest_enabled"] is False
    assert settings["context_budget_chars"] == 4000
    assert settings["max_memories"] == 0
    # Automatic promotion remains structurally impossible.
    assert settings["auto_promote_low_risk"] is False


def test_policy_set_and_persist(env):
    env["memory"].policy.set("context_budget_chars", 2500)
    assert env["memory"].policy.get("context_budget_chars") == 2500
    # A reopen sees the override.
    reopened = EclipseMemoryService(EclipseMemoryStore(env["memory"].store.path))
    try:
        assert reopened.policy.get("context_budget_chars") == 2500
    finally:
        reopened.close()


def test_policy_rejects_unknown_key(env):
    with pytest.raises(PolicyError):
        env["memory"].policy.set("nonsense", 1)


def test_policy_rejects_out_of_range(env):
    with pytest.raises(PolicyError):
        env["memory"].policy.set("context_budget_chars", 10_000_000)
    with pytest.raises(PolicyError):
        env["memory"].policy.set("candidate_confidence_threshold", 5)


def test_policy_cannot_unlock_auto_promotion(env):
    with pytest.raises(PolicyError):
        env["memory"].policy.set("auto_promote_low_risk", True)


def test_policy_reset(env):
    env["memory"].policy.set("retrieval_limit", 20)
    env["memory"].policy.reset("retrieval_limit")
    assert env["memory"].policy.get("retrieval_limit") == 8


def test_stored_true_override_is_migrated_to_safe_default(tmp_path):
    # A persisted `true` override from the old (over-saving) default must not
    # continue the unwanted behaviour: migration 5 deletes it so the new safe
    # default applies. Other overrides are preserved.
    import sqlite3

    from harness.eclipse_memory.db import now_iso

    path = os.path.join(str(tmp_path), "eclipse-memory.db")
    # Build a schema-v4 database with an unsafe stored override.
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE SchemaMigration (version INTEGER PRIMARY KEY, appliedAt TEXT NOT NULL)")
    for version, statements in __import__("harness.eclipse_memory.schema", fromlist=["MIGRATIONS"]).MIGRATIONS:
        if version > 4:
            continue
        for statement in statements:
            conn.executescript(statement)
        conn.execute("INSERT OR REPLACE INTO SchemaMigration VALUES (?, ?)", (version, now_iso()))
    conn.execute(
        "INSERT INTO MemoryPolicy (key, value, updatedAt) VALUES (?, ?, ?)",
        ("auto_capture_enabled", "true", now_iso()),
    )
    conn.execute(
        "INSERT INTO MemoryPolicy (key, value, updatedAt) VALUES (?, ?, ?)",
        ("auto_candidate_detection", "true", now_iso()),
    )
    conn.execute(
        "INSERT INTO MemoryPolicy (key, value, updatedAt) VALUES (?, ?, ?)",
        ("retrieval_limit", "20", now_iso()),
    )
    conn.commit()
    conn.close()

    service = EclipseMemoryService(EclipseMemoryStore(path))
    try:
        assert service.migration_status()["upToDate"] is True
        settings = service.policy.get_all()
        assert settings["auto_capture_enabled"] is False
        assert settings["auto_candidate_detection"] is False
        # An unrelated operator override is preserved.
        assert settings["retrieval_limit"] == 20
        # The reset is observable.
        rows = service.store._db.execute(
            "SELECT key, previousValue FROM MemoryPolicyMigration"
        ).fetchall()
        keys = {r["key"] for r in rows}
        assert {"auto_capture_enabled", "auto_candidate_detection"} <= keys
        # A stored MemoryPolicy row for the unsafe key is gone.
        remaining = {
            r["key"] for r in service.store._db.execute("SELECT key FROM MemoryPolicy").fetchall()
        }
        assert "auto_capture_enabled" not in remaining
    finally:
        service.close()


def test_retrieval_uses_policy_budget(env):
    # A large budget change is observable in diagnostics.
    env["memory"].policy.set("context_budget_chars", 500)
    env["memory"].write_memory(memory_type="semantic", content="x" * 400, source="manual")
    result = env["memory"].retrieve(query="x")
    assert result.diagnostics["budgetChars"] == 500


def test_retrieval_explicit_value_overrides_policy(env):
    env["memory"].policy.set("context_budget_chars", 500)
    result = env["memory"].retrieve(query="x", budget_chars=1234)
    assert result.diagnostics["budgetChars"] == 1234


# ── Mistake analysis ────────────────────────────────────────────────────────


def _tool(name, ok, code=None, text=None):
    class T:
        tool_call_id = f"c_{name}"
        duration_ms = 5
        error = None if ok else type("E", (), {
            "model_dump_json": lambda self: __import__("json").dumps({"code": code}),
            "code": code,
        })()
        args = {}

    T.name = name
    T.ok = ok
    T.text = text if text is not None else ("ok" if ok else f"Tool error ({code})")
    return T()


def test_tool_failure_detected(env):
    env["run_store"].create_run("run_1", "eclipse-agent", {"query": "x"})
    env["run_store"].record_tool_execution("run_1", _tool("get_fundamentals", False, "TOOL_ERROR"))
    env["run_store"].update_run("run_1", status="failed")
    cats = [m["category"] for m in analyze_run_for_mistakes("run_1", env["run_store"])]
    assert "tool_failure" in cats


def test_repeated_failure_detected(env):
    env["run_store"].create_run("run_2", "eclipse-agent", {"query": "x"})
    env["run_store"].record_tool_execution("run_2", _tool("market_get_quote", False, "TOOL_ERROR"))
    env["run_store"].record_tool_execution("run_2", _tool("market_get_quote", False, "TOOL_ERROR"))
    env["run_store"].update_run("run_2", status="failed")
    cats = [m["category"] for m in analyze_run_for_mistakes("run_2", env["run_store"])]
    assert "repeated_failure" in cats


def test_unsupported_claim_detected(env):
    env["run_store"].create_run("run_3", "eclipse-agent", {"query": "x"})
    env["run_store"].update_run("run_3", status="completed", output="Revenue was 1.2B in FY24", modelSteps=1)
    cats = [m["category"] for m in analyze_run_for_mistakes("run_3", env["run_store"])]
    assert "unsupported_claim" in cats


def test_missing_data_undisclosed_detected(env):
    env["run_store"].create_run("run_4", "eclipse-agent", {"query": "x"})
    env["run_store"].record_tool_execution(
        "run_4", _tool("market_get_ohlcv", False, "TOOL_ERROR", text="UNAVAILABLE — no data")
    )
    env["run_store"].update_run("run_4", status="completed", output="The 5y return is strong.", modelSteps=1)
    cats = [m["category"] for m in analyze_run_for_mistakes("run_4", env["run_store"])]
    assert "missing_data_undisclosed" in cats


def test_disclosed_unavailability_is_not_a_mistake(env):
    env["run_store"].create_run("run_5", "eclipse-agent", {"query": "x"})
    env["run_store"].record_tool_execution(
        "run_5", _tool("market_get_ohlcv", False, "TOOL_ERROR", text="UNAVAILABLE — no data")
    )
    env["run_store"].update_run(
        "run_5", status="completed",
        output="Historical prices are unavailable, so I cannot compute the return.", modelSteps=1,
    )
    cats = [m["category"] for m in analyze_run_for_mistakes("run_5", env["run_store"])]
    assert "missing_data_undisclosed" not in cats


def test_clean_run_yields_no_mistakes(env):
    env["run_store"].create_run("run_6", "eclipse-agent", {"query": "x"})
    env["run_store"].record_tool_execution("run_6", _tool("research_search", True))
    env["run_store"].update_run("run_6", status="completed", output="Here is a summary with sources.", modelSteps=2)
    assert analyze_run_for_mistakes("run_6", env["run_store"]) == []


def test_mistake_capture_is_idempotent(env):
    env["run_store"].create_run("run_7", "eclipse-agent", {"query": "x"})
    env["run_store"].record_tool_execution("run_7", _tool("get_news", False, "TOOL_ERROR"))
    env["run_store"].update_run("run_7", status="failed")
    first = capture_mistakes("run_7", env["run_store"], env["memory"].store)
    assert first
    second = capture_mistakes("run_7", env["run_store"], env["memory"].store)
    assert second == []


# ── Auto candidate detection (policy-gated) ─────────────────────────────────


def test_auto_detection_can_be_disabled_by_policy(env):
    env["memory"].policy.set("auto_candidate_detection", False)
    env["run_store"].create_run("run_8", "eclipse-agent", {"query": "x"})
    env["run_store"].record_tool_execution("run_8", _tool("get_fundamentals", False, "TOOL_ERROR"))
    env["run_store"].record_tool_execution("run_8", _tool("research_search", True))
    env["run_store"].update_run("run_8", status="completed", output="done", modelSteps=3)
    result = env["memory"].analyze_run("run_8", env["run_store"])
    assert result["candidateDetection"] == "disabled by policy"
    assert result["candidatesCreated"] == 0


def test_auto_detection_off_by_default_creates_no_candidates(env):
    env["run_store"].create_run("run_8b", "eclipse-agent", {"query": "x"})
    env["run_store"].record_tool_execution("run_8b", _tool("get_fundamentals", False, "TOOL_ERROR"))
    env["run_store"].record_tool_execution("run_8b", _tool("research_search", True))
    env["run_store"].update_run("run_8b", status="completed", output="Recovered.", modelSteps=3)
    result = env["memory"].analyze_run("run_8b", env["run_store"])
    # A single tool-using run is NOT automatically a learning candidate.
    assert result["candidateDetection"] == "disabled by policy"
    assert result["candidatesCreated"] == 0
    assert env["memory"].store.list_candidates() == []


def test_auto_detection_opt_in_creates_only_inert_candidates(env):
    env["memory"].policy.set("auto_candidate_detection", True)
    env["run_store"].create_run("run_8c", "eclipse-agent", {"query": "x"})
    env["run_store"].record_tool_execution("run_8c", _tool("get_fundamentals", False, "TOOL_ERROR"))
    env["run_store"].record_tool_execution("run_8c", _tool("research_search", True))
    env["run_store"].update_run("run_8c", status="completed", output="Recovered.", modelSteps=3)
    result = env["memory"].analyze_run("run_8c", env["run_store"])
    assert result["candidatesCreated"] >= 1
    for candidate in env["memory"].store.list_candidates():
        assert candidate["resultingSkillId"] is None  # inert


def test_auto_detection_creates_inert_candidates(env):
    env["memory"].policy.set("auto_candidate_detection", True)
    env["memory"].policy.set("candidate_confidence_threshold", 0.1)
    env["run_store"].create_run("run_9", "eclipse-agent", {"query": "x"})
    env["run_store"].append_event("run_9", "run.started", 1)
    env["run_store"].record_tool_execution("run_9", _tool("get_fundamentals", False, "TOOL_ERROR"))
    env["run_store"].record_tool_execution("run_9", _tool("research_search", True))
    env["run_store"].update_run("run_9", status="completed", output="Recovered with research.", modelSteps=3)
    result = env["memory"].analyze_run("run_9", env["run_store"])
    assert result["candidatesCreated"] >= 1
    # Created candidates are inert — no resulting skill was enabled.
    for candidate in env["memory"].store.list_candidates():
        assert candidate["resultingSkillId"] is None


def test_auto_detection_respects_confidence_threshold(env):
    env["memory"].policy.set("auto_candidate_detection", True)
    env["memory"].policy.set("candidate_confidence_threshold", 0.99)
    env["run_store"].create_run("run_10", "eclipse-agent", {"query": "x"})
    env["run_store"].record_tool_execution("run_10", _tool("get_fundamentals", False, "TOOL_ERROR"))
    env["run_store"].record_tool_execution("run_10", _tool("research_search", True))
    env["run_store"].update_run("run_10", status="completed", output="done", modelSteps=3)
    result = env["memory"].analyze_run("run_10", env["run_store"])
    assert result["candidatesCreated"] == 0
