"""The code-verification evaluation — a small, labelled, versioned set.

The measurement seam for Phase 4's trust spine. It is deliberately separate from
the verification implementation so a change to claim parsing or support logic can
be judged against recorded results (including the negative cases: an honest "I did
not run the tests" must not be flagged).

Design:
  * `dataset_v1.json` is a human-labelled set of (answer, ledger records) →
    expected (claim kind, supported) pairs.
  * `run_evaluation()` builds a ledger from each case's records through the REAL
    `VerificationLedger`, parses the answer with the REAL claim parser, and
    reports the deterministic metrics.
  * No model call anywhere; the check is pure.

Thresholds (a deterministic floor, not a blended score):
  * `falseVerifiedRate == 0.0` — an unbacked claim marked verified is a hard fail.
  * `claimRecall >= 0.95` — the parser must find the claims it is meant to.
  * `digestStability == 1.0` — the digest normalizes CRLF/trailing whitespace.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from ..policy import COMMAND_CLASSES
from ..verify import VerificationLedger, output_digest

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset_v1.json")

THRESHOLDS = {
    "falseVerifiedRate": 0.0,
    "claimRecall": 0.95,
    "digestStability": 1.0,
}


@dataclass
class EvalMetrics:
    version: str
    cases: int = 0
    expectedClaims: int = 0  # noqa: N815
    foundClaims: int = 0  # noqa: N815
    falseVerified: int = 0  # noqa: N815
    perCase: list[dict[str, Any]] = field(default_factory=list)  # noqa: N815

    @property
    def claimRecall(self) -> float:  # noqa: N815
        if self.expectedClaims == 0:
            return 1.0
        return self.foundClaims / self.expectedClaims

    @property
    def falseVerifiedRate(self) -> float:  # noqa: N815
        if self.expectedClaims == 0:
            return 0.0
        return self.falseVerified / self.expectedClaims


def _load_dataset() -> dict[str, Any]:
    with open(DATASET_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _ledger_for(run_id: str, records: list[dict[str, Any]]) -> VerificationLedger:
    ledger = VerificationLedger(run_id)
    for i, record in enumerate(records or []):
        command_class = str(record.get("commandClass") or "")
        if command_class not in COMMAND_CLASSES:
            continue
        ledger.record(
            command_execution_id=f"cmd_{run_id}_{i}", command_class=command_class,
            exit_code=int(record.get("exitCode") or 0), duration_ms=1,
            output=str(record.get("output") or ""),
        )
    return ledger


def _digest_stability() -> float:
    """The digest must normalize CRLF/trailing whitespace and change on a line."""
    a = output_digest("line1\nline2\n")
    b = output_digest("line1  \r\nline2\r\n\r\n")
    c = output_digest("line1\nline3\n")
    checks = [a == b, a != c]
    return 1.0 if all(checks) else 0.0


def run_evaluation() -> EvalMetrics:
    dataset = _load_dataset()
    metrics = EvalMetrics(version=str(dataset.get("version") or "unknown"))
    for i, case in enumerate(dataset.get("cases") or []):
        run_id = f"case_{i}"
        ledger = _ledger_for(run_id, case.get("records") or [])
        answer = str(case.get("answer") or "")
        actual = ledger.unverified_claims(answer)  # unsupported claims
        claims = ledger.claims(answer)
        # Support status per claim kind.
        supported_kinds = {c.kind for c in claims} - {c.kind for c in actual}
        unsupported_kinds = {c.kind for c in actual}

        expected = case.get("expectedClaims") or []
        expected_n = len(expected)
        found = 0
        false_verified = 0
        for exp in expected:
            kind = exp.get("kind")
            want_supported = bool(exp.get("supported"))
            if kind in supported_kinds or kind in unsupported_kinds:
                found += 1
            got_supported = kind in supported_kinds
            if want_supported and not got_supported and kind not in unsupported_kinds:
                pass  # not found at all — recall penalty, not a false-verify
            if got_supported and not want_supported:
                false_verified += 1
        metrics.cases += 1
        metrics.expectedClaims += expected_n
        metrics.foundClaims += found
        metrics.falseVerified += false_verified
        metrics.perCase.append({
            "id": case.get("id"), "found": found, "expected": expected_n,
            "falseVerified": false_verified,
        })
    return metrics


def check_thresholds(metrics: EvalMetrics) -> dict[str, Any]:
    """Return the failing dimension by name, or a pass."""
    failures: list[str] = []
    if metrics.falseVerifiedRate > THRESHOLDS["falseVerifiedRate"]:
        failures.append(
            f"falseVerifiedRate={metrics.falseVerifiedRate:.3f} > {THRESHOLDS['falseVerifiedRate']}"
        )
    if metrics.claimRecall < THRESHOLDS["claimRecall"]:
        failures.append(
            f"claimRecall={metrics.claimRecall:.3f} < {THRESHOLDS['claimRecall']}"
        )
    stability = _digest_stability()
    if stability < THRESHOLDS["digestStability"]:
        failures.append(f"digestStability={stability:.3f} < {THRESHOLDS['digestStability']}")
    return {"passed": not failures, "failures": failures, "digestStability": stability}


def format_report(metrics: EvalMetrics) -> str:
    lines = [
        f"Code verification eval — {metrics.version}",
        f"  cases={metrics.cases} expectedClaims={metrics.expectedClaims} "
        f"foundClaims={metrics.foundClaims} falseVerified={metrics.falseVerified}",
        f"  claimRecall={metrics.claimRecall:.3f} "
        f"falseVerifiedRate={metrics.falseVerifiedRate:.3f}",
        "  per-kind slices:",
    ]
    for row in metrics.perCase:
        lines.append(
            f"    [{row['id']}] found={row['found']}/{row['expected']} "
            f"falseVerified={row['falseVerified']}"
        )
    return "\n".join(lines)


def _kit_acceptance_test_exists(kit_id: str) -> bool:
    """Whether a Phase-9 kit's acceptance test ships with it (used by tasks.py)."""
    from ..kits.loader import _acceptance_test_exists  # noqa: PLC0415

    return _acceptance_test_exists(kit_id)


# ── Phase 12: the task + safety evaluation (a different subject) ─────────────
# The verification eval above grades the ledger. This half grades the SEVEN task
# shapes and the ELEVEN adversarial safety cases, and is what the release gate's
# code-eval step reports. Both live in this package because both are "the code
# eval"; they are exported under distinct names so neither shadows the other.
from .safety import run_safety_evaluation  # noqa: E402
from .tasks import (  # noqa: E402
    REVIEWED_TASKS_CHECKSUM,
    TaskMetrics,
    capability_rows,
    check_task_thresholds,
    format_task_report,
    load_task_dataset,
    run_task_evaluation,
    tasks_checksum,
)

# The combined per-category report the release gate prints: tasks, then safety.
# NEVER a single blended score — each block names its own slices.
def run_code_evaluation() -> dict[str, Any]:
    """Run the task fixtures AND the adversarial safety cases. Returns both halves."""
    task_metrics = run_task_evaluation()
    safety = run_safety_evaluation()
    return {"tasks": task_metrics, "safety": safety}


def check_code_thresholds(result: dict[str, Any]) -> dict[str, Any]:
    """Fail-by-name over tasks + safety. Never a composite pass/fail score."""
    failures: list[str] = []
    task_gate = check_task_thresholds(
        result["tasks"], reviewed_checksum=REVIEWED_TASKS_CHECKSUM
    )
    if not task_gate["passed"]:
        failures.extend(task_gate["failures"])
    blocked = [c for c in result["safety"] if not c.passed]
    if blocked:
        failures.extend(f"safety:{c.caseId}" for c in blocked)
    return {
        "passed": not failures,
        "failures": failures,
        "taskChecksum": task_gate.get("checksum"),
    }


def format_code_report(result: dict[str, Any]) -> str:
    """The combined report: per-shape tasks, then per-attack safety."""
    lines = [format_task_report(result["tasks"])]
    lines.append("")
    lines.append("Adversarial safety cases (blocked AND recorded):")
    for c in result["safety"]:
        mark = "PASS" if c.passed else "FAIL"
        lines.append(f"  [{c.caseId}] {mark} code={c.code} ({c.detail})")
    return "\n".join(lines)


__all__ = [
    # Phase 4: the verification eval (kept by name — the release gate uses it).
    "EvalMetrics",
    "THRESHOLDS",
    "check_thresholds",
    "format_report",
    "run_evaluation",
    # Phase 12: the task + safety eval.
    "TaskMetrics",
    "capability_rows",
    "check_code_thresholds",
    "check_task_thresholds",
    "format_code_report",
    "format_task_report",
    "load_task_dataset",
    "run_code_evaluation",
    "run_safety_evaluation",
    "run_task_evaluation",
    "tasks_checksum",
]
