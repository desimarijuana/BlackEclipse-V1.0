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
