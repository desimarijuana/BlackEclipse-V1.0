"""Skill quality over time (Phase 6): trends, sample warnings, failure causes,
same-evaluation-case comparison. Derived from real execution rows only."""

from __future__ import annotations

import pytest

from harness.eclipse_memory import EclipseMemoryService
from harness.eclipse_memory.skill_quality import (
    compare_evaluation_cases,
    skill_quality_metrics,
    version_quality_history,
)


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


def _seed(service, n, *, status="completed"):
    ids = []
    for _ in range(n):
        eid = service.store.create_execution(
            run_id="r", skill_id="test.skill", version="1.0.0", manifest_hash="h",
            parent_run_id=None, execution_mode="interactive", actor="local", input_data={},
        )
        service.store.finish_execution(
            eid, status=status, output="x", output_validated=(status == "completed"),
            error={"code": "OUTPUT_VALIDATION_FAILED"} if status != "completed" else None,
            duration_ms=100,
        )
        ids.append(eid)
    return ids


def test_low_sample_is_flagged(service):
    _seed(service, 2)
    metrics = skill_quality_metrics(service.store, "test.skill")
    assert metrics["executions"] == 2
    assert metrics["sampleReliable"] is False
    assert metrics["sampleWarning"]
    assert metrics["successInterval"] is not None


def test_reliable_sample_not_flagged(service):
    _seed(service, 20)
    metrics = skill_quality_metrics(service.store, "test.skill")
    assert metrics["sampleReliable"] is True
    assert metrics["sampleWarning"] is None
    assert metrics["successInterval"] is not None


def test_failure_cause_clustering(service):
    _seed(service, 2, status="failed")
    metrics = skill_quality_metrics(service.store, "test.skill")
    assert metrics["failureCauses"].get("output_validation", 0) >= 1


def test_time_weighted_success_present(service):
    _seed(service, 3)
    metrics = skill_quality_metrics(service.store, "test.skill")
    assert metrics["timeWeightedSuccessRate"] is not None


def test_trend_series_present(service):
    _seed(service, 3)
    metrics = skill_quality_metrics(service.store, "test.skill")
    assert isinstance(metrics["trend"], list)


def test_same_case_comparison(service):
    service.store.save_evaluation(
        skill_id="test.skill", version="1.0.0", status="passed", dimensions=[],
        cases=[{"caseId": "c1", "name": "c1", "kind": "schema", "status": "passed"}],
    )
    service.store.save_evaluation(
        skill_id="test.skill", version="2.0.0", status="failed", dimensions=[],
        cases=[{"caseId": "c1", "name": "c1", "kind": "schema", "status": "failed"},
               {"caseId": "c2", "name": "c2", "kind": "schema", "status": "passed"}],
    )
    comparison = compare_evaluation_cases(service.store, "test.skill", "1.0.0", "2.0.0")
    assert comparison["comparable"] is True
    assert "c1" in comparison["sharedCases"]
    assert any(r["caseId"] == "c1" for r in comparison["caseRegressions"])
    assert "c2" in comparison["addedCases"]


def test_evaluation_case_status_is_persisted(service):
    service.store.save_evaluation(
        skill_id="test.skill", version="1.0.0", status="failed", dimensions=[],
        cases=[{"caseId": "c1", "name": "c1", "kind": "schema", "status": "failed"}],
    )
    cases = service.store.list_evaluation_cases("test.skill", "1.0.0")
    assert cases and cases[0].get("status") == "failed"


def test_version_history_only_includes_executed(service):
    _seed(service, 1)
    service.store.upsert_skill(
        skill_id="test.skill", name="T", description="t", category="research",
        latest_version="1.0.0", status="enabled", tags=[],
    )
    service.store.save_version(
        {"id": "test.skill", "name": "T", "version": "1.0.0", "description": "t",
         "category": "research", "status": "enabled", "permissions": [], "requiredTools": []},
        "hash-1", instructions=None,
    )
    history = version_quality_history(service.store, "test.skill")
    assert len(history) == 1
    assert history[0]["version"] == "1.0.0"
