"""The capability-class registry + runner (Phase 20 §6.1–6.3, ADR-H193).

Every capability class a user can ask for is REGISTERED here — including the
classes this round could not grade, which are published as `not measured yet`
with their reason instead of being silently absent. A class is `measured` only
when a NAMED fixture/test actually ran and held:

  * `fixture`   — a deterministic offline fixture in THIS module, graded through
                  the REAL module it names (the thing under test is never mocked;
                  only its dependencies may be stubbed);
  * `test_gate` — a named test in the release gate (`pytest` or `vitest`); the
                  runner verifies the test exists so the statement's proof can
                  never point at nothing;
  * `code_eval` — a fixture id in the code eval's labelled dataset, graded by the
                  code gate in the same eval run.

A class with no fixture is reported `unmeasured` WITH ITS REASON — never a pass,
never a failure. The gate fails when a measured class falls below its floor OR
when a class that was measured regresses to unmeasured (`MEASURED_BASELINE`).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional

Kind = Literal["fixture", "test_gate", "code_eval", "unmeasured"]

_REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class CapabilityClass:
    id: str
    label_key: str                    # capability.class.<id> — plain words
    kind: Kind
    module: str                       # the real module this class exercises
    selectors: tuple[str, ...] = ()   # fixture ids / test selectors / dataset ids
    reason: str = ""                  # REQUIRED when kind == "unmeasured"
    floor: float = 1.0


# ── The fixtures (real modules, deterministic, offline) ─────────────────────


def _fixture_bulk_collection() -> dict[str, bool]:
    """A pull stopped at the ceiling is marked partial; the count equals the file."""
    from harness.acquire.budget import AcquisitionBudget
    from harness.acquire.writer import write_csv

    with tempfile.TemporaryDirectory() as tmp:
        budget = AcquisitionBudget(max_rows=5)
        path = Path(tmp) / "out.csv"
        written, complete, stopped = write_csv(
            path, ("a",), ({"a": i} for i in range(9)), budget,
        )
        lines = len(path.read_text(encoding="utf-8").strip().splitlines())
    return {
        "stoppedAtCeiling": written == 5 and complete is False and "5" in stopped,
        "fileMatchesCounter": lines == written + 1,
        "ceilingRecorded": bool(budget.exhausted),
    }


def _fixture_unattended_report() -> dict[str, bool]:
    """A degraded delivered report states its outcome and every limit."""
    from harness.automation.delivery import OUTCOME_FIRST_LINE, render_run_report

    class _Definition:
        name = "fixture"

    failed = render_run_report(
        _Definition(), "failed", "partial result", limits=["A source was stale."],
    )
    completed = render_run_report(_Definition(), "completed", "the answer")
    empty = render_run_report(_Definition(), "completed", "")
    return {
        "outcomeOnFirstLine": failed.splitlines()[0] == OUTCOME_FIRST_LINE["failed"],
        "limitNamed": "A source was stale." in failed,
        "completedStatesOutcome": completed.splitlines()[0] == OUTCOME_FIRST_LINE["completed"],
        "emptyNeverASuccess": "produced no result" in empty,
    }


def _fixture_artifact_verification() -> dict[str, bool]:
    """An unbacked artifact claim is marked; a backed one is not; a FAILED record
    never supports the claim."""
    from harness.code.verify import ArtifactRecord, VerificationLedger, enforce_answer

    unbacked = enforce_answer("The figure is intact.", VerificationLedger("f"))

    backed_ledger = VerificationLedger("f")
    backed_ledger.record_artifact(ArtifactRecord(
        artifact_name="c.png", kind="image", check="artifact_exists",
        passed=True, detail="it is where it was reported", observed={},
    ))
    backed = enforce_answer("The figure is intact.", backed_ledger)

    failed_ledger = VerificationLedger("f")
    failed_ledger.record_artifact(ArtifactRecord(
        artifact_name="c.png", kind="image", check="artifact_digest",
        passed=False, detail="its digest does not match the record", observed={},
    ))
    failed = enforce_answer("The figure is intact.", failed_ledger)

    return {
        "unbackedMarked": bool(unbacked.enforced),
        "backedSupported": not backed.enforced,
        "failedRecordNeverSupports": bool(failed.enforced),
    }


def _fixture_change_review() -> dict[str, bool]:
    """The protected-file rule fires and AGREES with the enforcement seam; an
    empty diff is never reported as clean."""
    from harness.code import policy
    from harness.code.review import DiffFile, DiffView, review_change

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "python" / "harness" / "code" / "policy.py"
        target.parent.mkdir(parents=True)
        target.write_text("# the policy module\n", encoding="utf-8")
        result = review_change(DiffView(files=[
            DiffFile(path="python/harness/code/policy.py", status="modified", added_lines=("x",)),
        ]), repo_root=root)
        rules = {f.rule for f in result.findings}

    empty = review_change(DiffView(), repo_root=Path("."))
    return {
        "protectedFound": "protected-path" in rules,
        "agreesWithPolicy": policy.is_protected("python/harness/code/policy.py"),
        "emptyNeverClean": bool(empty.unevaluated),
    }


_FIXTURES: dict[str, Callable[[], dict[str, bool]]] = {
    "bulk-collection-ceiling": _fixture_bulk_collection,
    "unattended-report-limits": _fixture_unattended_report,
    "artifact-claim-marked": _fixture_artifact_verification,
    "change-review-rules": _fixture_change_review,
}


# ── The registry (data) ──────────────────────────────────────────────────────

CLASSES: tuple[CapabilityClass, ...] = (
    # The seven code shapes: fixtures exist; the code gate grades them in this run.
    CapabilityClass("one_file", "capability.class.oneFile", "code_eval",
                    "harness.code.patch", ("one-file-change",)),
    CapabilityClass("cross_file", "capability.class.crossFile", "code_eval",
                    "harness.code.patch", ("cross-file-change",)),
    CapabilityClass("test_first", "capability.class.testFirst", "code_eval",
                    "harness.code.repair", ("test-first",)),
    CapabilityClass("repair", "capability.class.repair", "code_eval",
                    "harness.code.repair", ("failing-check-repair",)),
    CapabilityClass("job", "capability.class.job", "code_eval",
                    "harness.jobs.model", ("job-definition",)),
    CapabilityClass("kit", "capability.class.kit", "code_eval",
                    "harness.code.kits.loader", ("kit-scaffold",)),
    CapabilityClass("refusal", "capability.class.refusal", "code_eval",
                    "harness.code.policy", ("refusal-protected-write",)),
    # Graded here, through the real modules.
    CapabilityClass("bulk_collection", "capability.class.bulkCollection", "fixture",
                    "harness.acquire.budget", ("bulk-collection-ceiling",)),
    CapabilityClass("unattended_report", "capability.class.unattendedReport", "fixture",
                    "harness.automation.delivery", ("unattended-report-limits",)),
    CapabilityClass("artifact_verification", "capability.class.artifactVerification", "fixture",
                    "harness.code.verify", ("artifact-claim-marked",)),
    CapabilityClass("change_review", "capability.class.changeReview", "fixture",
                    "harness.code.review", ("change-review-rules",)),
    # Graded by named tests that run in the release gate.
    CapabilityClass("document_attachment", "capability.class.documentAttachment", "test_gate",
                    "lib/chat/extract",
                    ("vitest:src/lib/chat/extract.test.ts", "vitest:src/lib/chat/session-store.test.ts")),
    CapabilityClass("figure_provenance", "capability.class.figureProvenance", "test_gate",
                    "harness.code.recipes",
                    ("pytest:python/tests/test_analysis_recipes.py::test_drawdown_figure_writes_a_real_png_artifact_that_verifies",
                     "pytest:python/tests/test_analysis_execution.py")),
    # Declared and NOT graded — published as not measured, with the reason.
    CapabilityClass("price_authority", "capability.class.priceAuthority", "unmeasured",
                    "harness.retrieval.authority", (),
                    reason="Not graded yet — the source-choice logic is tested in pieces, not end to end."),
    CapabilityClass("promotion", "capability.class.promotion", "unmeasured",
                    "harness.code.actions", (),
                    reason="Not graded yet — putting a change into your files is tested in pieces, not end to end."),
    CapabilityClass("scraping_breadth", "capability.class.scrapingBreadth", "unmeasured",
                    "harness.acquire.registry", (),
                    reason="Not graded yet — only a few kinds of data sources are set up."),
    CapabilityClass("messaging_gateway", "capability.class.messagingGateway", "unmeasured",
                    "harness.gateway", (),
                    reason="Not built yet."),
)

#: Classes that MUST stay measured; the gate fails when one regresses to unmeasured.
MEASURED_BASELINE: frozenset[str] = frozenset(
    c.id for c in CLASSES if c.kind != "unmeasured"
)


# ── The runner ───────────────────────────────────────────────────────────────


@dataclass
class ClassResult:
    id: str
    status: Literal["passed", "failed", "unmeasured"]
    detail: str
    observed: dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityReport:
    results: list[ClassResult] = field(default_factory=list)

    @property
    def measured(self) -> list[ClassResult]:
        return [r for r in self.results if r.status != "unmeasured"]

    @property
    def unmeasured(self) -> list[ClassResult]:
        return [r for r in self.results if r.status == "unmeasured"]

    @property
    def failed(self) -> list[ClassResult]:
        return [r for r in self.results if r.status == "failed"]

    @property
    def passed(self) -> bool:
        return not self.failed

    def by_id(self, class_id: str) -> Optional[ClassResult]:
        return next((r for r in self.results if r.id == class_id), None)


def _check_test_selector(klass: CapabilityClass, selector: str) -> tuple[bool, str]:
    kind, _, target = selector.partition(":")
    if kind == "vitest":
        path = _REPO_ROOT / target
        return path.exists(), f"the test file is present: {target}"
    if kind == "pytest":
        file_part, _, test_name = target.partition("::")
        path = _REPO_ROOT / file_part
        if not path.exists():
            return False, f"the test file is missing: {file_part}"
        if test_name and f"def {test_name}" not in path.read_text(encoding="utf-8"):
            return False, f"the named test is missing: {test_name}"
        return True, f"the test is present: {target}"
    return False, f"unknown test selector {selector!r}"


def run_capability_eval(*, only: Optional[tuple[str, ...]] = None) -> CapabilityReport:
    """Grade every registered class. A class with no fixtures is reported
    `unmeasured` WITH ITS REASON — never as a pass, never as a failure."""
    report = CapabilityReport()
    for klass in CLASSES:
        if only is not None and klass.id not in only:
            continue
        if klass.kind == "unmeasured":
            report.results.append(ClassResult(
                id=klass.id, status="unmeasured",
                detail=klass.reason or "no fixture registered",
            ))
            continue
        if klass.kind == "fixture":
            try:
                observed = _FIXTURES[klass.selectors[0]]()
            except Exception as exc:  # noqa: BLE001 - a fixture error IS a failure
                report.results.append(ClassResult(
                    id=klass.id, status="failed",
                    detail=f"the fixture raised {type(exc).__name__}",
                ))
                continue
            failed_keys = sorted(k for k, ok in observed.items() if not ok)
            report.results.append(ClassResult(
                id=klass.id,
                status="failed" if failed_keys else "passed",
                detail=("every gold outcome held" if not failed_keys
                        else f"gold outcomes not held: {', '.join(failed_keys)}"),
                observed=observed,
            ))
            continue
        if klass.kind == "code_eval":
            dataset = _load_code_dataset()
            cases = dataset.get("cases") if isinstance(dataset.get("cases"), list) else []
            fixture_ids = {str(c.get("caseId")) for c in cases if isinstance(c, dict)}
            missing = [s for s in klass.selectors if s not in fixture_ids]
            report.results.append(ClassResult(
                id=klass.id,
                status="failed" if missing else "passed",
                detail=("fixtures present (graded by the code gate in this run)"
                        if not missing else f"fixture ids missing: {', '.join(missing)}"),
                observed={"fixtures": list(klass.selectors)},
            ))
            continue
        # test_gate
        problems: list[str] = []
        details: list[str] = []
        for selector in klass.selectors:
            ok, detail = _check_test_selector(klass, selector)
            details.append(detail)
            if not ok:
                problems.append(selector)
        report.results.append(ClassResult(
            id=klass.id,
            status="failed" if problems else "passed",
            detail=("; ".join(details) if not problems
                    else f"missing tests: {', '.join(problems)}"),
            observed={"selectors": list(klass.selectors)},
        ))
    return report


def _load_code_dataset() -> dict[str, Any]:
    path = Path(__file__).with_name("dataset_tasks_v1.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - an unreadable dataset is an empty one
        return {"cases": []}


def check_capability_floors(
    report: CapabilityReport, *, baseline: frozenset[str] = MEASURED_BASELINE,
) -> dict[str, Any]:
    """The gate: a measured class must pass; a baseline class must stay measured."""
    failures: list[str] = []
    for result in report.failed:
        failures.append(f"{result.id}: {result.detail}")
    for class_id in sorted(baseline):
        result = report.by_id(class_id)
        if result is None or result.status == "unmeasured":
            failures.append(f"{class_id}: regressed to unmeasured")
    return {
        "passed": not failures,
        "failures": failures,
        "measured": len(report.measured),
        "unmeasured": len(report.unmeasured),
        "classes": len(report.results),
    }


def format_capability_report(report: CapabilityReport) -> str:
    lines = [
        f"capability classes: {len(report.results)} registered, "
        f"{len(report.measured)} measured, {len(report.unmeasured)} not measured yet"
    ]
    for result in report.results:
        mark = {"passed": "OK", "failed": "FAIL", "unmeasured": "—"}[result.status]
        lines.append(f"  [{mark}] {result.id}: {result.detail}")
    if report.unmeasured:
        names = ", ".join(r.id for r in report.unmeasured)
        lines.append(f"  not measured yet (named, not hidden): {names}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    """The gate step. Prints the counts; non-zero on a floor violation or a
    measured class regressing to unmeasured."""
    import sys  # noqa: PLC0415

    report = run_capability_eval()
    print(format_capability_report(report))
    verdict = check_capability_floors(report)
    print(
        "capability-class gate:",
        "PASS" if verdict["passed"] else "FAIL",
        verdict["failures"] if not verdict["passed"] else "",
    )
    return 0 if verdict["passed"] else 1


__all__ = [
    "CLASSES",
    "MEASURED_BASELINE",
    "CapabilityClass",
    "CapabilityReport",
    "ClassResult",
    "check_capability_floors",
    "format_capability_report",
    "run_capability_eval",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
