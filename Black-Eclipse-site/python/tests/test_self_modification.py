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
from harness.skills.evaluation import evaluate_skill
from harness.skills.registry import SkillRegistry
from harness.skills.versioning import version_history


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


def _recovery_candidate(store, *, occurrence=1):
    return store.save_candidate({
        "candidateType": "failure_recovery",
        "title": "Retry analysis_run after a transient TOOL_ERROR",
        "problem": "analysis_run failed with TOOL_ERROR; it recovered.",
        "condition": "analysis_run returns TOOL_ERROR",
        "action": "retry analysis_run once after TOOL_ERROR and verify the result",
        "proposedLesson": "When analysis_run fails with TOOL_ERROR, retry it once.",
        "proposedProcedure": [
            {"step": 1, "action": "classify", "detail": "recognize TOOL_ERROR"},
            {"step": 2, "action": "recover", "detail": "retry analysis_run"},
        ],
        "failedCall": "analysis_run",
        "recoveredCall": "analysis_run",
        "precondition": "TOOL_ERROR",
        "replayTest": "Replay run_selfmod forcing analysis_run to TOOL_ERROR.",
        "evidenceReferences": [
            {"kind": "tool", "name": "analysis_run", "phase": "failed"},
            {"kind": "tool", "name": "analysis_run", "phase": "recovered"},
        ],
        "occurrenceCount": occurrence,
        "confidence": 0.5,
        "status": "detected",
        "signature": f"recovery-{occurrence}",
        "sourceRunId": "run_selfmod",
    })


def test_single_occurrence_recovery_is_not_auto_accepted(tmp_path):
    service = _service(tmp_path)
    try:
        cid = _recovery_candidate(service.skill_registry.store, occurrence=1)
        executor = SelfModificationExecutor(
            service, SelfModificationPolicy(mode="enable"),
        )
        result = executor.run_once()
        assert result["accepted"] == []
        assert service.skill_registry.store.get_candidate(cid)["status"] == "detected"
        assert any(
            item.get("reason") == "insufficient_recurrence_or_evidence"
            for item in result["skipped"]
        )
    finally:
        service.store.close()


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


def test_canary_rolls_back_a_granted_skill_when_evaluation_fails(tmp_path):
    service = _service(tmp_path)
    try:
        _candidate(service.skill_registry.store)
        executor = SelfModificationExecutor(
            service, SelfModificationPolicy(mode="enable", ttl_days=7),
        )
        executor.run_once()
        grant = executor.audit.active("enable_skill")[0]
        skill_id = grant["subject"]
        version = service.skill_registry.store.get_skill(skill_id)["latestVersion"]
        service.skill_registry.store.save_evaluation(
            skill_id=skill_id, version=version, status="failed",
            dimensions=[{"name": "discrimination", "status": "failed"}],
            summary="canary failure",
        )
        result = executor.run_once()
        assert result["rolledBack"], result
        assert service.skill_registry.store.get_skill(skill_id)["status"] == "disabled"
        assert executor.audit.active("enable_skill") == []
    finally:
        service.store.close()


def test_shadow_mode_records_but_does_not_enable(tmp_path):
    service = _service(tmp_path)
    try:
        cid = _candidate(service.skill_registry.store)
        accepted = SelfModificationExecutor(
            service, SelfModificationPolicy(mode="accept"),
        )
        accepted.run_once()
        skill_id = service.skill_registry.store.get_candidate(cid)["resultingSkillId"]
        assert service.skill_registry.store.get_skill(skill_id)["status"] == "draft"

        shadow = SelfModificationExecutor(
            service, SelfModificationPolicy(mode="shadow"),
        )
        result = shadow.run_once()
        assert result["enabled"], result
        assert service.skill_registry.store.get_skill(skill_id)["status"] == "draft"
        assert any(
            row["kind"] == "shadow_enable_skill"
            for row in shadow.audit.list(10)
        )
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
        version = service.skill_registry.store.get_skill(skill_id)["latestVersion"]
        stored = service.skill_registry.store.get_version(skill_id, version)
        assert stored["nonActivationCause"] == "active_skill_cap"
        history = version_history(service.skill_registry, skill_id)
        assert history[0]["nonActivationCause"] == "active_skill_cap"
        assert history[0]["nonActivationDetail"]
    finally:
        service.store.close()


def test_unchanged_passed_version_is_evaluated_once(tmp_path):
    service = _service(tmp_path)
    try:
        cid = _candidate(service.skill_registry.store)
        executor = SelfModificationExecutor(
            service, SelfModificationPolicy(mode="enable"),
        )
        executor.run_once()
        skill_id = service.skill_registry.store.get_candidate(cid)["resultingSkillId"]
        version = service.skill_registry.store.get_skill(skill_id)["latestVersion"]
        before = len(service.skill_registry.store.list_evaluations(skill_id, limit=50))

        result = evaluate_skill(skill_id, version, service.skill_registry)

        after = len(service.skill_registry.store.list_evaluations(skill_id, limit=50))
        assert result["skipped"] is True
        assert result["reason"] == "unchanged_passed"
        assert after == before
    finally:
        service.store.close()
