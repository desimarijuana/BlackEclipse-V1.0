"""Phase 20 (ADR-H193) — the capability-class registry, the runner and the gate.

Every class is registered; an unmeasured class states its reason and is never
reported as a pass. A measured class may not silently regress to unmeasured.
The generated statement carries every row and the unmeasured count.
"""

from __future__ import annotations

from harness.code.eval.capabilities import (
    CLASSES,
    MEASURED_BASELINE,
    CapabilityReport,
    ClassResult,
    check_capability_floors,
    format_capability_report,
    run_capability_eval,
)


def _camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(part.capitalize() for part in rest)


def test_every_class_is_named_and_unmeasured_classes_state_a_reason():
    assert CLASSES
    ids = [c.id for c in CLASSES]
    assert len(ids) == len(set(ids))
    for klass in CLASSES:
        assert klass.label_key == f"capability.class.{_camel(klass.id)}", klass.id
        assert klass.module, klass.id
        if klass.kind == "unmeasured":
            assert klass.reason, klass.id
            assert klass.id not in MEASURED_BASELINE
        else:
            assert klass.selectors, klass.id
            assert klass.id in MEASURED_BASELINE


def test_the_runner_grades_the_real_modules_and_reports_unmeasured_honestly():
    report = run_capability_eval()
    assert report.passed, [r.detail for r in report.failed]
    # Unmeasured classes are reported as unmeasured WITH a reason — not pass/fail.
    assert report.unmeasured
    for result in report.unmeasured:
        assert result.detail
    assert check_capability_floors(report)["passed"] is True


def test_a_measured_class_regressing_to_unmeasured_fails_the_gate():
    report = CapabilityReport(results=[
        ClassResult(id="bulk_collection", status="unmeasured", detail="gone"),
        ClassResult(id="artifact_verification", status="passed", detail="ok"),
    ])
    verdict = check_capability_floors(report)
    assert verdict["passed"] is False
    assert any("bulk_collection" in failure for failure in verdict["failures"])


def test_a_failed_class_fails_the_gate():
    report = CapabilityReport(results=[
        ClassResult(id="bulk_collection", status="failed", detail="ceiling not enforced"),
    ])
    verdict = check_capability_floors(report)
    assert verdict["passed"] is False
    assert any("ceiling" in failure for failure in verdict["failures"])


def test_the_report_names_the_unmeasured_classes_never_hides_them():
    text = format_capability_report(run_capability_eval())
    assert "not measured yet" in text
    for result in run_capability_eval().unmeasured:
        assert result.id in text


def test_the_statement_contains_every_class_and_the_unmeasured_count():
    from harness.code.eval.statement import render_statement

    text = render_statement()
    assert "Every capability class" in text
    for klass in CLASSES:
        assert f"`{klass.label_key}`" in text, klass.id
    report = run_capability_eval()
    assert f"{len(report.unmeasured)} of {len(report.results)} classes are not measured yet." in text


def test_the_committed_statement_matches_a_fresh_generation():
    from harness.code.eval.statement import STATEMENT_PATH, render_statement

    with open(STATEMENT_PATH, encoding="utf-8") as handle:
        committed = handle.read()
    assert committed == render_statement()
