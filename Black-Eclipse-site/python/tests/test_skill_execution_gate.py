"""W5.1 — behavioural execution evaluation and the promotion gate."""

from __future__ import annotations

import os

import pytest

from harness.eclipse_memory import EclipseMemoryStore
from harness.skills.evaluation import (
    evaluate_skill,
    execution_gate_applies,
    promotion_gate,
)
from harness.skills.execution_eval import (
    InvocationResult,
    evaluate_skill_execution,
)
from harness.skills.manifest import SkillManifest
from harness.skills.registry import SkillRegistry


class _Invoker:
    def __init__(self, outputs=None, fail=False):
        self.outputs = list(outputs or [])
        self.fail = fail
        self.calls: list[str] = []

    def invoke(self, manifest, case, *, run_id):
        self.calls.append(run_id)
        if self.fail:
            return InvocationResult(
                ok=False, runId=run_id, status="failed", error="boom",
            )
        output = self.outputs.pop(0) if self.outputs else (
            "summary: done\nlimitations: example only\nevidence: tool result"
        )
        return InvocationResult(ok=True, runId=run_id, status="completed", output=output)


def _manifest(**overrides):
    payload = {
        "id": "learned.execution-demo",
        "name": "Execution demo",
        "version": "0.1.0",
        "description": "A learned procedure used to test behavioural evaluation.",
        "category": "quality",
        "tags": ["learned"],
        "status": "draft",
        "inputSchema": {
            "type": "object",
            "properties": {"objective": {"type": "string"}},
            "required": ["objective"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "limitations": {"type": "array", "items": {"type": "string"}},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary"],
        },
        "requiredTools": [],
        "requiredSkills": [],
        "permissions": ["data.read", "analysis.execute"],
        "riskLevel": "medium",
        "author": "test",
        "origin": "learning",
        "sourceRunId": "run_test_source",
        "evaluationStatus": "not_evaluated",
    }
    payload.update(overrides)
    return SkillManifest(**payload)


def _cases(count=3):
    return [
        {
            "caseId": f"case_{i}",
            "kind": "execution",
            "input": {"objective": "run"},
            "graders": [{"name": "honesty", "config": {
                "require_markers": ["limitation", "evidence"],
            }}],
        }
        for i in range(count)
    ]


def test_no_cases_is_needs_review_not_passed():
    result = evaluate_skill_execution(_manifest(), [], invoker=_Invoker())
    assert not result.ok
    assert result.status == "needs_review"
    assert "no execution cases" in result.reason


def test_too_few_cases_is_needs_review():
    result = evaluate_skill_execution(
        _manifest(), _cases(2), invoker=_Invoker(), min_cases=3,
    )
    assert not result.ok
    assert result.status == "needs_review"
    assert "at least 3" in result.reason


def test_no_runner_is_honest_needs_review():
    result = evaluate_skill_execution(_manifest(), _cases(3), invoker=None)
    assert not result.ok
    assert result.status == "needs_review"
    assert "no execution runner" in result.reason


def test_passing_execution_carries_run_ids_and_scores():
    invoker = _Invoker()
    result = evaluate_skill_execution(_manifest(), _cases(3), invoker=invoker)
    assert result.ok and result.status == "passed"
    assert result.passed == 3
    assert len(result.runIds) == 3
    assert result.graderScores["honesty"] == 1.0
    assert len(invoker.calls) == 3


def test_failing_execution_is_not_a_pass():
    result = evaluate_skill_execution(
        _manifest(), _cases(3), invoker=_Invoker(fail=True),
    )
    assert not result.ok
    assert result.status == "failed"
    assert result.passed == 0


def test_min_pass_rate_is_enforced():
    # Two dishonest outputs, one honest: 1/3 below the 0.8 default.
    invoker = _Invoker(outputs=[
        "summary: done",
        "summary: done",
        "summary: done\nlimitations: x\nevidence: y",
    ])
    result = evaluate_skill_execution(_manifest(), _cases(3), invoker=invoker)
    assert not result.ok
    assert result.passed == 1


def test_gate_applies_only_to_learned_or_system_authored_skills():
    assert execution_gate_applies(_manifest())
    assert not execution_gate_applies(_manifest(id="skill.other", origin="author"))
    assert not execution_gate_applies(_manifest(id="research.planning", origin="builtin"))


def test_promotion_gate_refuses_static_only_evaluation():
    gate = promotion_gate(
        {"status": "passed", "dimensions": [], "skillId": "learned.x"},
        require_execution=True,
    )
    assert not gate["passed"]
    assert "no execution run ids" in gate["reason"]


class _Store:
    def __init__(self, runs):
        self._runs = runs

    def list_executions(self, skill_id, limit=50):
        return [{"runId": run} for run in self._runs]


def test_promotion_gate_requires_existing_run_ids():
    gate = promotion_gate(
        {"status": "passed", "dimensions": [], "skillId": "learned.x",
         "executionRunIds": ["run_a"]},
        require_execution=True, store=_Store([]),
    )
    assert not gate["passed"]
    assert "do not exist" in gate["reason"]

    gate = promotion_gate(
        {"status": "passed", "dimensions": [], "skillId": "learned.x",
         "executionRunIds": ["run_a"]},
        require_execution=True, store=_Store(["run_a"]),
    )
    assert gate["passed"]


@pytest.fixture()
def learned_registry(tmp_path):
    store = EclipseMemoryStore(os.path.join(str(tmp_path), "eclipse-memory.db"))
    registry = SkillRegistry(store)
    manifest = _manifest()
    store.upsert_skill(
        skill_id=manifest.id, name=manifest.name, description=manifest.description,
        category=manifest.category, latest_version=manifest.version,
        status="draft", tags=manifest.tags,
    )
    store.save_version(manifest.model_dump(), manifest.content_hash())
    store.replace_evaluation_cases(manifest.id, manifest.version, _cases(3))
    registry.load_stored(manifest.id)
    yield registry, store
    store.close()


def test_evaluate_skill_persists_execution_evidence(learned_registry, monkeypatch):
    monkeypatch.setenv("HARNESS_SKILL_EXEC_EVAL", "on")
    registry, store = learned_registry
    report = evaluate_skill(
        "learned.execution-demo", "0.1.0", registry,
        require_execution=True, execution_invoker=_Invoker(),
    )
    execution = report["execution"]
    assert execution["ok"] is True, report
    assert execution["ok"] is True
    stored = store.get_evaluation(report["evaluationId"])
    assert stored["executionRunIds"] == list(execution["runIds"])
    assert stored["executionScores"]["honesty"] == 1.0
    assert any(d["name"] == "execution_eval" for d in stored["dimensions"])
    # A draft becomes `testing` (non-interactive only) so the real runtime can
    # execute it; it is still not enabled.
    assert store.get_version("learned.execution-demo", "0.1.0")["status"] == "testing"

    # The production invoker writes a SkillExecution row per run; mirror that so
    # the gate can prove provenance, not just a list of ids.
    for run_id in execution["runIds"]:
        store.create_execution(
            run_id=run_id, skill_id="learned.execution-demo", version="0.1.0",
            manifest_hash=None, parent_run_id=None, execution_mode="evaluation",
            actor="test", input_data={"objective": "run"},
        )

    gate = promotion_gate(
        stored, require_execution=True, store=store, allow_needs_review=True,
    )
    assert gate["passed"], gate


def test_evaluate_skill_without_runner_is_needs_review(learned_registry):
    registry, _ = learned_registry
    report = evaluate_skill(
        "learned.execution-demo", "0.1.0", registry,
        require_execution=True, execution_invoker=None,
    )
    assert report["status"] == "needs_review"
    dimension = next(d for d in report["dimensions"] if d["name"] == "execution_eval")
    assert dimension["status"] == "needs_review"
    assert "no execution runner" in dimension["detail"]


def test_failed_execution_is_held_for_a_bounded_backoff(learned_registry, monkeypatch):
    monkeypatch.setenv("HARNESS_SKILL_EXEC_EVAL", "on")
    monkeypatch.setenv("HARNESS_SKILL_EVAL_RETRY_HOURS", "12")
    registry, _ = learned_registry
    invoker = _Invoker(fail=True)
    first = evaluate_skill(
        "learned.execution-demo", "0.1.0", registry,
        require_execution=True, execution_invoker=invoker,
    )
    assert first["execution"]["status"] == "failed"
    assert first["status"] == "needs_review"
    attempts = len(invoker.calls)
    second = evaluate_skill(
        "learned.execution-demo", "0.1.0", registry,
        require_execution=True, execution_invoker=invoker,
    )
    assert second["skipped"] is True
    assert second["reason"] == "execution_retry_backoff"
    assert len(invoker.calls) == attempts, "an unchanged failed attempt must not re-run"


def test_flag_off_preserves_static_behaviour(learned_registry):
    registry, _ = learned_registry
    report = evaluate_skill(
        "learned.execution-demo", "0.1.0", registry,
        require_execution=False,
    )
    assert report["status"] == "passed"
    assert not any(d["name"] == "execution_eval" for d in report["dimensions"])
