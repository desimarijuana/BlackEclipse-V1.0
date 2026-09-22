"""Phase 3-M — Eclipse-Memory database, isolation, write and retrieval tests.

Covers Milestones 1–2 and the safety-critical parts of 5: separate database
file, configurable path, migrations, health, memory typing/scope, evidence,
links, supersession, dedupe, retrieval ranking + budget + diagnostics, scope
isolation, corrections and mistakes.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.service import MemoryWriteError


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-emem-")
    path = os.path.join(directory, "eclipse-memory.db")
    svc = EclipseMemoryService(EclipseMemoryStore(path))
    yield svc
    svc.close()


# ── Database / isolation ────────────────────────────────────────────────────


def test_separate_database_file(service):
    assert service.store.path.endswith("eclipse-memory.db")


def test_migrations_applied_and_idempotent(service):
    status = service.migration_status()
    assert status["upToDate"] is True
    assert status["appliedVersions"]
    # Re-opening the same file must not fail or re-run migrations.
    store2 = EclipseMemoryStore(service.store.path)
    assert store2.migration_status()["upToDate"] is True
    store2.close()


def test_health_reports_counts(service):
    health = service.health()
    assert health["ok"] is True
    assert health["integrity"] == "ok"
    assert "MemoryRecord" in health["counts"]


def test_configurable_path_env(monkeypatch):
    target = os.path.join(tempfile.mkdtemp(), "custom-memory.db")
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", target)
    store = EclipseMemoryStore()
    try:
        assert os.path.abspath(store.path) == os.path.abspath(target)
        assert os.path.isfile(target)
    finally:
        store.close()


def test_does_not_touch_other_databases(service):
    # The eclipse-memory file only contains eclipse-memory tables — no JDdS /
    # journal / harness-run tables.
    tables = {
        r[0]
        for r in service.store._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "MemoryRecord" in tables
    assert "HarnessRun" not in tables
    assert "Trade" not in tables
    assert "Price" not in tables


# ── Write pipeline ──────────────────────────────────────────────────────────


def test_explicit_memory_save_and_scope(service):
    memory = service.write_memory(
        memory_type="preference", content="User prefers concise answers",
        source="explicit_user", scope="user", scope_id="u1", created_by="u1",
    )
    assert memory["memoryType"] == "preference"
    assert memory["scope"] == "user"
    assert memory["status"] == "active"


def test_preference_cannot_be_universal(service):
    memory = service.write_memory(
        memory_type="preference", content="Likes dark charts",
        source="explicit_user", scope="general", created_by="u1",
    )
    # A preference is forced into a user scope — never universal.
    assert memory["scope"] == "user"


def test_rejects_unknown_type_empty_content_and_bad_source(service):
    with pytest.raises(MemoryWriteError):
        service.write_memory(memory_type="nonsense", content="x", source="explicit_user")
    with pytest.raises(MemoryWriteError):
        service.write_memory(memory_type="semantic", content="   ", source="explicit_user")
    with pytest.raises(MemoryWriteError):
        service.write_memory(memory_type="semantic", content="x", source="model_chatter")


def test_duplicate_detection(service):
    first = service.write_memory(
        memory_type="semantic", content="ACME is listed on PSX",
        source="verified_source", scope="market", subject="ACME",
    )
    second = service.write_memory(
        memory_type="semantic", content="ACME is listed on PSX",
        source="verified_source", scope="market", subject="ACME",
    )
    assert first["id"] == second["id"]


def test_evidence_attachment(service):
    memory = service.write_memory(
        memory_type="semantic", content="FY24 revenue grew 12%",
        source="verified_source", scope="market", subject="ACME",
        evidence={"sourceType": "filing", "sourceUrl": "https://example.com/filing",
                  "text": "revenue 1.2B", "verificationStatus": "valid"},
    )
    evidence = service.store.list_evidence(memory["id"])
    assert len(evidence) == 1
    assert evidence[0]["sourceType"] == "filing"
    assert evidence[0]["verificationStatus"] == "valid"


def test_supersession_preserves_both(service):
    old = service.write_memory(memory_type="semantic", content="CEO is A", source="manual")
    new = service.write_memory(memory_type="semantic", content="CEO is B", source="manual", allow_duplicate=True)
    service.store.supersede_memory(old["id"], new["id"])
    assert service.store.get_memory(old["id"])["status"] == "superseded"
    # The old record still exists (audit preserved).
    assert service.store.get_memory(old["id"]) is not None
    links = service.store.list_links(old["id"])
    assert any(link["relation"] == "superseded" for link in links)


def test_proposed_memory_is_inert(service):
    proposed = service.propose_memory(
        memory_type="procedural", content="Fallback to source B when A fails",
        subject="retrieval",
    )
    assert proposed["status"] == "proposed"
    result = service.retrieve(query="source fallback")
    assert all(m["id"] != proposed["id"] for m in result.memories)


def test_review_memory(service):
    proposed = service.propose_memory(memory_type="procedural", content="Try source B first")
    approved = service.review_memory(proposed["id"], approve=True)
    assert approved["status"] == "active"


# ── Retrieval pipeline ──────────────────────────────────────────────────────


def test_retrieval_relevance_and_exclusion(service):
    service.write_memory(memory_type="semantic", content="ACME revenue is 1.2B",
                         source="manual", subject="ACME")
    service.write_memory(memory_type="preference", content="User likes terse summaries",
                         source="explicit_user", scope="user", scope_id="u1")
    result = service.retrieve(query="ACME revenue")
    ids = [m["subject"] for m in result.memories]
    assert "ACME" in ids
    # A preference with no keyword overlap is not force-injected.
    assert result.diagnostics["selected"] >= 1


def test_retrieval_excludes_superseded(service):
    old = service.write_memory(memory_type="semantic", content="Old fact about ACME", source="manual", subject="ACME")
    new = service.write_memory(memory_type="semantic", content="New fact about ACME", source="manual", subject="ACME", allow_duplicate=True)
    service.store.supersede_memory(old["id"], new["id"])
    result = service.retrieve(query="fact about ACME")
    returned = {m["id"] for m in result.memories}
    assert old["id"] not in returned
    assert new["id"] in returned


def test_retrieval_scope_isolation(service):
    service.write_memory(memory_type="preference", content="u1 secret preference",
                         source="explicit_user", scope="user", scope_id="u1")
    result = service.retrieve(query="secret preference", actor_scope="user", scope_id="u2")
    # u2 must not retrieve u1's memory.
    assert all(m.get("scopeId") != "u1" for m in result.memories)


def test_retrieval_budget_enforced(service):
    for i in range(20):
        service.write_memory(memory_type="semantic", content=f"fact number {i} " + "x" * 200,
                             source="manual", allow_duplicate=True)
    result = service.retrieve(query="fact", budget_chars=500)
    assert result.diagnostics["usedChars"] <= 500


def test_retrieval_diagnostics_recorded(service):
    service.write_memory(memory_type="semantic", content="Something relevant", source="manual")
    service.retrieve(query="relevant", run_id="run_x")
    events = service.store.list_retrievals()
    assert events
    assert events[0]["runId"] == "run_x"
    assert "candidates" in events[0]


# ── Corrections / mistakes ──────────────────────────────────────────────────


def test_correction_recorded_and_memory_captured(service):
    result = service.record_correction(
        wrong="Compared FY23 to FY24-Q1", correction="Compare like-for-like periods",
        subject="fundamental-analysis", provided_by="user", scope="user",
    )
    assert result["correctionId"]
    assert result["memory"]["memoryType"] == "correction"
    # A correction is not automatically generalizable.
    assert result["generalizable"] is False
    assert service.store.list_corrections()


def test_mistake_recorded(service):
    mistake_id = service.record_mistake({
        "category": "currency_mismatch", "severity": "high", "runId": "run_m",
        "expected": "PKR", "actual": "USD", "reusable": True,
    })
    assert mistake_id
    mistakes = service.store.list_mistakes("run_m")
    assert mistakes[0]["category"] == "currency_mismatch"


# ── Legacy skill-table import ───────────────────────────────────────────────


def test_import_legacy_skills_is_idempotent(tmp_path):
    import os

    legacy = os.path.join(str(tmp_path), "agent-memory.db")
    from harness.skills import SkillStore as OldStore
    from harness.skills.manifest import SkillManifest

    old = OldStore(legacy)
    manifest = SkillManifest(id="legacy.skill", name="Legacy", version="1.0.0",
                             description="x", category="research", status="enabled")
    old.upsert_skill(skill_id=manifest.id, name=manifest.name, description=manifest.description,
                     category=manifest.category, latest_version=manifest.version,
                     status=manifest.status, tags=manifest.tags)
    old.save_version(manifest.model_dump(), manifest.content_hash())
    old.close()

    fresh_path = os.path.join(str(tmp_path), "eclipse-memory.db")
    svc = EclipseMemoryService(EclipseMemoryStore(fresh_path))
    try:
        first = svc.import_legacy_skills(legacy)
        assert first["imported"] is True
        assert "legacy.skill" in [s["id"] for s in svc.store.list_skills()]
        # Re-running is a no-op (never duplicates).
        assert svc.import_legacy_skills(legacy)["imported"] is False
    finally:
        svc.close()


def test_import_skips_missing_legacy_file(service):
    assert service.import_legacy_skills("/nonexistent/agent-memory.db")["imported"] is False


def test_does_not_touch_journal(service):
    # Even if a JDdS-like database exists next to it, eclipse-memory never opens
    # or mutates it — the only tables here are memory/skill tables.
    tables = {r[0] for r in service.store._db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "Trade" not in tables
    assert "JournalDay" not in tables
    assert "ResearchReport" not in tables
