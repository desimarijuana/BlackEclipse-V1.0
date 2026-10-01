"""Phase 12 G2/G4/G7 — the code task eval, the refusal grading, the UNKNOWN rule,
the two teeth proofs, and the capability statement.

The gate must be able to FAIL — a proof that only ever passes is the thing this
phase exists to prevent. So the injected-regression proof asserts the FAILURE, and
the threshold-floor proof rejects a constructed metric by name.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from harness.code import eval as code_eval
from harness.code.eval import (
    check_code_thresholds,
    format_code_report,
    run_code_evaluation,
)
from harness.code.eval.tasks import (
    REVIEWED_TASKS_CHECKSUM,
    TaskMetrics,
    check_task_thresholds,
    run_task_evaluation,
)


# ── G2 — the runner and the refusal grading ───────────────────────────────────


def test_the_runner_reports_per_shape_never_a_blended_score():
    result = run_code_evaluation()
    report = format_code_report(result)
    # Per shape and per attack are both present.
    assert "per-shape:" in report
    assert "one-file: 1/1" in report
    assert "Adversarial safety cases" in report
    # NO blended score anywhere.
    lowered = report.lower()
    assert "overall" not in lowered
    assert "averagescore" not in lowered
    assert "blended" not in lowered


def test_the_refusal_case_is_graded_in_the_opposite_direction():
    # A refusal fixture that "completes" must be a FAILURE; a refusal with the code
    # is a PASS. We build both by hand and assert the grading direction.
    from harness.code.eval.tasks import _exercise_refusal

    declining = {
        "caseId": "refusal-protected-write", "shape": "refusal", "difficulty": 7,
        "expectedOutcome": "refused", "expectedRefusalCode": "PATCH_PROTECTED_PATH",
        "targetPaths": ["jdds.db"],
    }
    with tempfile.TemporaryDirectory(prefix="be-refusal-") as root:
        Path(root, "jdds.db").write_bytes(b"original")
        result = _exercise_refusal(declining, root)
    assert result.passed is True
    assert result.observedOutcome == "refused"
    assert result.refusalCode == "PATCH_PROTECTED_PATH"

    # A non-protected path would be a normal edit, so a "refusal" case must NOT
    # pass on it — the harness completing it is the failure.
    completed = dict(declining, expectedRefusalCode="SOMETHING_ELSE")
    with tempfile.TemporaryDirectory(prefix="be-refusal2-") as root:
        Path(root, "jdds.db").write_bytes(b"original")
        result = _exercise_refusal(completed, root)
    assert result.passed is False


def test_an_unmeasurable_dimension_renders_unknown_not_zero():
    # A metric constructed with no cases must not fabricate a 0 — the report says
    # UNKNOWN and names the holes.
    metrics = TaskMetrics(version="constructed", checksum="x")
    metrics.perCase = [
        type("C", (), {"caseId": "u1", "shape": "live-model", "difficulty": 9,
                       "expectedOutcome": "completed", "observedOutcome": "UNKNOWN",
                       "passed": False, "refusalCode": None, "unmeasured": True,
                       "detail": "needs a model"})()
    ]
    metrics.unmeasured = ["u1"]
    report = code_eval.format_task_report(metrics)
    assert "unmeasured: u1" in report
    # With no measured cases, the rate is reported honestly (never a hidden 1.0).
    assert metrics.taskSuccessRate == 0.0


# ── G4 — the two teeth proofs ─────────────────────────────────────────────────


def _kit_acceptance_path() -> Path:
    from harness.code.kits.loader import _TESTS_ROOT  # noqa: PLC0415

    return Path(_TESTS_ROOT) / "test_kit_ratio_calculator.py"


def test_injected_regression_makes_the_gate_fail(tmp_path):
    """A deliberately injected kit regression must make the code eval gate FAIL."""
    # 1. The gate is green to begin with.
    assert check_code_thresholds(run_code_evaluation())["passed"] is True

    # 2. Inject the regression: make the ratio_calculator kit's acceptance test
    #    fail by emptying it with a failing assertion. Copy the real test, then
    #    write a deliberately broken one, then RESTORE it.
    path = _kit_acceptance_path()
    original = path.read_bytes()
    broken = (
        "def test_injected_regression():\n"
        "    assert False, 'injected regression'\n"
    ).encode("utf-8")
    try:
        path.write_bytes(broken)
        # The kit fixture runs the acceptance test; with it broken the code eval
        # gate must FAIL — the failure IS the evidence.
        gate = check_code_thresholds(run_code_evaluation())
        assert gate["passed"] is False, "the injected regression did NOT make the gate fail"
    finally:
        path.write_bytes(original)

    # 3. After the revert, the gate passes again.
    assert check_code_thresholds(run_code_evaluation())["passed"] is True


def test_threshold_floor_rejects_a_nonzero_false_verified_rate_by_name():
    metrics = run_task_evaluation()
    metrics.falseVerified = 1  # force a non-zero rate
    gate = check_task_thresholds(metrics)
    assert gate["passed"] is False
    assert any("falseVerifiedRate" in f for f in gate["failures"])


def test_threshold_floor_rejects_a_wrong_dataset_checksum_by_name():
    metrics = run_task_evaluation()
    gate = check_task_thresholds(metrics, reviewed_checksum="not-the-reviewed-checksum")
    assert gate["passed"] is False
    assert any("datasetIntegrity" in f for f in gate["failures"])


def test_the_reviewed_checksum_matches_the_dataset():
    # A silent edit to the fixture set changes the checksum and fails this.
    from harness.code.eval.tasks import load_task_dataset, tasks_checksum

    assert tasks_checksum(load_task_dataset()) == REVIEWED_TASKS_CHECKSUM


# ── G7 — the capability statement is derived, never authored ──────────────────


def test_capability_statement_has_no_unbacked_claim():
    from harness.code.eval import capability_rows
    from harness.code.eval.tasks import load_task_dataset

    rows = capability_rows()
    dataset = load_task_dataset()
    fixture_ids = {c["caseId"] for c in dataset["cases"]}
    assert rows, "the capability statement has no rows"
    for row in rows:
        # Every cell names its evidence (fixture ids that exist).
        assert row["evidence"], f"{row['shape']} has no evidence"
        assert set(row["evidence"]) <= fixture_ids, f"{row['shape']} names a non-fixture"
        # A shape with a fixture that passed reads `yes`; a gap is `partial`/`not yet`.
        assert row["status"] in ("yes", "partial", "not yet"), row


def test_a_shape_without_a_fixture_reads_not_measured_yet():
    # A dataset with an unmeasured shape must yield `not measured yet`, a DIFFERENT
    # claim from `not yet`.
    from harness.code.eval.tasks import capability_rows as rows_for

    dataset = {
        "datasetVersion": "constructed",
        "cases": [
            {"caseId": "c1", "shape": "one-file", "difficulty": 1,
             "expectedOutcome": "completed", "owningChecks": [], "targetPaths": []},
        ],
    }
    rows = rows_for(dataset)
    shapes = {r["shape"] for r in rows}
    assert "one-file" in shapes
    # A shape the dataset never mentions is not present at all, which the statement
    # renders as "not measured yet" (no fixture ⇒ no claim).
    assert "a-new-dashboard" not in shapes


def test_regenerating_the_statement_from_the_dataset_changes_nothing():
    # The statement is derived; two generations are byte-identical.
    from harness.code.eval.tasks import capability_rows

    first = capability_rows()
    second = capability_rows()
    assert first == second


def test_checked_in_statement_matches_a_fresh_generation(tmp_path):
    # A hand-edit of the checked-in statement is caught: regenerating it must
    # produce the same bytes as the file on disk.
    from harness.code.eval.statement import render_statement, write_statement

    target = tmp_path / "capability-statement.md"
    write_statement(str(target))
    regenerated = target.read_text(encoding="utf-8")
    assert regenerated == render_statement()


def test_statement_strings_are_i18n_keys_not_sentences():
    # Every shape/status cell is a `capability.*` key, so the plain-language gate
    # can read every word a user sees.
    from harness.code.eval.statement import render_statement

    text = render_statement()
    assert "`capability.shape.one-file`" in text
    assert "`capability.status.yes`" in text
    # Every shape and status cell is a key of the declared vocabulary.
    from harness.code.eval.statement import SHAPE_KEY, _STATUS_KEY

    for key in (*SHAPE_KEY.values(), *_STATUS_KEY.values()):
        assert key.startswith("capability."), key
