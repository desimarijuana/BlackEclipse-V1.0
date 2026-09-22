"""Phase 3-A — user skill authoring tests.

Covers creating, editing (new version), deleting, persistence across restart,
and the safety gates (safe permissions, real tools, operator-only, built-ins
immutable). The agent's tools must ALSO be able to use a user skill.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.eclipse_memory import EclipseMemoryStore
from harness.finance_tools import register_finance_tools
from harness.retrieval_tools import register_retrieval_tools
from harness.schemas import ModelSettings
from harness.skills import Actor, SkillRegistry
from harness.skills.authoring import SkillAuthoringError
from harness.skills.permissions import OPERATOR_ACTOR
from harness.tools import DataBridge, ToolRegistry


def _registry(path: str) -> SkillRegistry:
    store = EclipseMemoryStore(path)
    registry = SkillRegistry(store)
    tools = ToolRegistry()
    register_finance_tools(tools)
    register_retrieval_tools(tools)
    registry.attach_tool_registry(tools)
    registry.load_all()
    return registry


@pytest.fixture()
def registry():
    directory = tempfile.mkdtemp(prefix="be-authoring-")
    reg = _registry(os.path.join(directory, "eclipse-memory.db"))
    yield reg
    reg.store.close()


# ── Create ──────────────────────────────────────────────────────────────────


def test_create_user_skill(registry):
    result = registry.create_user_skill(
        name="Quote Checker", description="Check a quote",
        instructions="1. Get the quote.\n2. Report it.",
        required_tools=["market_get_quote"], permissions=["data.read"],
    )
    assert result["skillId"].startswith("user.")
    assert result["status"] == "enabled"
    loaded = registry.get(result["skillId"])
    assert loaded is not None and loaded.authored
    assert "Get the quote" in loaded.load_instructions()
    assert registry.validate(result["skillId"])["ok"]


def test_created_skill_is_discoverable(registry):
    registry.create_user_skill(name="Earnings Reader", description="Read earnings",
                               instructions="1. step")
    found = registry.discover(query="earnings reader")
    assert any(s["id"].startswith("user.") for s in found)
    # The library summary exposes the author origin for the UI badge.
    summary = [s for s in registry.list_summaries() if s["id"].startswith("user.")]
    assert summary and summary[0]["origin"] == "author"


def test_create_rejects_unknown_tool(registry):
    with pytest.raises(SkillAuthoringError):
        registry.create_user_skill(name="X", description="d", instructions="i",
                                   required_tools=["does_not_exist"])


def test_create_rejects_forbidden_permission(registry):
    with pytest.raises(SkillAuthoringError):
        registry.create_user_skill(name="X", description="d", instructions="i",
                                   permissions=["trade.execute"])
    with pytest.raises(SkillAuthoringError):
        registry.create_user_skill(name="X", description="d", instructions="i",
                                   permissions=["production.modify"])


def test_create_rejects_operator_permission(registry):
    # skill.enable is operator-only, never part of a user skill's surface.
    with pytest.raises(SkillAuthoringError):
        registry.create_user_skill(name="X", description="d", instructions="i",
                                   permissions=["skill.enable"])


def test_create_rejects_empty_instructions(registry):
    with pytest.raises(SkillAuthoringError):
        registry.create_user_skill(name="X", description="d", instructions="   ")


def test_create_rejects_duplicate_id(registry):
    registry.create_user_skill(name="Dup", description="d", instructions="i")
    with pytest.raises(SkillAuthoringError):
        registry.create_user_skill(name="Dup", description="d", instructions="i",
                                   skill_id="user.dup")


def test_reserved_prefix_rejected(registry):
    with pytest.raises(SkillAuthoringError):
        registry.create_user_skill(name="X", description="d", instructions="i",
                                   skill_id="learned.x")


# ── Edit ────────────────────────────────────────────────────────────────────


def test_edit_creates_new_version(registry):
    created = registry.create_user_skill(name="Edit Me", description="d", instructions="v1")
    sid = created["skillId"]
    updated = registry.update_user_skill(sid, instructions="v2 procedure")
    assert updated["version"] == "1.1.0"
    # Both versions remain (the enabled version was not mutated).
    versions = {v["version"] for v in registry.store.list_versions(sid)}
    assert "1.0.0" in versions and "1.1.0" in versions
    assert "v2 procedure" in registry.get(sid).load_instructions()
    assert registry.store.get_skill(sid)["latestVersion"] == "1.1.0"


def test_cannot_edit_builtin(registry):
    with pytest.raises(SkillAuthoringError):
        registry.update_user_skill("research.planning", instructions="hijack")


# ── Delete ──────────────────────────────────────────────────────────────────


def test_delete_user_skill(registry):
    created = registry.create_user_skill(name="Delete Me", description="d", instructions="i")
    result = registry.delete_user_skill(created["skillId"])
    assert result["deleted"] is True
    assert registry.get(created["skillId"]) is None
    assert registry.store.get_user_skill(created["skillId"]) is None


def test_cannot_delete_builtin(registry):
    with pytest.raises(SkillAuthoringError):
        registry.delete_user_skill("research.planning")


def test_delete_referenced_skill_deprecates_instead(registry):
    created = registry.create_user_skill(name="Used Skill", description="d", instructions="i")
    sid = created["skillId"]
    # Simulate execution history.
    registry.store.create_execution(
        run_id="run_x", skill_id=sid, version="1.0.0", manifest_hash="h",
        parent_run_id=None, execution_mode="interactive", actor="local", input_data={},
    )
    result = registry.delete_user_skill(sid)
    assert result["deleted"] is False
    assert result["status"] == "deprecated"
    assert registry.store.get_skill(sid) is not None  # retained for audit


# ── Persistence ─────────────────────────────────────────────────────────────


def test_user_skill_survives_restart():
    directory = tempfile.mkdtemp(prefix="be-authoring-restart-")
    path = os.path.join(directory, "eclipse-memory.db")
    reg = _registry(path)
    reg.create_user_skill(name="Persisted", description="d", instructions="survives",
                          required_tools=["market_get_quote"])
    reg.store.close()

    reg2 = _registry(path)
    try:
        found = [s for s in reg2.all_manifests() if s.id.startswith("user.")]
        assert found, "user skill should survive a restart"
        assert "survives" in reg2.get(found[0].id).load_instructions()
        assert reg2.validate(found[0].id)["ok"]
    finally:
        reg2.store.close()


def test_enabled_status_preserved_across_reload():
    directory = tempfile.mkdtemp(prefix="be-authoring-status-")
    path = os.path.join(directory, "eclipse-memory.db")
    reg = _registry(path)
    created = reg.create_user_skill(name="Status", description="d", instructions="i")
    reg.set_status(created["skillId"], "disabled", OPERATOR_ACTOR)
    reg.store.close()

    reg2 = _registry(path)
    try:
        assert reg2.store.get_skill(created["skillId"])["status"] == "disabled"
    finally:
        reg2.store.close()
