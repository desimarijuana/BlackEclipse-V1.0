"""Skill usefulness metrics (Phase 7) — measured from real execution records.

Correctness:
  * metrics are derived from actual `SkillExecution` rows, never fabricated;
  * an empty sample reports None rates, not a misleading zero;
  * tool-budget failures and invalid outputs are counted;
  * deprecation is advisory only and never promotes/demotes a skill;
  * version regression comparison is deterministic and explicit.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryStore
from harness.eclipse_memory.skill_quality import (
    compare_versions,
    promotion_evidence,
    skill_quality_metrics,
)


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-skillq-")
    s = EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db"))
    yield s
    s.close()


def _exec(store, *, status="completed", validated=True, metrics=None, error=None, version="1.0.0", skill_id="test.skill"):
    run_id = store.create_execution(
        run_id=f"run_{os.urandom(4).hex()}", skill_id=skill_id, version=version,
        manifest_hash="h", parent_run_id=None, execution_mode="interactive",
        actor="local", input_data={},
    )
    store.finish_execution(
        run_id, status=status, output="{}", error=error, output_validated=validated,
        metrics=metrics or {"toolCalls": 2, "durationMs": 100},
    )
    return run_id


def test_empty_sample_reports_unknown_not_zero(store):
    metrics = skill_quality_metrics(store, "test.skill")
    assert metrics["executions"] == 0
    assert metrics["successRate"] is None
    assert metrics["failureRate"] is None
    assert metrics["usefulness"]["score"] is None


def test_success_and_validation_rates(store):
    _exec(store, status="completed", validated=True)
    _exec(store, status="completed", validated=True)
    _exec(store, status="failed", validated=False, error={"code": "SKILL_FAILED", "message": "x"})
    _exec(store, status="completed", validated=False)
    metrics = skill_quality_metrics(store, "test.skill")
    assert metrics["executions"] == 4
    assert metrics["completed"] == 3
    assert metrics["failed"] == 1
    assert metrics["successRate"] == 0.75
    assert metrics["failureRate"] == 0.25
    assert metrics["outputValidationRate"] == 0.5
    assert metrics["invalidOutputCount"] == 1


def test_tool_budget_failure_rate(store):
    _exec(store, status="completed", validated=True)
    _exec(store, status="failed", validated=False,
          error={"code": "TOOL_BUDGET_EXCEEDED", "message": "budget"})
    metrics = skill_quality_metrics(store, "test.skill")
    assert metrics["toolBudgetFailureRate"] == 0.5


def test_version_scoping(store):
    _exec(store, version="1.0.0", status="completed")
    _exec(store, version="2.0.0", status="completed")
    assert skill_quality_metrics(store, "test.skill", version="1.0.0")["executions"] == 1
    assert skill_quality_metrics(store, "test.skill")["executions"] == 2


def test_deprecation_recommendation_is_advisory(store):
    for _ in range(4):
        _exec(store, status="failed", validated=False, error={"code": "SKILL_FAILED", "message": "x"})
    metrics = skill_quality_metrics(store, "test.skill")
    assert metrics["deprecation"]["recommend"] is True
    # The recommendation does not change any skill status by itself.
    assert metrics["executions"] == 4


def test_compare_versions_detects_regression(store):
    for _ in range(3):
        _exec(store, version="1.0.0", status="completed", validated=True)
    _exec(store, version="2.0.0", status="completed", validated=True)
    _exec(store, version="2.0.0", status="failed", validated=False, error={"code": "SKILL_FAILED", "message": "x"})
    comparison = compare_versions(store, "test.skill", "1.0.0", "2.0.0")
    assert comparison["regressed"] is True
    assert any("successRate" in r for r in comparison["regressions"])


def test_promotion_evidence_states_it_is_advisory(store):
    _exec(store, version="1.0.0", status="completed", validated=True)
    evidence = promotion_evidence(store, "test.skill", "1.0.0")
    assert evidence["executionMetrics"]["executions"] == 1
    assert "operator-gated" in evidence["note"]
    assert evidence["evaluation"] is None  # no evaluation recorded
