"""Phase 9 (final hardening) — bundle reproducibility.

A locked bundle records exact member versions AND content hashes, so it can be
reconstructed; an update never silently changes locked behavior; a member whose
content changed under the same version is detected; disabled skills stay disabled;
and the lock is exportable/rollback-able.
"""

from __future__ import annotations

import json

import pytest

from harness.eclipse_memory import EclipseMemoryService
from harness.skills.bundles import (
    SkillBundle,
    bundle_update_preview,
    lock_bundle,
    resolve_bundle,
    rollback_bundle,
)
from harness.skills.registry import SkillRegistry


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


def _library(tmp_path, *, version="1.0.0", prose="Do the thing."):
    root = tmp_path / "lib"
    folder = root / "research" / "alpha"
    folder.mkdir(parents=True)
    (folder / "skill.json").write_text(json.dumps({
        "id": "research.alpha", "name": "Alpha", "version": version,
        "description": "A skill.", "category": "research", "status": "enabled",
        "instructions": "SKILL.md", "permissions": ["data.read"], "requiredTools": [],
    }), encoding="utf-8")
    (folder / "SKILL.md").write_text(prose, encoding="utf-8")
    return root


def _registry(service, root):
    reg = SkillRegistry(service.store)
    reg.load_all(root=str(root))
    return reg


def test_lock_records_versions_and_hashes(service, tmp_path):
    root = _library(tmp_path)
    reg = _registry(service, root)
    service.store.save_skill_bundle({"id": "b", "name": "B", "skills": ["research.alpha"]})
    result = lock_bundle(service.store, reg, "b")
    assert result["ok"] is True
    bundle = service.store.get_skill_bundle("b")
    assert bundle["memberVersions"] == {"research.alpha": "1.0.0"}
    assert bundle["memberHashes"]["research.alpha"]
    assert bundle["locked"] is True


def test_locked_receipt_is_reproducible(service, tmp_path):
    root = _library(tmp_path)
    reg = _registry(service, root)
    service.store.save_skill_bundle({"id": "b", "name": "B", "skills": ["research.alpha"]})
    lock_bundle(service.store, reg, "b")
    resolution = resolve_bundle(service.store, reg, "b")
    receipt = resolution.receipt
    assert receipt["bundleId"] == "b"
    assert receipt["locked"] is True
    member = receipt["members"][0]
    assert member["skillId"] == "research.alpha"
    assert member["version"] == "1.0.0"
    assert member["contentHash"]
    assert member["lockedHash"] == member["contentHash"]


def test_content_edit_under_same_version_is_detected(service, tmp_path):
    root = _library(tmp_path)
    reg = _registry(service, root)
    service.store.save_skill_bundle({"id": "b", "name": "B", "skills": ["research.alpha"]})
    lock_bundle(service.store, reg, "b")

    # Edit the prose without bumping the version.
    (root / "research" / "alpha" / "SKILL.md").write_text("Malicious new procedure.", encoding="utf-8")
    reg.load_all(root=str(root))
    resolution = resolve_bundle(service.store, reg, "b")
    assert resolution.content_drifted == ["research.alpha"]
    assert any("research.alpha" in item for item in resolution.incompatible)
    assert resolution.locked_hashes["research.alpha"] != resolution.current_hashes["research.alpha"]


def test_update_preview_reports_changes_without_mutating(service, tmp_path):
    root = _library(tmp_path)
    reg = _registry(service, root)
    service.store.save_skill_bundle({"id": "b", "name": "B", "skills": ["research.alpha"]})
    lock_bundle(service.store, reg, "b")
    before = service.store.get_skill_bundle("b")

    (root / "research" / "alpha" / "SKILL.md").write_text("changed", encoding="utf-8")
    reg.load_all(root=str(root))
    preview = bundle_update_preview(service.store, reg, "b")
    assert preview["wouldChange"] is True
    change = preview["changes"][0]
    assert change["change"] == "content_changed"
    # Read-only: the stored lock is unchanged.
    assert service.store.get_skill_bundle("b") == before


def test_rollback_repins_recorded_lock(service, tmp_path):
    root = _library(tmp_path)
    reg = _registry(service, root)
    service.store.save_skill_bundle({"id": "b", "name": "B", "skills": ["research.alpha"]})
    lock_bundle(service.store, reg, "b")
    first_lock = service.store.get_skill_bundle("b")

    # A content edit + re-lock pushes the first lock onto the bounded history.
    (root / "research" / "alpha" / "SKILL.md").write_text("changed prose", encoding="utf-8")
    reg.load_all(root=str(root))
    lock_bundle(service.store, reg, "b")
    assert service.store.get_skill_bundle("b")["memberHashes"] != first_lock["memberHashes"]

    # Roll back to the first recorded lock (hash, same version).
    result = rollback_bundle(service.store, reg, "b")
    assert result["ok"] is True
    assert result["bundle"]["memberHashes"] == first_lock["memberHashes"]
    assert result["bundle"]["memberVersions"] == first_lock["memberVersions"]


def test_disabled_member_stays_disabled_under_lock(service, tmp_path):
    root = tmp_path / "lib"
    folder = root / "f"
    folder.mkdir(parents=True)
    (folder / "skill.json").write_text(json.dumps({
        "id": "system.hidden", "name": "H", "version": "1.0.0", "description": "d",
        "category": "system", "status": "disabled", "permissions": [], "requiredTools": [],
    }), encoding="utf-8")
    (folder / "SKILL.md").write_text("x", encoding="utf-8")
    reg = _registry(service, root)
    service.store.save_skill_bundle({"id": "b", "name": "B", "skills": ["system.hidden"]})
    lock_bundle(service.store, reg, "b")
    resolution = resolve_bundle(service.store, reg, "b")
    assert "system.hidden" in resolution.unavailable
    assert "system.hidden" not in resolution.resolved


def test_lock_is_exportable_and_reconstructable(service, tmp_path):
    from harness.eclipse_memory.transfer import export_payload, import_payload

    root = _library(tmp_path)
    reg = _registry(service, root)
    service.store.save_skill_bundle({"id": "b", "name": "B", "skills": ["research.alpha"]})
    lock_bundle(service.store, reg, "b")

    document = export_payload(service.store)
    exported = document["bundles"][0]
    assert exported["memberVersions"] == {"research.alpha": "1.0.0"}
    assert exported["memberHashes"]["research.alpha"]
    assert exported["locked"] is True

    # Reconstruct into a fresh store.
    from harness.eclipse_memory.store import EclipseMemoryStore

    other = EclipseMemoryService(EclipseMemoryStore(str(tmp_path / "other.db")))
    report = import_payload(other, document)
    assert report["importedBundles"] == 1
    rebuilt = other.store.get_skill_bundle("b")
    assert rebuilt["memberHashes"] == exported["memberHashes"]
    assert rebuilt["locked"] is True
    other.close()


def test_bundle_never_widens_permissions_on_lock(service, tmp_path):
    # A member that declares blocked permissions stays blocked regardless of lock.
    root = tmp_path / "lib"
    folder = root / "f"
    folder.mkdir(parents=True)
    (folder / "skill.json").write_text(json.dumps({
        "id": "finance.evil", "name": "E", "version": "1.0.0", "description": "d",
        "category": "finance", "status": "enabled", "permissions": ["trade.execute"],
    }), encoding="utf-8")
    (folder / "SKILL.md").write_text("x", encoding="utf-8")
    reg = _registry(service, root)
    service.store.save_skill_bundle({"id": "b", "name": "B", "skills": ["finance.evil"]})
    from harness.skills.permissions import OPERATOR_ACTOR, can_enable

    manifest = reg.manifest("finance.evil")
    assert can_enable(manifest.permissions, OPERATOR_ACTOR).allowed is False
