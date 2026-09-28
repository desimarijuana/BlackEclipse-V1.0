"""Phase 8 â€” cross-cutting regression/hardening for the memory & skills
evolution. Each test pins one safety invariant the earlier phases introduced.
Uses temp DBs only; the developer's real stores are never touched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from harness.eclipse_memory import EclipseMemoryService
from harness.eclipse_memory.transfer import export_payload, import_payload
from harness.skills.bundles import resolve_bundle
from harness.skills.learn import LearnRequest, learn_from_source
from harness.skills.project_skills import trust_root, untrust_root
from harness.skills.registry import SkillRegistry


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


def _write_skill(root: Path, skill_id: str, *, status: str = "enabled", permissions=None) -> None:
    folder = root / skill_id.split(".")[-1]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "skill.json").write_text(json.dumps({
        "id": skill_id, "name": skill_id, "version": "1.0.0", "description": "t",
        "category": "research", "status": status, "permissions": permissions or ["data.read"],
    }), encoding="utf-8")
    (folder / "SKILL.md").write_text("procedure", encoding="utf-8")


# â”€â”€ Project skill trust â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_project_trust_then_untrust_roundtrip(service, tmp_path):
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    _write_skill(root / ".black-eclipse" / "skills", "proj.deploy")
    trust_root(service.store, str(root))
    reg = SkillRegistry(service.store)
    reg.load_all(project_root=str(root), project_discovery=True)
    assert reg.manifest("proj.deploy") is not None
    untrust_root(service.store, str(root))
    reg.load_all(project_root=str(root), project_discovery=True)
    assert reg.manifest("proj.deploy") is None


# â”€â”€ Bundle resolution safety â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_bundle_never_enables_disabled(service, tmp_path):
    root = tmp_path / "lib"
    _write_skill(root, "research.a")
    _write_skill(root, "system.off", status="disabled")
    reg = SkillRegistry(service.store)
    reg.load_all(root=str(root), project_discovery=False)
    service.store.save_skill_bundle({"id": "b", "skills": ["research.a", "system.off"]})
    res = resolve_bundle(service.store, reg, "b")
    assert res.resolved == ["research.a"]
    assert "system.off" in res.unavailable


# â”€â”€ Generated-skill sanitization â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_generated_skill_never_carries_a_secret(service, tmp_path):
    root = tmp_path / "lib"
    _write_skill(root, "research.a")
    reg = SkillRegistry(service.store)
    reg.load_all(root=str(root), project_discovery=False)
    result = learn_from_source(
        LearnRequest(
            source_kind="document", title="Token setup",
            objective="Set api_key: sk-supersecret then call the API.",
            tools=["research_search"],
        ),
        service.store, available_tools=["research_search"], actor_is_operator=True,
    )
    assert result["ok"] is True
    assert "secret" in result["sanitized"]
    # The secret must not appear in the persisted draft manifest.
    stored = service.store.get_version(result["draft"]["id"], "0.1.0")
    assert "sk-supersecret" not in json.dumps(stored)


def test_generated_skill_stays_inert(service, tmp_path):
    root = tmp_path / "lib"
    _write_skill(root, "research.a")
    reg = SkillRegistry(service.store)
    reg.load_all(root=str(root), project_discovery=False)
    result = learn_from_source(
        LearnRequest(source_kind="repeated_workflow", title="Weekly", objective="Do the thing."),
        service.store, available_tools=["research_search"], actor_is_operator=True,
    )
    assert result["draft"]["status"] == "draft"
    assert service.store.get_skill(result["draft"]["id"])["status"] == "draft"


# â”€â”€ Export/import compatibility â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_export_import_roundtrip_preserves_bundles_and_trust(service, tmp_path):
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    trust_root(service.store, str(root))
    service.store.save_skill_bundle({"id": "research", "name": "R", "skills": ["research.a"]})
    service.write_memory(memory_type="preference", content="I prefer concise answers", source="explicit_user")

    document = export_payload(service.store)
    assert document["version"] == 2
    assert len(document["bundles"]) == 1
    assert len(document["projectTrust"]) == 1

    # Import into a fresh store.
    from harness.eclipse_memory.store import EclipseMemoryStore

    other = EclipseMemoryService(EclipseMemoryStore(str(tmp_path / "other.db")))
    report = import_payload(other, document)
    assert report["imported"] >= 1
    assert report["importedBundles"] == 1
    assert len(other.store.list_skill_bundles()) == 1
    other.close()


def test_v1_export_still_imports(service):
    v1 = {
        "schema": "black-eclipse-memory-export", "version": 1,
        "memories": [{"content": "I prefer concise answers", "memoryType": "preference", "scope": "user", "scopeId": "u1"}],
    }
    report = import_payload(service, v1)
    assert report["imported"] == 1
    assert report["importedBundles"] == 0


# â”€â”€ Archive reversibility â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_archive_is_reversible(service):
    memory = service.write_memory(memory_type="preference", content="durable fact", source="explicit_user")
    service.store.archive_memory(memory["id"])
    assert service.store.get_memory(memory["id"])["status"] == "archived"
    restored = service.store.restore_memory(memory["id"])
    assert restored["status"] == "active"


# â”€â”€ Scope isolation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_scope_isolation_on_retrieval(service):
    service.write_memory(memory_type="preference", content="u1 secret preference", source="explicit_user", scope="user", scope_id="u1")
    result = service.retrieve(query="secret preference", actor_scope="user", scope_id="u2")
    assert all("u1" != m.get("scopeId") for m in result.memories)


# â”€â”€ Prompt budget â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_bundle_content_is_prompt_bounded(service, tmp_path):
    root = tmp_path / "lib"
    for i in range(14):
        _write_skill(root, f"research.s{i}")
    reg = SkillRegistry(service.store)
    reg.load_all(root=str(root), project_discovery=False)
    service.store.save_skill_bundle({"id": "big", "skills": [f"research.s{i}" for i in range(14)]})
    res = resolve_bundle(service.store, reg, "big")
    # The bundle caps members at 12 and content at the manifest bound.
    assert len(res.resolved) <= 12
    assert len(res.content) <= 1200

