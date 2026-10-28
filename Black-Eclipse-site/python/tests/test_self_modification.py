"""Class-authorized self-modification: accept, read-only enable, expiry, cap."""

from __future__ import annotations

import os
from types import SimpleNamespace

from harness.eclipse_memory import EclipseMemoryStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.self_modification import (
    SelfModificationExecutor,
    SelfModificationPolicy,
)
from harness.skills.registry import SkillRegistry


class _Tools:
    def names(self):
        return ["analysis_run"]


def _service(tmp_path):
    run_store = AgentMemoryStore(os.path.join(str(tmp_path), "agent-memory.db"))
    skill_store = EclipseMemoryStore(os.path.join(str(tmp_path), "eclipse-memory.db"))
    registry = SkillRegistry(skill_store)
    registry.attach_tool_registry(_Tools())
    return SimpleNamespace(store=run_store, skill_registry=registry)


def _candidate(store, candidate_id="cand_selfmod"):
    return store.save_candidate({
        "candidateType": "successful_procedure",
        "title": "Reusable procedure: analysis_run",
        "problem": "A repeatable procedure completed.",
        "proposedLesson": "Use analysis_run for this repeatable computation.",
        "proposedProcedure": [{"step": 1, "action": "call analysis_run"}],
        "evidenceReferences": [
            {"kind": "tool", "name": "analysis_run"},
            {"kind": "tool", "name": "analysis_run"},
        ],
        "confidence": 0.7, "status": "detected",
        "signature": candidate_id, "sourceRunId": "run_selfmod",
    })


def test_accept_mode_accepts_but_does_not_enable(tmp_path):
    service = _service(tmp_path)
    try:
        cid = _candidate(service.skill_registry.store)
        executor = SelfModificationExecutor(
            service, SelfModificationPolicy(mode="accept"),
        )
        result = executor.run_once()
        assert result["accepted"]
        assert service.skill_registry.store.get_candidate(cid)["status"] == "accepted"
        skill_id = service.skill_registry.store.get_candidate(cid)["resultingSkillId"]
        assert service.skill_registry.store.get_skill(skill_id)["status"] == "draft"
    finally:
        service.store.close()


def test_enable_mode_enables_read_only_skill_with_audit_and_expiry(tmp_path):
    service = _service(tmp_path)
    try:
        cid = _candidate(service.skill_registry.store)
        executor = SelfModificationExecutor(
            service,
            SelfModificationPolicy(mode="enable", ttl_days=7, max_active_skills=3),
        )
        result = executor.run_once()
        assert result["accepted"] and result["enabled"]
        skill_id = service.skill_registry.store.get_candidate(cid)["resultingSkillId"]
        assert service.skill_registry.store.get_skill(skill_id)["status"] == "enabled"
        active = executor.audit.active("enable_skill")
        assert active and active[0]["expiresAt"]
    finally:
        service.store.close()


def test_ttl_expiry_disables_the_skill(tmp_path):
    service = _service(tmp_path)
    try:
        _candidate(service.skill_registry.store)
        executor = SelfModificationExecutor(
            service, SelfModificationPolicy(mode="enable", ttl_days=7),
        )
        executor.run_once()
        grant = executor.audit.active("enable_skill")[0]
        executor.audit._db.execute(
            "UPDATE SelfModificationAction SET expiresAt='2000-01-01T00:00:00Z' WHERE id=?",
            (grant["id"],),
        )
        executor.audit._db.commit()
        result = executor.run_once()
        assert grant["id"] in result["expired"]
        assert service.skill_registry.store.get_skill(grant["subject"])["status"] == "disabled"
    finally:
        service.store.close()


def test_off_mode_and_cap_refuse_enablement(tmp_path):
    service = _service(tmp_path)
    try:
        cid = _candidate(service.skill_registry.store)
        executor = SelfModificationExecutor(
            service, SelfModificationPolicy(mode="off"),
        )
        assert executor.run_once()["accepted"] == []
        executor = SelfModificationExecutor(
            service,
            SelfModificationPolicy(mode="enable", max_active_skills=0),
        )
        executor.run_once()
        skill_id = service.skill_registry.store.get_candidate(cid)["resultingSkillId"]
        assert service.skill_registry.store.get_skill(skill_id)["status"] == "draft"
    finally:
        service.store.close()
