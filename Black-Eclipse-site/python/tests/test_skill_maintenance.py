"""Milestone 1 — skill maintenance: staleness, usage, retirement, pinning.

Everything is driven off a temp DB; no network, no JDdS. The pass is
report-only by default and can only age enabled, unpinned, unused skills.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from harness.skills import SkillRegistry, SkillStore
from harness.skills.maintenance import (
    assess_skills,
    maintenance_report,
    run_skill_maintenance,
)
from harness.skills.permissions import OPERATOR_ACTOR


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-skills-maint-")
    s = SkillStore(os.path.join(directory, "eclipse-memory.db"))
    yield s
    s.close()


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    ) + "Z"


def _manifest(skill_id: str, version: str = "1.0.0", **overrides):
    base = {
        "id": skill_id,
        "name": skill_id,
        "version": version,
        "description": "A maintenance test skill.",
        "category": "research",
        "status": "enabled",
        "inputSchema": {"type": "object", "properties": {}},
        "requiredTools": [],
        "permissions": ["data.read"],
    }
    base.update(overrides)
    return base


def _seed(store, skill_id: str, version: str = "1.0.0", *, status: str = "enabled",
          created_days_ago: float = 0, pinned: bool = False):
    from harness.skills.manifest import SkillManifest

    manifest = SkillManifest(**_manifest(skill_id, version, status=status))
    store.upsert_skill(
        skill_id=skill_id, name=skill_id, description="d",
        category="research", latest_version=version, status=status, tags=[],
    )
    store.save_version(manifest.model_dump(), manifest.content_hash(), instructions="x")
    store.set_version_status(skill_id, version, status)
    if pinned:
        store.set_version_pinned(skill_id, version, True)
    store._db.execute(
        "UPDATE SkillVersion SET createdAt=?, updatedAt=? WHERE skillId=? AND version=?",
        (_iso(created_days_ago), _iso(created_days_ago), skill_id, version),
    )
    store._db.commit()


def _execution(store, skill_id: str, version: str, *, status: str = "succeeded",
               finished_days_ago: float = 0):
    execution_id = store.create_execution(
        run_id=f"run-{skill_id}-{version}-{status}-{finished_days_ago}",
        skill_id=skill_id, version=version, manifest_hash=None,
        parent_run_id=None, execution_mode="interactive", actor="test",
        input_data={},
    )
    store.finish_execution(execution_id, status=status, output="ok", duration_ms=1)
    store._db.execute(
        "UPDATE SkillExecution SET finishedAt=?, createdAt=? WHERE id=?",
        (_iso(finished_days_ago), _iso(finished_days_ago), execution_id),
    )
    store._db.commit()


def _policy(**overrides):
    base = {
        "skill_maintenance_enabled": False,
        "skill_maintenance_auto_archive": False,
        "skill_stale_after_days": 90,
        "skill_archive_after_days": 180,
    }
    base.update(overrides)
    return base


# ── Derivation from real execution rows ─────────────────────────────────────


def test_staleness_derived_from_execution_rows(store):
    _seed(store, "stale.a", created_days_ago=200)
    _execution(store, "stale.a", "1.0.0", finished_days_ago=200)
    _seed(store, "fresh.b", created_days_ago=1)
    _execution(store, "fresh.b", "1.0.0", finished_days_ago=1)

    assessments = {a["skillId"]: a for a in assess_skills(store, _policy())}
    assert assessments["stale.a"]["stale"] is True
    assert assessments["stale.a"]["lastUsedAt"] is not None
    assert assessments["stale.a"]["archiveEligible"] is True
    assert assessments["fresh.b"]["stale"] is False
    assert assessments["fresh.b"]["archiveEligible"] is False


def test_never_run_uses_anchor_not_zero(store):
    _seed(store, "never.ran", created_days_ago=300)
    assessment = next(a for a in assess_skills(store, _policy()) if a["skillId"] == "never.ran")
    assert assessment["everRun"] is False
    assert assessment["stale"] is True
    assert any("never executed" in r for r in assessment["reasons"])


def test_failed_execution_is_not_usage(store):
    _seed(store, "failed.only", created_days_ago=200)
    _execution(store, "failed.only", "1.0.0", status="failed", finished_days_ago=1)
    assessment = next(a for a in assess_skills(store, _policy()) if a["skillId"] == "failed.only")
    assert assessment["everRun"] is True
    assert assessment["successes"] == 0
    assert assessment["lastUsedAt"] is None
    # Age is measured from the anchor, so it still reads as stale.
    assert assessment["stale"] is True


# ── Pinning ─────────────────────────────────────────────────────────────────


def test_pinned_never_transitioned(store, registry_store=None):
    _seed(store, "pinned.skill", created_days_ago=400, pinned=True)
    registry = SkillRegistry(store)
    result = run_skill_maintenance(
        store, registry, _policy(skill_maintenance_enabled=True, skill_maintenance_auto_archive=True)
    )
    assert result["archived"] == []
    assert store.get_skill("pinned.skill")["status"] == "enabled"
    assert store.is_version_pinned("pinned.skill", "1.0.0") is True
    assessment = next(a for a in assess_skills(store, _policy()) if a["skillId"] == "pinned.skill")
    assert assessment["pinnedExempt"] is True


def test_pin_is_orthogonal_to_status(store):
    _seed(store, "stale.pinned", created_days_ago=400, status="disabled", pinned=True)
    assert store.is_version_pinned("stale.pinned", "1.0.0") is True
    assert store.get_skill("stale.pinned")["status"] == "disabled"


def test_pin_survives_reopen():
    directory = tempfile.mkdtemp(prefix="be-skills-pin-")
    path = os.path.join(directory, "eclipse-memory.db")
    first = SkillStore(path)
    _seed(first, "reopen.pin", created_days_ago=400, pinned=True)
    first.close()

    second = SkillStore(path)
    try:
        assert second.is_version_pinned("reopen.pin", "1.0.0") is True
        assert second.get_skill("reopen.pin") is not None
    finally:
        second.close()


# ── Archive is reversible ───────────────────────────────────────────────────


def test_archive_is_reversible(store):
    _seed(store, "old.skill", created_days_ago=400)
    registry = SkillRegistry(store)
    result = run_skill_maintenance(
        store, registry, _policy(skill_maintenance_enabled=True, skill_maintenance_auto_archive=True)
    )
    assert len(result["archived"]) == 1
    # Retirement persists as the distinct `archived` lifecycle state.
    assert store.get_skill("old.skill")["status"] == "archived"

    # Restorable through the existing lifecycle machinery: register the skill in
    # the registry and re-enable the version.
    from harness.skills.loader import LoadedSkill
    from harness.skills.manifest import SkillManifest

    registry.register(LoadedSkill(
        manifest=SkillManifest(**_manifest("old.skill")), folder="",
        instructions_path=None, instructions_text="x", authored=True, provenance="profile",
    ))
    restored = registry.set_status("old.skill", "enabled", OPERATOR_ACTOR, version="1.0.0")
    assert restored["ok"] is True
    assert store.get_skill("old.skill")["status"] == "enabled"


def test_report_only_default_changes_nothing(store):
    _seed(store, "old.skill", created_days_ago=400)
    registry = SkillRegistry(store)
    result = run_skill_maintenance(store, registry, _policy())
    assert result["reportOnly"] is True
    assert result["archived"] == []
    assert store.get_skill("old.skill")["status"] == "enabled"
    assert result["stale"] == 1
    assert result["archiveEligible"] == 1


def test_idempotent_rerun(store):
    _seed(store, "old.skill", created_days_ago=400)
    registry = SkillRegistry(store)
    policy = _policy(skill_maintenance_enabled=True, skill_maintenance_auto_archive=True)
    first = run_skill_maintenance(store, registry, policy)
    second = run_skill_maintenance(store, registry, policy)
    assert len(first["archived"]) == 1
    assert second["archived"] == []


def test_pass_never_raises_on_unreadable_store(store):
    class Broken:
        def _db(self):
            raise RuntimeError("boom")

    fake = type("Fake", (), {"_db": property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))})()
    result = run_skill_maintenance(fake, None, _policy())
    assert result["ok"] is False
    assert "error" in result


def test_report_has_no_content(store):
    _seed(store, "old.skill", created_days_ago=400)
    report = maintenance_report(store, _policy())
    assert report["reportOnly"] is True
    assert report["counts"]["stale"] == 1
    for item in report["recommendations"]:
        assert "content" not in item


def test_scope_isolation_across_skills(store):
    _seed(store, "a.stale", created_days_ago=400)
    _seed(store, "b.fresh", created_days_ago=1)
    assessments = {a["skillId"]: a for a in assess_skills(store, _policy())}
    assert assessments["a.stale"]["stale"] is True
    assert assessments["b.fresh"]["stale"] is False
