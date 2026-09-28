"""Skill bundles: resolution is deterministic, missing/disabled reported, and a
bundle can never enable a disabled skill or bypass permissions (Phase 3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.eclipse_memory import EclipseMemoryService
from harness.skills.bundles import BundleError, SkillBundle, resolve_bundle
from harness.skills.registry import SkillRegistry


def _write_skill(root: Path, skill_id: str, *, status: str = "enabled", permissions=None) -> None:
    folder = root / skill_id.split(".")[-1]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "skill.json").write_text(json.dumps({
        "id": skill_id,
        "name": skill_id,
        "version": "1.0.0",
        "description": "test skill",
        "category": "research",
        "status": status,
        "permissions": permissions or ["data.read"],
    }), encoding="utf-8")
    (folder / "SKILL.md").write_text("procedure", encoding="utf-8")


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


@pytest.fixture()
def registry(service, tmp_path):
    root = tmp_path / "lib"
    _write_skill(root, "research.planning")
    _write_skill(root, "quality.financial-data-quality")
    _write_skill(root, "system.hidden", status="disabled")
    reg = SkillRegistry(service.store)
    reg.load_all(root=str(root), project_discovery=False)
    return reg


def test_bundle_requires_at_least_one_skill():
    with pytest.raises(BundleError):
        SkillBundle(id="research", skills=[])


def test_bundle_rejects_bad_id():
    with pytest.raises(BundleError):
        SkillBundle(id="Bad Id", skills=["a.b"])


def test_resolve_reports_missing_member(service, registry):
    service.store.save_skill_bundle({"id": "research", "skills": ["research.planning", "does.not.exist"]})
    resolution = resolve_bundle(service.store, registry, "research")
    assert "research.planning" in resolution.resolved
    assert "does.not.exist" in resolution.missing
    assert resolution.ok is True


def test_bundle_does_not_enable_disabled_skill(service, registry):
    service.store.save_skill_bundle({"id": "mix", "skills": ["research.planning", "system.hidden"]})
    resolution = resolve_bundle(service.store, registry, "mix")
    assert "system.hidden" in resolution.unavailable
    assert "system.hidden" not in resolution.resolved
    # The skill's stored status is untouched — a bundle never enables.
    assert registry.store.get_skill("system.hidden")["status"] == "disabled"


def test_unknown_bundle_is_not_ok(service, registry):
    resolution = resolve_bundle(service.store, registry, "nope")
    assert resolution.ok is False


def test_bundle_resolution_is_deterministic(service, registry):
    service.store.save_skill_bundle({"id": "r", "skills": ["research.planning", "quality.financial-data-quality", "research.planning"]})
    a = resolve_bundle(service.store, registry, "r")
    b = resolve_bundle(service.store, registry, "r")
    assert a.resolved == b.resolved == ["research.planning", "quality.financial-data-quality"]
    assert a.content == b.content


def test_bundle_content_is_bounded(service, registry):
    service.store.save_skill_bundle({
        "id": "big", "skills": ["research.planning"],
        "instruction": "x" * 5000, "constraints": "y" * 5000,
    })
    bundle = service.store.get_skill_bundle("big")
    assert len(bundle["instruction"]) <= 800
    assert len(bundle["constraints"]) <= 800


def test_bundle_rejects_permission_denied_member(service, registry, tmp_path):
    root = tmp_path / "special"
    _write_skill(root, "finance.heavy", permissions=["portfolio.modify"])
    registry.load_all(root=str(root), project_discovery=False)
    service.store.save_skill_bundle({"id": "p", "skills": ["finance.heavy"]})
    from harness.skills.permissions import DEFAULT_ACTOR

    resolution = resolve_bundle(service.store, registry, "p", actor=DEFAULT_ACTOR)
    assert resolution.ok is False
    assert "finance.heavy" in resolution.unavailable


# -- Lifecycle: version identity, lock, drift (Phase 9) ----------------------


def test_bundle_has_version_identity(service, registry):
    service.store.save_skill_bundle({"id": "r", "skills": ["research.planning"], "version": "2.0.0"})
    bundle = service.store.get_skill_bundle("r")
    assert bundle["version"] == "2.0.0"


def test_bundle_rejects_bad_version(service):
    from harness.skills.bundles import BundleError, SkillBundle

    try:
        SkillBundle(id="r", skills=["research.planning"], version="not-semver")
        assert False, "expected BundleError"
    except BundleError:
        pass


def test_lock_and_detect_drift(service, registry, tmp_path):
    from harness.skills.bundles import lock_bundle, resolve_bundle

    service.store.save_skill_bundle({"id": "r", "skills": ["research.planning"]})
    locked = lock_bundle(service.store, registry, "r")
    assert locked["ok"] is True
    assert locked["bundle"]["locked"] is True
    locked_versions = locked["bundle"]["memberVersions"]
    assert "research.planning" in locked_versions

    # No drift immediately after locking.
    resolution = resolve_bundle(service.store, registry, "r")
    assert resolution.drifted is False
    assert resolution.locked is True

    # Simulate a member version change by resolving the SAME bundle against a
    # registry that reports the member at a different version.
    from harness.skills.manifest import SkillManifest
    from harness.skills.bundles import _resolve

    class _StubRegistry:
        store = type("S", (), {"get_skill": staticmethod(lambda _id: None)})()

        @staticmethod
        def manifest(skill_id):
            return SkillManifest(
                id=skill_id, name="P", version="9.9.9", description="d",
                category="research", status="enabled",
            ) if skill_id == "research.planning" else None

    bundle = SkillBundle(
        id="r", skills=["research.planning"], version="1.0.0",
        member_versions=locked_versions, locked=True,
    )
    resolution2 = _resolve(bundle, _StubRegistry(), actor=None)
    assert resolution2.drifted is True
    assert any("9.9.9" in item for item in resolution2.incompatible)


def test_disabled_member_stays_disabled_under_lock(service, registry):
    service.store.save_skill_bundle({"id": "mix", "skills": ["research.planning", "system.hidden"]})
    from harness.skills.bundles import lock_bundle, resolve_bundle

    lock_bundle(service.store, registry, "mix")
    resolution = resolve_bundle(service.store, registry, "mix")
    assert "system.hidden" not in resolution.resolved
    assert "system.hidden" in resolution.unavailable


def test_lock_never_widens_permissions(service, registry, tmp_path):
    from harness.skills.bundles import lock_bundle

    heavy = tmp_path / "special"
    _write_skill(heavy, "finance.heavy", permissions=["portfolio.modify"])
    registry.load_all(root=str(heavy), project_discovery=False)
    service.store.save_skill_bundle({"id": "p2", "skills": ["finance.heavy"]})
    lock_bundle(service.store, registry, "p2")
    from harness.skills.permissions import DEFAULT_ACTOR

    resolution = resolve_bundle(service.store, registry, "p2", actor=DEFAULT_ACTOR)
    assert "finance.heavy" in resolution.unavailable
