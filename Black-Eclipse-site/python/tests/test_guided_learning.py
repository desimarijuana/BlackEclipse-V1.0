"""Guided `/learn`: inert drafts, sanitization, one-off safety, operator gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.eclipse_memory import EclipseMemoryService
from harness.skills.learn import (
    LearnRequest,
    build_learn_draft,
    learn_from_source,
    lint_skill_content,
    sanitize_skill_content,
)
from harness.skills.registry import SkillRegistry


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


def _registry(service, tmp_path):
    root = tmp_path / "lib"
    folder = root / "research" / "planning"
    folder.mkdir(parents=True)
    (folder / "skill.json").write_text(json.dumps({
        "id": "research.planning", "name": "Planning", "version": "1.0.0",
        "description": "plan", "category": "research", "status": "enabled",
        "requiredTools": ["research_search"],
    }), encoding="utf-8")
    (folder / "SKILL.md").write_text("plan", encoding="utf-8")
    reg = SkillRegistry(service.store)
    reg.load_all(root=str(root), project_discovery=False)
    return reg


def test_secret_is_sanitized():
    clean, removed = sanitize_skill_content("Use api_key: sk-abc123 then continue")
    assert "secret" in removed
    assert "sk-abc123" not in clean


def test_issue_numbers_are_removed():
    clean, removed = sanitize_skill_content("Fix issue #1234 before deploying")
    assert "issue_number" in removed
    assert "#1234" not in clean


def test_transcript_lines_are_stripped():
    clean, removed = sanitize_skill_content("User: do the thing\nAssistant: done\nAlways verify.")
    assert "raw_transcript" in removed
    assert "User:" not in clean
    assert "Always verify." in clean


def test_lint_flags_dates_without_removing():
    codes = lint_skill_content("On 2026-01-15 we migrated the database")
    assert "irrelevant_date" in codes


def test_build_learn_draft_is_deterministic_and_inert_shape():
    req = LearnRequest(
        source_kind="document", title="Deploy staging",
        objective="Deploy to staging. Verify health. Roll back on failure.",
        tools=["research_search"], source_run_id="run-1",
    )
    a = build_learn_draft(req)
    b = build_learn_draft(req)
    assert a == b
    assert a["procedure"]
    assert a["sourceKind"] == "document"


def test_learn_requires_operator(service, tmp_path):
    registry = _registry(service, tmp_path)
    result = learn_from_source(
        LearnRequest(source_kind="run", title="X", objective="do x"),
        service.store, available_tools=["research_search"], actor_is_operator=False,
    )
    assert result["ok"] is False


def test_learn_creates_inert_draft(service, tmp_path):
    registry = _registry(service, tmp_path)
    result = learn_from_source(
        LearnRequest(
            source_kind="run", title="Weekly review",
            objective="Collect sources. Verify. Summarize.", tools=["research_search"],
            source_run_id="run-7",
        ),
        service.store, available_tools=["research_search"], actor_is_operator=True,
    )
    assert result["ok"] is True
    draft = result["draft"]
    assert draft["status"] == "draft"
    assert draft["evaluationStatus"] == "not_evaluated"
    assert draft["origin"] == "learning"
    # Draft skill exists in the store but is NOT enabled.
    skill = service.store.get_skill(draft["id"])
    assert skill["status"] == "draft"


def test_learn_drops_unavailable_tools(service, tmp_path):
    registry = _registry(service, tmp_path)
    result = learn_from_source(
        LearnRequest(source_kind="run", title="Y", objective="do y", tools=["not_a_tool"]),
        service.store, available_tools=["research_search"], actor_is_operator=True,
    )
    assert result["ok"] is True
    assert "not_a_tool" not in result["draft"]["requiredTools"]
