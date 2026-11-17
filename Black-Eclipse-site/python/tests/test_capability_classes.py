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

import pytest  # noqa: E402  (kept next to its use, after the module imports)

try:  # the measured classes run the VENDORED analysis interpreter.
    from harness.code.execution import interpreter_path as _interpreter_path

    _ANALYSIS_INTERPRETER = _interpreter_path()
except Exception:  # noqa: BLE001 - environment dependent
    _ANALYSIS_INTERPRETER = ""
if not _ANALYSIS_INTERPRETER:
    pytest.skip(
        "the vendored analysis interpreter is not provisioned here "
        "(run `npm run setup:python`)",
        allow_module_level=True,
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
    # Round 3 / W8 (ADR-H296): EVERY registered class is now measured. A
    # capability that is published but not graded is a capability a reader
    # cannot trust, and the `messaging_gateway` class - which named something
    # that is not built - was retired rather than left as an excuse.
    #
    # The gate for a class that IS unmeasured stays: it must carry a reason,
    # and it must never be reported as a pass or a failure.
    assert not report.unmeasured, [
        r.id for r in report.unmeasured
    ]
    for result in report.measured:
        assert result.status in ("passed", "failed")
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
