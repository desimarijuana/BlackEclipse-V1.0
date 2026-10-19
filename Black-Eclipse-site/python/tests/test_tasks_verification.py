"""Round 4 (W8.4): the task-type verifier — completion is evidence, not prose.

These pin the dispatch rule (no taskType ⇒ no verifier, pre-W8 behavior), each
built-in verifier's accept/reject boundary, the deliverable-coverage rule, and
the honest refusal for an unknown verifier or a crashing one.
"""

from __future__ import annotations

import pytest

from harness.tasks import verification as verification_module
from harness.tasks.model import GoalContract, Task, TaskType
from harness.tasks.verification import TaskVerification, verify_task

NOW = "2026-01-01T00:00:00+00:00"


def _task(task_type=None, contract=None) -> Task:
    return Task(
        id="task_x", title="t", task_type=task_type, goal_contract=contract,
        created_at=NOW, updated_at=NOW,
    )


def _record(command_class: str, exit_code: int) -> dict:
    return {
        "commandClass": command_class, "exitCode": exit_code,
        "outputDigest": "d" * 16, "argv": ["x"], "startedAt": NOW,
    }


CODE_CONTRACT = GoalContract(
    objective="build a greeting app", deliverables=["greeting app"],
    acceptance=["the produced files exist", "tests pass"],
)


def _code_evidence(passing: bool = True) -> dict:
    return {"codeVerification": {
        "records": [_record("python_test", 0 if passing else 1)],
        "artifacts": [], "reviews": [],
    }}


# ── Dispatch ──────────────────────────────────────────────────────────────────


def test_no_task_type_means_no_verifier():
    assert verify_task(_task(), status="completed") is None


def test_unknown_task_type_is_a_refusal_not_a_pass(monkeypatch):
    task = _task(task_type=TaskType.CODE, contract=CODE_CONTRACT)
    monkeypatch.setitem(verification_module._VERIFIERS, "code", None)
    verdict = verify_task(task, status="completed", evidence=_code_evidence(),
                          artifacts=[{"label": "greeting app"}])
    assert verdict is not None and not verdict.ok
    assert "no verifier is registered" in verdict.missing[0]


def test_a_crashing_verifier_refuses(monkeypatch):
    class Boom:
        task_type = "code"

        def verify(self, ctx):
            raise RuntimeError("boom")

    monkeypatch.setitem(verification_module._VERIFIERS, "code", Boom())
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=CODE_CONTRACT), status="completed",
    )
    assert verdict is not None and not verdict.ok
    assert "failed to run" in verdict.missing[0]


# ── Code ──────────────────────────────────────────────────────────────────────


def test_code_passes_with_passing_tests_and_a_matching_artifact():
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=CODE_CONTRACT),
        status="completed", evidence=_code_evidence(),
        artifacts=[{"uri": "/w/greeting.py", "kind": "file", "label": "greeting app"}],
    )
    assert verdict.ok, verdict.summary()
    names = {c.name for c in verdict.checks}
    assert {"run_completed", "tests", "deliverable:greeting app"} <= names


def test_code_rejects_failing_tests_even_when_the_run_completed():
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=CODE_CONTRACT),
        status="completed", evidence=_code_evidence(passing=False),
        artifacts=[{"label": "greeting app"}],
    )
    assert not verdict.ok
    assert "no successful tests run was recorded" in verdict.missing


def test_code_rejects_missing_artifact_for_a_declared_deliverable():
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=CODE_CONTRACT),
        status="completed", evidence=_code_evidence(), artifacts=[],
    )
    assert not verdict.ok
    assert any("greeting app" in m and "artifact" in m for m in verdict.missing)


def test_code_requires_no_test_record_when_acceptance_never_mentions_tests():
    contract = GoalContract(
        objective="build a script", deliverables=["sync script"],
        acceptance=["the produced files exist"],
    )
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=contract),
        status="completed", evidence={"codeVerification": {"records": [], "artifacts": []}},
        artifacts=[{"label": "sync script"}],
    )
    assert verdict.ok, verdict.summary()


def test_code_build_signal_requires_a_build_record():
    contract = GoalContract(
        objective="x", deliverables=["app"],
        acceptance=["the project builds without errors"],
    )
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=contract),
        status="completed", evidence=_code_evidence(), artifacts=[{"label": "app"}],
    )
    assert not verdict.ok
    assert "no successful build run was recorded" in verdict.missing


def test_code_run_status_not_completed_is_a_refusal():
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=CODE_CONTRACT),
        status="failed", evidence=_code_evidence(),
        artifacts=[{"label": "greeting app"}],
    )
    assert not verdict.ok
    assert "the run did not complete" in verdict.missing


# ── Research / finance ────────────────────────────────────────────────────────


def test_research_requires_recorded_sources():
    contract = GoalContract(objective="r", acceptance=["claims trace to named sources"])
    ok = verify_task(
        _task(task_type=TaskType.RESEARCH, contract=contract), status="completed",
        evidence={"research": {"sources": [{"canonicalUrl": "https://x"}], "claims": []}},
    )
    assert ok.ok
    rejected = verify_task(
        _task(task_type=TaskType.RESEARCH, contract=contract), status="completed",
        evidence={"research": {"sources": [], "claims": [{"text": "c"}]}},
    )
    assert not rejected.ok
    assert "no sources were recorded" in rejected.missing[0]


def test_finance_requires_provenance_evidence():
    contract = GoalContract(objective="f", acceptance=["financial claims carry provenance"])
    rejected = verify_task(
        _task(task_type=TaskType.FINANCE, contract=contract), status="completed",
        evidence={},
    )
    assert not rejected.ok
    assert "provenance" in rejected.missing[0]
    ok = verify_task(
        _task(task_type=TaskType.FINANCE, contract=contract), status="completed",
        evidence={"research": {"sources": [{"canonicalUrl": "https://x"}]}},
    )
    assert ok.ok


# ── Document / workflow / general ────────────────────────────────────────────


def test_document_requires_a_delivered_artifact_or_document_record():
    contract = GoalContract(objective="d", acceptance=["the document artifact is delivered"])
    assert not verify_task(
        _task(task_type=TaskType.DOCUMENT, contract=contract), status="completed",
    ).ok
    assert verify_task(
        _task(task_type=TaskType.DOCUMENT, contract=contract), status="completed",
        artifacts=[{"uri": "artifact://a1", "kind": "document"}],
    ).ok


def test_workflow_requires_observed_steps_and_a_result():
    contract = GoalContract(objective="w", acceptance=["the workflow completed with an observable result"])
    task = _task(task_type=TaskType.WORKFLOW, contract=contract)
    assert not verify_task(task, status="completed", metrics={"toolCalls": 0}).ok
    assert verify_task(
        task, status="completed", metrics={"toolCalls": 3},
        evidence={"output": "done"},
    ).ok


def test_general_requires_a_recorded_result():
    contract = GoalContract(objective="g", acceptance=["the requested result is delivered"])
    task = _task(task_type=TaskType.GENERAL, contract=contract)
    assert not verify_task(task, status="completed").ok
    assert verify_task(task, status="completed", artifacts=[{"uri": "artifact://a"}]).ok


def test_verification_summary_is_bounded_and_plain():
    verdict = TaskVerification("code", [], ["a", "b", "c", "d", "e", "f"])
    assert verdict.summary().startswith("verification failed:")
    assert verdict.summary().count(";") == 4  # five named, never the whole log
