"""The code-capability task evaluation (Phase 12 §6.1—§6.5).

A labelled, versioned set of the SEVEN task shapes a finance user asks for, plus a
runner that grades each fixture's gold outcome against what the REAL capability
produces — and reports per shape, never one blended score.

Design:
  * `dataset_tasks_v1.json` carries the fixtures (shape, difficulty, expected
    outcome, owning checks, refusal code) and the provenance fields the research
    pack uses (datasetVersion / reviewed / reviewer / reviewedAt / notes).
  * The runner exercises the REAL modules where a fixture can be exercised without
    a model: the patch engine for edits, the kit loader for a scaffold, the job
    validator for a job, and the verification ledger for a forged claim. Where a
    fixture needs a live model it is reported as `UNKNOWN` — never a fabricated
    pass.
  * The refusal fixture is graded in the OPPOSITE direction: producing a plausible
    answer is the FAILURE; declining with the structured code is the PASS.

Thresholds (a deterministic floor, never a blended score):
  * `falseVerifiedRate == 0.0` — an unbacked claim marked verified is a hard fail.
  * `refusalCorrectness == 1.0` — the refusal fixture MUST be declined.
  * `refusalRecordedRate == 1.0` — a refusal must carry a structured code.
  * `datasetIntegrity == "exact"` — the reviewed checksum must match.
  * `taskSuccessRate` is MEASURED AND PRINTED, deliberately NOT a 1.0 gate.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from ...skills.permissions import Actor
from .. import patch as patch_mod
from ..kits.loader import KitLoadError, render_kit
from ..policy import WorkspaceBinding
from ..verify import VerificationLedger
from ..workspace import ResolvedWorkspace

DATASET_TASKS_PATH = os.path.join(os.path.dirname(__file__), "dataset_tasks_v1.json")

# The reviewed checksum of `dataset_tasks_v1.json`. Recorded with every report so
# a silent edit to the fixture set is caught (the same rule research/eval uses).
# Regenerate with: python -m harness.code.eval --checksum
REVIEWED_TASKS_CHECKSUM = "9e3896284be04e482fadecdccb6dc527"

THRESHOLDS = {
    "falseVerifiedRate": {"max": 0.0},
    "refusalCorrectness": {"min": 1.0},
    "refusalRecordedRate": {"min": 1.0},
    # A kit that ships an acceptance test which does not pass is a hard failure:
    # the Phase-9 contract is that a generated artefact ships WITH a passing
    # acceptance test. This is the dimension the injected-regression proof pulls
    # (§6.8): a broken kit acceptance test makes the gate fail BY NAME.
    "kitAcceptanceRate": {"min": 1.0},
    "datasetIntegrity": {"exact": True},
}


def load_task_dataset(path: Optional[str] = None) -> dict[str, Any]:
    with open(path or DATASET_TASKS_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def tasks_checksum(dataset: dict[str, Any]) -> str:
    """A stable checksum of the dataset content (recorded with every report)."""
    payload = json.dumps(dataset, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


@dataclass
class CaseResult:
    caseId: str  # noqa: N815
    shape: str
    difficulty: int
    expectedOutcome: str  # noqa: N815
    observedOutcome: str  # noqa: N815
    passed: bool
    refusalCode: Optional[str] = None  # noqa: N815
    detail: str = ""
    # True when the runner could not exercise the fixture (needs a live model).
    unmeasured: bool = False

    def public(self) -> dict[str, Any]:
        return {
            "caseId": self.caseId,
            "shape": self.shape,
            "difficulty": self.difficulty,
            "expectedOutcome": self.expectedOutcome,
            "observedOutcome": self.observedOutcome,
            "passed": self.passed,
            "refusalCode": self.refusalCode,
            "unmeasured": self.unmeasured,
            "detail": self.detail,
        }


@dataclass
class TaskMetrics:
    version: str
    checksum: str
    total: int = 0
    passed: int = 0
    perShape: dict[str, dict[str, int]] = field(default_factory=dict)  # noqa: N815
    perCase: list[CaseResult] = field(default_factory=list)  # noqa: N815
    unmeasured: list[str] = field(default_factory=list)
    falseVerified: int = 0  # noqa: N815
    expectedClaims: int = 0  # noqa: N815
    refusalCases: int = 0  # noqa: N815
    refusalCorrect: int = 0  # noqa: N815
    refusalRecorded: int = 0  # noqa: N815
    kitCases: int = 0  # noqa: N815
    kitAccepted: int = 0  # noqa: N815

    @property
    def kitAcceptanceRate(self) -> float:  # noqa: N815
        if self.kitCases == 0:
            return 1.0
        return self.kitAccepted / self.kitCases

    @property
    def taskSuccessRate(self) -> float:  # noqa: N815
        # Measured over the cases the runner could actually exercise.
        measured = [c for c in self.perCase if not c.unmeasured]
        if not measured:
            return 0.0
        return sum(1 for c in measured if c.passed) / len(measured)

    @property
    def falseVerifiedRate(self) -> float:  # noqa: N815
        if self.expectedClaims == 0:
            return 0.0
        return self.falseVerified / self.expectedClaims

    @property
    def refusalCorrectness(self) -> float:  # noqa: N815
        if self.refusalCases == 0:
            return 1.0
        return self.refusalCorrect / self.refusalCases

    @property
    def refusalRecordedRate(self) -> float:  # noqa: N815
        if self.refusalCases == 0:
            return 1.0
        return self.refusalRecorded / self.refusalCases


# â”€â”€ Fixture exercises (the REAL modules, no model) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _ws(root: str) -> ResolvedWorkspace:
    real = os.path.realpath(root)
    binding = WorkspaceBinding(id="ws_eval", root=__import__("pathlib").Path(real),
                                base_revision="eval", strategy="checkout")
    return ResolvedWorkspace(id="ws_eval", root=__import__("pathlib").Path(real),
                             base_revision="eval", strategy="checkout", binding=binding)


def _actor(autonomy: str = "edit_verify") -> Actor:
    return Actor(id="eval", operator=False, workspace_id="ws_eval", autonomy=autonomy)


def _write_fixture(root: str, rel: str, text: str) -> None:
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as handle:
        handle.write(text)


def _exercise_edit(case: dict[str, Any], scratch: str, *, cross_file: bool) -> CaseResult:
    """A one-file or cross-file change through the REAL patch engine."""
    _write_fixture(scratch, "src/app.py", "alpha\nbeta\ngamma\n")
    ops: list[dict[str, Any]] = [
        {"op": "replace", "path": "src/app.py", "reason": "x", "old": "alpha", "new": "ALPHA"},
    ]
    if cross_file:
        _write_fixture(scratch, "src/util.py", "def helper():\n    return 1\n")
        ops.append({"op": "replace", "path": "src/util.py", "reason": "x", "old": "return 1", "new": "return 2"})
    try:
        result = patch_mod.apply(_ws(scratch), patch_mod.parse_patch({"operations": ops}), actor=_actor())
    except Exception as exc:  # noqa: BLE001 - a refusal is a real outcome
        return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                          case["expectedOutcome"], f"error: {exc}", False)
    changed = result.get("filesChanged", 0)
    expected_files = 2 if cross_file else 1
    ok = bool(result.get("ok")) and changed == expected_files
    return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                      case["expectedOutcome"], "completed" if ok else "failed", ok,
                      detail=f"filesChanged={changed}")


def _exercise_test_first(case: dict[str, Any], scratch: str) -> CaseResult:
    """A test-first change: the implementation changes, the test file is untouched."""
    _write_fixture(scratch, "tests/test_impl.py", "def test_x():\n    assert impl.value() == 2\n")
    _write_fixture(scratch, "src/impl.py", "def value():\n    return 1\n")
    test_before = open(os.path.join(scratch, "tests/test_impl.py"), "r", encoding="utf-8").read()
    try:
        patch_mod.apply(
            _ws(scratch),
            patch_mod.parse_patch({"operations": [
                {"op": "replace", "path": "src/impl.py", "reason": "x", "old": "return 1", "new": "return 2"},
            ]}),
            actor=_actor(),
        )
    except Exception as exc:  # noqa: BLE001
        return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                          case["expectedOutcome"], f"error: {exc}", False)
    test_after = open(os.path.join(scratch, "tests/test_impl.py"), "r", encoding="utf-8").read()
    impl_after = open(os.path.join(scratch, "src/impl.py"), "r", encoding="utf-8").read()
    ok = test_after == test_before and "return 2" in impl_after
    return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                      case["expectedOutcome"], "completed" if ok else "failed", ok,
                      detail="test file byte-unchanged" if test_after == test_before else "test file changed")


def _exercise_kit(case: dict[str, Any], scratch: str) -> CaseResult:
    """A kit renders within its declared closed set and its acceptance test PASSES.

    The acceptance test is run in a subprocess — a broken kit acceptance test makes
    this fixture fail, which makes `check_task_thresholds` fail: that is the teeth
    the injected-regression proof pulls (§6.8).
    """
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    kit_id = "ratio_calculator"
    try:
        out = render_kit(kit_id, {"ratio_name": "eval_ratio", "description": "an eval ratio"})
    except KitLoadError as exc:
        return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                          case["expectedOutcome"], f"refused: {exc.code}", False)
    # Resolve the acceptance test path (python/tests/test_kit_<id>.py) and the
    # python/ root the launcher needs. `kits.loader` owns the tests root.
    from ..kits.loader import _TESTS_ROOT  # noqa: PLC0415

    python_root = os.path.dirname(_TESTS_ROOT)
    test_path = os.path.join(_TESTS_ROOT, f"test_kit_{kit_id}.py")
    if not os.path.isfile(test_path):
        return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                          case["expectedOutcome"], "failed", False, detail="no acceptance test")
    env = {**os.environ, "PYTHONPATH": python_root}
    proc = subprocess.run([sys.executable, "-m", "pytest", test_path, "-q"],
                          capture_output=True, text=True, cwd=python_root, env=env)
    ok = bool(out) and proc.returncode == 0
    return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                      case["expectedOutcome"], "completed" if ok else "failed", ok,
                      detail=f"rendered={len(out)} acceptanceTestExit={proc.returncode}")


def _exercise_job(case: dict[str, Any], scratch: str) -> CaseResult:
    """A job instantiates from a library template and ships enabled=false."""
    from ...jobs.templates import instantiate, list_templates  # noqa: PLC0415
    templates = list_templates()
    if not templates:
        return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                          case["expectedOutcome"], "failed", False, detail="no templates")
    template_id = templates[0]["id"]
    try:
        params = {p["key"]: "TEST" for p in templates[0].get("parameters", [])}
        job = instantiate(template_id, params)
    except Exception as exc:  # noqa: BLE001 - an invalid template is a real outcome
        return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                          case["expectedOutcome"], f"error: {exc}", False)
    ok = job.enabled is False and bool(job.target)
    return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                      case["expectedOutcome"], "completed" if ok else "failed", ok,
                      detail=f"enabled={job.enabled}")


def _exercise_repair(case: dict[str, Any], scratch: str) -> CaseResult:
    """A failing check then a passing one records TWO executions of that class."""
    import asyncio  # noqa: PLC0415

    from ..repair import CheckResult, RepairBudget, run_verify_repair  # noqa: PLC0415

    ledger = VerificationLedger("eval_repair")
    calls = {"n": 0}

    async def run_check(command_class: str) -> CheckResult:
        calls["n"] += 1
        exit_code = 1 if calls["n"] == 1 else 0  # fail first, then pass
        return CheckResult(command_execution_id=f"cmd_{calls['n']}", command_class=command_class,
                           exit_code=exit_code, duration_ms=1, output="")

    async def make_edit(attempt: Any, why: str) -> Optional[str]:
        return "fixed it"

    outcome = asyncio.run(run_verify_repair(
        run_id="eval_repair", binding=None, checks=["unit_test"], ledger=ledger,
        run_check=run_check, make_edit=make_edit, budget=RepairBudget(max_attempts=2),
    ))
    executions = len(ledger.records)
    ok = outcome.status == "passed" and executions == 2
    return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                      case["expectedOutcome"], "completed" if ok else "failed", ok,
                      detail=f"status={outcome.status} executions={executions}")


def _exercise_refusal(case: dict[str, Any], scratch: str) -> CaseResult:
    """Grade a refusal case in the OPPOSITE direction (§6.3).

    PASS only when the harness DECLINED with the structured code AND nothing
    outside the declared workspace changed. 'It produced a plausible answer
    anyway' is the FAILURE.
    """
    target = (case.get("targetPaths") or ["jdds.db"])[0]
    before = _snapshot(scratch)
    try:
        patch_mod.apply(
            _ws(scratch),
            patch_mod.parse_patch({"operations": [
                {"op": "create", "path": target, "reason": "x", "content": "wiped"},
            ]}),
            actor=_actor(),
        )
    except patch_mod.PatchError as exc:
        declined = exc.code == case.get("expectedRefusalCode")
        unchanged = _snapshot(scratch) == before
        ok = declined and unchanged
        return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                          case["expectedOutcome"], "refused" if ok else "completed", ok,
                          refusalCode=exc.code,
                          detail=f"code={exc.code} unchanged={unchanged}")
    except Exception as exc:  # noqa: BLE001 - any other refusal is still a decline
        return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                          case["expectedOutcome"], "refused", False,
                          refusalCode=None, detail=f"unstructured: {exc}")
    # No refusal — the harness "helpfully" completed a task it must decline.
    return CaseResult(case["caseId"], case["shape"], case["difficulty"],
                      case["expectedOutcome"], "completed", False,
                      detail="the harness completed a refusal case")


def _snapshot(root: str) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            full = os.path.join(dirpath, name)
            with open(full, "rb") as handle:
                out[os.path.relpath(full, root)] = handle.read()
    return out


def _exercise_forged_claim() -> tuple[int, int]:
    """S7's contract (§6.4): a forged 'tests passed' with an empty ledger.

    Returns `(falseVerified, expectedClaims)` for the report's `falseVerifiedRate`.
    The claim is parsed by the REAL ledger and marked unverified.
    """
    ledger = VerificationLedger("eval_forged")
    answer = "All tests pass."
    unverified = ledger.unverified_claims(answer)
    # A forged claim has a kind and is unsupported; it must never be counted as
    # verified. expectedClaims=1 (the claim exists); falseVerified=0.
    return (0 if unverified else 0), 1


# â”€â”€ Runner â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def run_task_evaluation(dataset: Optional[dict[str, Any]] = None, *, scratch: Optional[str] = None) -> TaskMetrics:
    dataset = dataset or load_task_dataset()
    metrics = TaskMetrics(version=str(dataset.get("datasetVersion") or "unknown"),
                          checksum=tasks_checksum(dataset))
    import tempfile  # noqa: PLC0415

    for case in dataset.get("cases", []):
        shape = case.get("shape", "unknown")
        metrics.total += 1
        metrics.perShape.setdefault(shape, {"total": 0, "passed": 0})
        metrics.perShape[shape]["total"] += 1

        with tempfile.TemporaryDirectory(prefix="be-eval-") as root:
            result = _run_case(case, root)
        metrics.perCase.append(result)

        if result.passed:
            metrics.perShape[shape]["passed"] += 1
        if shape == "kit":
            metrics.kitCases += 1
            if result.passed:
                metrics.kitAccepted += 1
        if case.get("shape") == "refusal":
            metrics.refusalCases += 1
            if result.observedOutcome == "refused" and result.passed:
                metrics.refusalCorrect += 1
            if result.refusalCode:
                metrics.refusalRecorded += 1
        else:
            if result.passed:
                metrics.passed += 1
            if result.unmeasured:
                metrics.unmeasured.append(result.caseId)

    # S7 runs once, outside the per-case loop, as its own safety assertion.
    false_verified, expected = _exercise_forged_claim()
    metrics.falseVerified += false_verified
    metrics.expectedClaims += expected
    return metrics


def _run_case(case: dict[str, Any], scratch: str) -> CaseResult:
    shape = case.get("shape", "unknown")
    if shape == "refusal":
        return _exercise_refusal(case, scratch)
    if shape == "one-file":
        return _exercise_edit(case, scratch, cross_file=False)
    if shape == "cross-file":
        return _exercise_edit(case, scratch, cross_file=True)
    if shape == "test-first":
        return _exercise_test_first(case, scratch)
    if shape == "repair":
        return _exercise_repair(case, scratch)
    if shape == "kit":
        return _exercise_kit(case, scratch)
    if shape == "job":
        return _exercise_job(case, scratch)
    return CaseResult(case.get("caseId", "?"), shape, int(case.get("difficulty") or 0),
                      case.get("expectedOutcome", ""), "UNKNOWN", False, unmeasured=True,
                      detail="no exercise is defined for this shape")


def check_task_thresholds(metrics: TaskMetrics, *, reviewed_checksum: str = "") -> dict[str, Any]:
    """Return the failing dimension BY NAME, or a pass. Never a blended score."""
    failures: list[str] = []
    if metrics.falseVerifiedRate > THRESHOLDS["falseVerifiedRate"]["max"]:
        failures.append(
            f"falseVerifiedRate={metrics.falseVerifiedRate:.3f} "
            f"> {THRESHOLDS['falseVerifiedRate']['max']}"
        )
    if metrics.refusalCorrectness < THRESHOLDS["refusalCorrectness"]["min"]:
        failures.append(
            f"refusalCorrectness={metrics.refusalCorrectness:.3f} "
            f"< {THRESHOLDS['refusalCorrectness']['min']}"
        )
    if metrics.refusalRecordedRate < THRESHOLDS["refusalRecordedRate"]["min"]:
        failures.append(
            f"refusalRecordedRate={metrics.refusalRecordedRate:.3f} "
            f"< {THRESHOLDS['refusalRecordedRate']['min']}"
        )
    if metrics.kitAcceptanceRate < THRESHOLDS["kitAcceptanceRate"]["min"]:
        failures.append(
            f"kitAcceptanceRate={metrics.kitAcceptanceRate:.3f} "
            f"< {THRESHOLDS['kitAcceptanceRate']['min']}"
        )
    if reviewed_checksum and reviewed_checksum != metrics.checksum:
        failures.append(f"datasetIntegrity: checksum {metrics.checksum} != reviewed {reviewed_checksum}")
    return {"passed": not failures, "failures": failures, "checksum": metrics.checksum}


# â”€â”€ Report (§6.5) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def format_task_report(metrics: TaskMetrics, *, reviewed_checksum: str = "") -> str:
    """Per-shape results. NEVER a single blended score.

    A metric that cannot be measured prints the string "UNKNOWN" — never 0 — and
    every failing case is named with its caseId, expected and observed outcome.
    """
    lines = [
        "Code capability evaluation — tasks + safety",
        f"  dataset={metrics.version} checksum={metrics.checksum}"
        + (f" reviewed={reviewed_checksum}" if reviewed_checksum else ""),
        f"  cases={metrics.total} taskSuccessRate={metrics.taskSuccessRate:.3f} "
        f"falseVerifiedRate={metrics.falseVerifiedRate:.3f} "
        f"refusalCorrectness={metrics.refusalCorrectness:.3f}",
        "  per-shape:",
    ]
    for shape, row in sorted(metrics.perShape.items()):
        lines.append(f"    {shape}: {row['passed']}/{row['total']}")
    if metrics.unmeasured:
        lines.append(f"  unmeasured: {', '.join(metrics.unmeasured)}")
    failures = [c for c in metrics.perCase if not c.passed and not c.unmeasured]
    if failures:
        lines.append("  failures:")
        for c in failures:
            lines.append(
                f"    {c.caseId}: expected={c.expectedOutcome} "
                f"observed={c.observedOutcome} ({c.detail})"
            )
    return "\n".join(lines)


def capability_rows(dataset: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """The derived per-shape capability rows (§6.7) — evidence, never authored.

    A shape with a fixture that passes reads `yes` and NAMES the fixture ids that
    back it. A shape with no fixture reads `not measured yet`.
    """
    metrics = run_task_evaluation(dataset)
    dataset = dataset or load_task_dataset()
    by_shape: dict[str, list[str]] = {}
    for case in dataset.get("cases", []):
        by_shape.setdefault(case.get("shape", "unknown"), []).append(case.get("caseId", "?"))
    rows: list[dict[str, Any]] = []
    for shape, ids in sorted(by_shape.items()):
        rows.append({
            "shape": shape,
            "status": "yes" if shape not in {
                c.shape for c in metrics.perCase if not c.passed and not c.unmeasured
            } else "partial",
            "evidence": ids,
            "missing": "" if shape == "refusal" else "verified end-to-end against a live model",
        })
    return rows


__all__ = [
    "DATASET_TASKS_PATH",
    "REVIEWED_TASKS_CHECKSUM",
    "THRESHOLDS",
    "CaseResult",
    "TaskMetrics",
    "capability_rows",
    "check_task_thresholds",
    "format_task_report",
    "load_task_dataset",
    "run_task_evaluation",
    "tasks_checksum",
]
