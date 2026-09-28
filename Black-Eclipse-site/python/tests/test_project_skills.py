"""Project-local skills: trust, precedence, provenance, untrust (Phase 2).

Every test uses a temp DB and a temp project root — the developer's real
eclipse-memory.db and repo skills are never touched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from harness.eclipse_memory import EclipseMemoryService
from harness.skills.registry import SkillRegistry


def _write_skill(root: Path, subdir: str, skill_id: str, *, instructions: str = "Do the thing.") -> Path:
    folder = root / subdir / skill_id.split(".")[-1]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "skill.json").write_text(
        json.dumps({
            "id": skill_id,
            "name": skill_id,
            "version": "1.0.0",
            "description": "A project skill.",
            "category": "research",
            "status": "enabled",
            "instructions": "SKILL.md",
            "permissions": ["data.read"],
            "requiredTools": [],
        }),
        encoding="utf-8",
    )
    (folder / "SKILL.md").write_text(instructions, encoding="utf-8")
    return folder


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    return root


def test_untrusted_project_is_not_loaded(service, project):
    _write_skill(project, ".black-eclipse/skills", "proj.deploy")
    registry = SkillRegistry(service.store)
    registry.load_all(project_root=str(project), project_discovery=True)
    assert registry.manifest("proj.deploy") is None
    notices = registry.project_notices()
    assert any("not trusted" in n for n in notices)


def test_trusted_project_is_loaded_and_tagged(service, project):
    from harness.skills.project_skills import trust_root

    _write_skill(project, ".black-eclipse/skills", "proj.deploy")
    trust_root(service.store, str(project))
    registry = SkillRegistry(service.store)
    registry.load_all(project_root=str(project), project_discovery=True)
    assert registry.manifest("proj.deploy") is not None
    assert registry.provenance_of("proj.deploy") == "project"


def test_project_takes_precedence_over_bundled(service, project, tmp_path):
    from harness.skills.project_skills import trust_root
    from harness.skills.loader import load_catalog

    # A bundled skill id that the project shadows.
    bundled_root = tmp_path / "bundled"
    _write_skill(bundled_root, "", "research.planning", instructions="BUNDLED")
    _write_skill(project, ".black-eclipse/skills", "research.planning", instructions="PROJECT")
    trust_root(service.store, str(project))

    registry = SkillRegistry(service.store)
    registry.load_all(root=str(bundled_root), project_root=str(project), project_discovery=True)
    entry = registry.get("research.planning")
    assert entry is not None
    assert entry.load_instructions() == "PROJECT"
    assert entry.provenance == "project"


def test_untrust_immediately_stops_injection(service, project):
    from harness.skills.project_skills import trust_root, untrust_root

    _write_skill(project, ".black-eclipse/skills", "proj.deploy")
    trust_root(service.store, str(project))
    registry = SkillRegistry(service.store)
    registry.load_all(project_root=str(project), project_discovery=True)
    assert registry.manifest("proj.deploy") is not None

    untrust_root(service.store, str(project))
    registry.load_all(project_root=str(project), project_discovery=True)
    assert registry.manifest("proj.deploy") is None


def test_discovery_off_loads_nothing(service, project):
    from harness.skills.project_skills import trust_root

    _write_skill(project, ".black-eclipse/skills", "proj.deploy")
    trust_root(service.store, str(project))
    registry = SkillRegistry(service.store)
    registry.load_all(project_root=str(project), project_discovery=False)
    assert registry.manifest("proj.deploy") is None
    assert registry.project_notices() == []


def test_agents_dir_convention_is_scanned(service, project):
    from harness.skills.project_skills import trust_root

    _write_skill(project, ".agents/skills", "proj.convention")
    trust_root(service.store, str(project))
    registry = SkillRegistry(service.store)
    registry.load_all(project_root=str(project), project_discovery=True)
    assert registry.manifest("proj.convention") is not None


def test_project_skill_cannot_grant_blocked_permission(service, project):
    """A project skill declaring a forbidden permission stays well-formed but
    can never be enabled/executed — the permission gate is unchanged."""
    from harness.skills.project_skills import trust_root
    from harness.skills.permissions import OPERATOR_ACTOR, can_enable

    folder = project / ".black-eclipse" / "skills" / "evil"
    folder.mkdir(parents=True)
    (folder / "skill.json").write_text(json.dumps({
        "id": "proj.evil",
        "name": "evil",
        "version": "1.0.0",
        "description": "tries to trade",
        "category": "finance",
        "status": "enabled",
        "permissions": ["trade.execute"],
    }), encoding="utf-8")
    (folder / "SKILL.md").write_text("trade now", encoding="utf-8")
    trust_root(service.store, str(project))
    registry = SkillRegistry(service.store)
    registry.load_all(project_root=str(project), project_discovery=True)

    manifest = registry.manifest("proj.evil")
    assert manifest is not None
    decision = can_enable(manifest.permissions, OPERATOR_ACTOR)
    assert decision.allowed is False


def test_trust_is_per_absolute_path(service, project, tmp_path):
    from harness.skills.project_skills import is_trusted, trust_root

    other = tmp_path / "other"
    (other / ".git").mkdir(parents=True)
    trust_root(service.store, str(project))
    assert is_trusted(service.store, str(project)) is True
    assert is_trusted(service.store, str(other)) is False


def test_find_project_root_walks_to_git(project):
    from harness.skills.project_skills import find_project_root

    nested = project / "a" / "b"
    nested.mkdir(parents=True)
    assert find_project_root(str(nested)) == os.path.abspath(str(project))


# -- Drift detection (Phase 2, remaining-gaps plan) --------------------------


def test_unchanged_trusted_project_stays_loaded(service, project):
    from harness.skills.project_skills import trust_root

    _write_skill(project, ".black-eclipse/skills", "proj.deploy")
    trust_root(service.store, str(project))
    reg = SkillRegistry(service.store)
    reg.load_all(project_root=str(project), project_discovery=True)
    assert reg.manifest("proj.deploy") is not None
    assert reg.project_drift() is False


def test_instruction_change_quarantines_trusted_project(service, project):
    from harness.skills.project_skills import trust_root

    folder = _write_skill(project, ".black-eclipse/skills", "proj.deploy", instructions="Original procedure.")
    trust_root(service.store, str(project))
    reg = SkillRegistry(service.store)
    reg.load_all(project_root=str(project), project_discovery=True)
    assert reg.manifest("proj.deploy") is not None

    # Change the prose (a material behavior change) without re-approving.
    (folder / "SKILL.md").write_text("Malicious new procedure.", encoding="utf-8")
    reg.load_all(project_root=str(project), project_discovery=True)
    assert reg.manifest("proj.deploy") is None
    assert reg.project_drift() is True
    assert any("quarantined" in n for n in reg.project_notices())


def test_manifest_change_quarantines_trusted_project(service, project):
    from harness.skills.project_skills import trust_root

    folder = _write_skill(project, ".black-eclipse/skills", "proj.deploy")
    trust_root(service.store, str(project))
    manifest_path = folder / "skill.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["description"] = "changed"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    reg = SkillRegistry(service.store)
    reg.load_all(project_root=str(project), project_discovery=True)
    assert reg.manifest("proj.deploy") is None
    assert reg.project_drift() is True


def test_reapprove_clears_drift(service, project):
    from harness.skills.project_skills import trust_root

    folder = _write_skill(project, ".black-eclipse/skills", "proj.deploy", instructions="v1")
    trust_root(service.store, str(project))
    (folder / "SKILL.md").write_text("v2", encoding="utf-8")
    reg = SkillRegistry(service.store)
    reg.load_all(project_root=str(project), project_discovery=True)
    assert reg.project_drift() is True

    # Operator re-approves: re-baselines the hash.
    trust_root(service.store, str(project))
    reg.load_all(project_root=str(project), project_discovery=True)
    assert reg.manifest("proj.deploy") is not None
    assert reg.project_drift() is False


def test_untrust_after_drift_still_blocks(service, project):
    from harness.skills.project_skills import trust_root, untrust_root

    folder = _write_skill(project, ".black-eclipse/skills", "proj.deploy", instructions="v1")
    trust_root(service.store, str(project))
    (folder / "SKILL.md").write_text("v2", encoding="utf-8")
    untrust_root(service.store, str(project))
    reg = SkillRegistry(service.store)
    reg.load_all(project_root=str(project), project_discovery=True)
    assert reg.manifest("proj.deploy") is None


def test_drift_event_is_recorded(service, project):
    from harness.skills.project_skills import trust_root

    folder = _write_skill(project, ".black-eclipse/skills", "proj.deploy", instructions="v1")
    trust_root(service.store, str(project))
    (folder / "SKILL.md").write_text("v2", encoding="utf-8")
    reg = SkillRegistry(service.store)
    reg.load_all(project_root=str(project), project_discovery=True)
    events = service.store.list_events(limit=50)
    assert any(e["type"] == "skill.project_drift" for e in events)


# -- Per-skill identity + selective quarantine (final hardening) -------------


def test_changed_skill_quarantines_only_that_skill(service, project):
    from harness.skills.project_skills import trust_root

    stable = _write_skill(project, ".black-eclipse/skills", "proj.stable", instructions="unchanged")
    changing = _write_skill(project, ".black-eclipse/skills", "proj.changing", instructions="v1")
    trust_root(service.store, str(project))

    (changing / "SKILL.md").write_text("v2 — malicious", encoding="utf-8")
    reg = SkillRegistry(service.store)
    reg.load_all(project_root=str(project), project_discovery=True)

    # The changed skill is quarantined; the unchanged one still loads.
    assert reg.manifest("proj.changing") is None
    assert reg.manifest("proj.stable") is not None
    assert reg.project_drift() is True
    assert reg.project_quarantined_ids() == ["proj.changing"]
    assert reg.project_unchanged_ids() == ["proj.stable"]
    assert "proj.changing" in reg.project_changed_ids()


def test_reapprove_reactivates_changed_skill(service, project):
    from harness.skills.project_skills import trust_root

    _write_skill(project, ".black-eclipse/skills", "proj.stable", instructions="unchanged")
    changing = _write_skill(project, ".black-eclipse/skills", "proj.changing", instructions="v1")
    trust_root(service.store, str(project))
    (changing / "SKILL.md").write_text("v2", encoding="utf-8")

    reg = SkillRegistry(service.store)
    reg.load_all(project_root=str(project), project_discovery=True)
    assert reg.manifest("proj.changing") is None

    trust_root(service.store, str(project), actor="operator")
    reg.load_all(project_root=str(project), project_discovery=True)
    assert reg.manifest("proj.changing") is not None
    assert reg.project_drift() is False


def test_changed_skill_review_reports_hashes_not_content(service, project):
    from harness.skills.project_skills import changed_skill_review, trust_root

    changing = _write_skill(project, ".black-eclipse/skills", "proj.deploy", instructions="secret-prose-v1")
    trust_root(service.store, str(project))
    (changing / "SKILL.md").write_text("secret-prose-v2", encoding="utf-8")

    review = changed_skill_review(service.store, str(project))
    assert review["drift"] is True
    entry = next(c for c in review["changes"] if c["skillId"] == "proj.deploy")
    assert entry["status"] == "changed"
    assert entry["approvedHash"] and entry["currentHash"]
    # Content is never returned — only hashes/ids.
    assert "secret-prose" not in json.dumps(review)


def test_new_skill_under_trusted_root_requires_approval(service, project):
    from harness.skills.project_skills import trust_root

    _write_skill(project, ".black-eclipse/skills", "proj.first", instructions="a")
    trust_root(service.store, str(project))
    _write_skill(project, ".black-eclipse/skills", "proj.added", instructions="b")

    reg = SkillRegistry(service.store)
    reg.load_all(project_root=str(project), project_discovery=True)
    assert reg.manifest("proj.first") is not None
    assert reg.manifest("proj.added") is None
    assert "proj.added" in reg.project_quarantined_ids()


def test_approval_history_records_who_what_when(service, project):
    from harness.skills.project_skills import trust_root, untrust_root

    _write_skill(project, ".black-eclipse/skills", "proj.deploy")
    trust_root(service.store, str(project), actor="operator-a")
    untrust_root(service.store, str(project), actor="operator-b")

    history = service.store.list_project_approvals()
    actions = [h["action"] for h in history]
    assert "approve" in actions and "untrust" in actions
    approve = next(h for h in history if h["action"] == "approve")
    assert approve["actor"] == "operator-a"
    assert approve["level"] == "root"
    assert approve["approvedHash"]
    assert "proj.deploy" in approve["skillIds"]
    assert "proj.deploy" in approve["contentHashes"]
    untrust = next(h for h in history if h["action"] == "untrust")
    assert untrust["actor"] == "operator-b"


def test_legacy_root_only_trust_quarantines_whole_root(service, project):
    """A trust row without per-skill identity (pre-migration / legacy) keeps the
    previous fail-closed whole-root behavior."""
    from harness.skills.project_skills import canonical_root, root_content_hash

    _write_skill(project, ".black-eclipse/skills", "proj.deploy")
    # Simulate a legacy row: trustedHash set, no contentHashes.
    service.store.set_project_trust(
        canonical_root(str(project)), True,
        content_hash=root_content_hash(str(project)), content_hashes=None,
    )
    # Change a skill without re-approving.
    (project / ".black-eclipse" / "skills" / "deploy" / "SKILL.md").write_text("changed", encoding="utf-8")

    reg = SkillRegistry(service.store)
    reg.load_all(project_root=str(project), project_discovery=True)
    assert reg.manifest("proj.deploy") is None
    assert reg.project_drift() is True

