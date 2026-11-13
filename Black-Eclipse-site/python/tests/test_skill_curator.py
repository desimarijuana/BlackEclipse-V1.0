"""W5.2 — the skill curator: reports, inert merges, and hard safety rules."""

from __future__ import annotations

import os

import pytest

from harness.eclipse_memory import EclipseMemoryStore
from harness.skills.curator import (
    CuratorPolicy,
    approve_proposal,
    reject_proposal,
    run_curator,
    scan,
)
from harness.skills.manifest import SkillManifest
from harness.skills.registry import SkillRegistry


def _manifest(skill_id, *, name, description, tags=None, permissions=None, origin="author"):
    return SkillManifest(**{
        "id": skill_id,
        "name": name,
        "version": "1.0.0",
        "description": description,
        "category": "research",
        "tags": tags or ["research"],
        "status": "enabled",
        "inputSchema": {"type": "object", "properties": {"objective": {"type": "string"}},
                        "required": ["objective"]},
        "outputSchema": {"type": "object", "properties": {"summary": {"type": "string"}},
                         "required": ["summary"]},
        "requiredTools": [],
        "requiredSkills": [],
        "permissions": permissions or ["data.read"],
        "riskLevel": "low",
        "author": "test",
        "origin": origin,
        "evaluationStatus": "not_evaluated",
    })


def _add(store, manifest):
    store.upsert_skill(
        skill_id=manifest.id, name=manifest.name, description=manifest.description,
        category=manifest.category, latest_version=manifest.version,
        status="enabled", tags=manifest.tags,
    )
    store.save_version(
        manifest.model_dump(), manifest.content_hash(),
        instructions="Shared procedure body.",
    )


@pytest.fixture()
def registry(tmp_path):
    store = EclipseMemoryStore(os.path.join(str(tmp_path), "eclipse-memory.db"))
    reg = SkillRegistry(store)
    _add(store, _manifest(
        "skill.drawdown", name="Drawdown ladder",
        description="Compute the drawdown ladder for a portfolio and report the worst peak-to-trough.",
        permissions=["data.read", "analysis.execute"],
    ))
    _add(store, _manifest(
        "skill.drawdown-copy", name="Drawdown ladder copy",
        description="Compute the drawdown ladder for a portfolio and report the worst peak-to-trough.",
        permissions=["data.read"],
    ))
    reg.load_stored("skill.drawdown")
    reg.load_stored("skill.drawdown-copy")
    yield reg, store
    store.close()


def test_dry_run_reports_and_changes_nothing(registry):
    reg, store = registry
    before = len(store.list_versions("skill.drawdown")) + len(store.list_versions("skill.drawdown-copy"))
    result = run_curator(store, reg, mode="dry_run")
    assert result["ok"] and result["mode"] == "dry_run"
    assert result["proposals"] >= 1
    after = len(store.list_versions("skill.drawdown")) + len(store.list_versions("skill.drawdown-copy"))
    assert after == before, "dry_run must not create a version"
    proposals = store.list_curator_proposals()
    assert all(p["status"] == "reported" for p in proposals)
    assert store.list_curator_runs()


def test_propose_creates_an_inert_merged_draft_with_intersection_permissions(registry):
    reg, store = registry
    result = run_curator(store, reg, mode="propose")
    assert result["ok"]
    proposals = [p for p in store.list_curator_proposals() if p["status"] == "proposed"]
    assert proposals, result
    proposal = proposals[0]
    draft_ref = proposal["proposedDraftId"]
    assert draft_ref
    skill_id, version = draft_ref.split("@")
    stored = store.get_version(skill_id, version)
    assert stored is not None
    assert stored["status"] == "draft"
    assert stored["baseVersion"] == "1.0.0"
    manifest = stored["manifest"]
    # Intersection: the copy only has data.read, so the merge cannot widen it.
    assert manifest["permissions"] == ["data.read"]
    # The active version is untouched.
    assert store.get_version("skill.drawdown", "1.0.0")["status"] == "enabled"


def test_approve_creates_a_draft_from_a_reported_proposal(registry):
    reg, store = registry
    run_curator(store, reg, mode="dry_run")
    proposal = store.list_curator_proposals()[0]
    result = approve_proposal(store, reg, proposal["id"], actor="operator")
    assert result["ok"]
    assert result["draft"]
    skill_id, version = result["draft"].split("@")
    assert store.get_version(skill_id, version)["status"] == "draft"
    assert store.get_curator_proposal(proposal["id"])["status"] == "approved"


def test_reject_is_terminal(registry):
    reg, store = registry
    run_curator(store, reg, mode="dry_run")
    proposal = store.list_curator_proposals()[0]
    assert reject_proposal(store, proposal["id"])["ok"]
    assert not approve_proposal(store, reg, proposal["id"])["ok"]


def test_compliance_and_pinned_skills_are_skipped(tmp_path):
    store = EclipseMemoryStore(os.path.join(str(tmp_path), "eclipse-memory.db"))
    reg = SkillRegistry(store)
    protected = _manifest(
        "skill.protected", name="Compliance report", description="Compliance audit report.",
        tags=["compliance"],
    )
    other = _manifest("skill.other", name="Compliance report", description="Compliance audit report.")
    _add(store, protected)
    _add(store, other)
    reg.load_stored("skill.protected")
    reg.load_stored("skill.other")
    proposals = scan(reg, policy=CuratorPolicy(mode="dry_run"))
    ids = {skill_id for proposal in proposals for skill_id in proposal.skillIds}
    assert "skill.protected" not in ids
    store.close()


def test_apply_hands_archive_suggestions_to_maintenance(registry):
    reg, store = registry
    result = run_curator(store, reg, mode="apply", maintenance_policy={})
    assert result["ok"]
    assert result["applied"] == 0, "report-only maintenance must not archive"
    assert result["maintenance"], "apply must run the one maintenance pass"


def test_merge_deduplicates_identical_body_lines(registry):
    reg, store = registry
    result = run_curator(store, reg, mode="propose")
    assert result["ok"]
    proposal = next(p for p in store.list_curator_proposals() if p["proposedDraftId"])
    skill_id, version = proposal["proposedDraftId"].split("@")
    stored = store.get_version(skill_id, version)
    instructions = stored["instructions"]
    # The fixture stores the same one-line body on both members; the merged
    # draft must carry it once, not twice.
    assert instructions.count("Shared procedure body.") == 1


def test_off_mode_writes_nothing(registry):
    reg, store = registry
    result = run_curator(store, reg, mode="off")
    assert result["ok"] and result["skipped"]
    assert store.list_curator_runs() == []
