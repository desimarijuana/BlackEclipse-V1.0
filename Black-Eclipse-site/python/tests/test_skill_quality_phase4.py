"""Phase 4 (final hardening) — skill quality confidence and regression.

Proves the five evidence states are distinguished, failure-cause trends exist,
sample size/uncertainty are surfaced, and promotion evidence carries a
same-case regression warning before promotion.
"""

from __future__ import annotations

import pytest

from harness.eclipse_memory import EclipseMemoryService
from harness.eclipse_memory.skill_quality import (
    EVIDENCE_DEGRADED,
    EVIDENCE_INSUFFICIENT,
    EVIDENCE_MIXED,
    EVIDENCE_NONE,
    EVIDENCE_RELIABLE,
    FAILURE_CAUSES,
    promotion_evidence,
    skill_quality_metrics,
)


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


def _seed(service, n, *, status="completed", version="1.0.0", error=None):
    ids = []
    for _ in range(n):
        eid = service.store.create_execution(
            run_id="r", skill_id="test.skill", version=version, manifest_hash="h",
            parent_run_id=None, execution_mode="interactive", actor="local", input_data={},
        )
        service.store.finish_execution(
            eid, status=status, output="x", output_validated=(status == "completed"),
            error=error if error is not None else (
                {"code": "OUTPUT_VALIDATION_FAILED"} if status != "completed" else None
            ),
            duration_ms=100,
        )
        ids.append(eid)
    return ids


def _seed_alternating(service, success, failure, *, version="1.0.0"):
    """Seed successes/failures with a non-declining (alternating) recency
    distribution and explicit distinct ascending timestamps, so the
    time-weighted metric is deterministic (sub-second ties otherwise make its
    ordering arbitrary)."""
    total = success + failure
    fail_positions = {round((k + 0.5) * total / max(1, failure)) for k in range(failure)} if failure else set()
    ordered_ids: list[str] = []
    for i in range(total):
        status = "failed" if i in fail_positions and i < total - 1 else "completed"
        ordered_ids.extend(_seed(service, 1, status=status, version=version))
    # Stamp strictly increasing createdAt in insertion order.
    for index, execution_id in enumerate(ordered_ids):
        service.store._db.execute(
            "UPDATE SkillExecution SET createdAt=? WHERE id=?",
            (f"2026-01-01T00:{index:02d}:00+00:00", execution_id),
        )
    service.store._db.commit()


def test_required_failure_categories_vocabulary():
    for required in (
        "missing_tool", "provider_failure", "permission_denied", "invalid_input",
        "output_validation", "timeout", "unsupported_data", "user_correction",
        "tool_failure", "missing_evidence",
    ):
        assert required in FAILURE_CAUSES, required


def test_no_evidence_state(service):
    metrics = skill_quality_metrics(service.store, "test.skill")
    assert metrics["evidenceState"]["state"] == EVIDENCE_NONE


def test_insufficient_evidence_state(service):
    _seed(service, 2)
    metrics = skill_quality_metrics(service.store, "test.skill")
    assert metrics["evidenceState"]["state"] == EVIDENCE_INSUFFICIENT
    assert "reliability" in metrics["evidenceState"]["reason"]


def test_reliable_success_state(service):
    _seed(service, 20)
    metrics = skill_quality_metrics(service.store, "test.skill")
    assert metrics["evidenceState"]["state"] == EVIDENCE_RELIABLE


def test_degraded_state_on_high_failure(service):
    _seed(service, 20, status="failed")
    metrics = skill_quality_metrics(service.store, "test.skill")
    assert metrics["evidenceState"]["state"] == EVIDENCE_DEGRADED


def test_mixed_state_when_inconsistent(service):
    # 20 executions, ~60% success → enough sample, not reliable, not degraded.
    # Alternating (with real timestamps) avoids a monotonic decline, which is
    # correctly classified as degraded, not mixed.
    _seed_alternating(service, 12, 8)
    metrics = skill_quality_metrics(service.store, "test.skill")
    assert metrics["executions"] == 20
    assert metrics["sampleReliable"] is True
    assert metrics["evidenceState"]["state"] == EVIDENCE_MIXED


def test_failure_cause_trend_present(service):
    _seed(service, 2, status="failed", error={"code": "TIMEOUT"})
    metrics = skill_quality_metrics(service.store, "test.skill")
    assert isinstance(metrics["failureCauseTrend"], list)
    assert metrics["failureCauses"].get("timeout", 0) >= 1


def test_tool_error_classified_as_tool_failure(service):
    _seed(service, 1, status="failed", error={"code": "TOOL_ERROR"})
    metrics = skill_quality_metrics(service.store, "test.skill")
    assert metrics["failureCauses"].get("tool_failure", 0) >= 1


def test_promotion_evidence_surfaces_sample_and_uncertainty(service):
    _seed(service, 2, version="1.0.0")
    evidence = promotion_evidence(service.store, "test.skill", "1.0.0")
    assert evidence["sample"]["executions"] == 2
    assert evidence["sample"]["reliable"] is False
    assert evidence["sample"]["successInterval"] is not None
    assert evidence["evidenceState"]["state"] == EVIDENCE_INSUFFICIENT
    assert any("insufficient" in w.lower() or "only" in w.lower() for w in evidence["warnings"])


def test_promotion_evidence_includes_regression_warning(service):
    service.store.upsert_skill(
        skill_id="test.skill", name="T", description="t", category="research",
        latest_version="2.0.0", status="draft", tags=[],
    )
    for version, status in (("1.0.0", "passed"), ("2.0.0", "failed")):
        service.store.save_version(
            {"id": "test.skill", "name": "T", "version": version, "description": "t",
             "category": "research", "status": "draft", "permissions": [], "requiredTools": []},
            f"hash-{version}", instructions=None,
        )
    service.store.save_evaluation(
        skill_id="test.skill", version="1.0.0", status="passed", dimensions=[],
        cases=[{"caseId": "c1", "name": "c1", "kind": "schema", "status": "passed"}],
    )
    service.store.save_evaluation(
        skill_id="test.skill", version="2.0.0", status="failed", dimensions=[],
        cases=[{"caseId": "c1", "name": "c1", "kind": "schema", "status": "failed"}],
    )
    evidence = promotion_evidence(service.store, "test.skill", "2.0.0")
    assert evidence["regression"] is not None
    assert evidence["regression"]["regressed"] is True
    assert any("regression" in w.lower() for w in evidence["warnings"])
