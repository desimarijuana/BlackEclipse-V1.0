"""Contradiction-detection evaluation — a small, versioned, labeled set.

This is the measurement seam for the conflict detector. `contradictions_v1.json`
is a human-labeled set of (existing memory, new statement, authority) tuples with
the SAFE expected disposition. `run_contradiction_evaluation()` runs the REAL
`eclipse_memory.conflicts.detect_conflict` for each case (and, when enabled, the
optional semantic candidate layer) and reports:

  * contradiction recall (conflicts the detector caught);
  * false-conflict rate (unrelated memory it wrongly tried to change);
  * confirmation accuracy (same-meaning restatements recognised);
  * unrelated-memory safety;
  * scope isolation;
  * authority correctness.

Report-only by default; `check_contradiction_thresholds` is the release gate.
Nothing here is production code — it imports the detector and never touches the
developer's database (pure functions, no store).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from ..conflicts import DECISION_SUPERSEDE, detect_conflict

CONTRADICTION_DATASET_PATH = os.path.join(os.path.dirname(__file__), "contradictions_v1.json")

# Kinds where a conflict (supersede/propose) is the SAFE expectation.
_CONFLICT_KINDS = frozenset(
    {"direct-polarity", "paraphrase-conflict", "ambiguous", "authority"}
)
# Kinds where NO action (none) is the SAFE expectation.
_NO_CONFLICT_KINDS = frozenset(
    {"unrelated", "different-subject", "different-scope", "temporary", "observation-vs-preference"}
)

# Release thresholds for the contradiction gate. Safety is absolute: semantic
# handling must never introduce a false conflict, a scope leak, or an
# unauthorized/automatic-over-explicit supersede. Recall/confirmation are floors.
CONTRADICTION_THRESHOLDS: dict[str, Any] = {
    "falseConflictRate": 0.0,
    "scopeIsolation": 1.0,
    "authorityCorrectness": 1.0,
    "unauthorizedSupersessions": 0,
    "confirmationAccuracy": 1.0,
    "contradictionRecall": 0.6,
}


@dataclass
class ContradictionCase:
    caseId: str
    kind: str
    existing: dict[str, Any]
    new: dict[str, Any]
    newAuthority: str = "explicit"
    expectDecision: str = "none"
    expectSupersedesExisting: bool = False


@dataclass
class ContradictionResult:
    caseId: str
    kind: str
    expected: str
    actual: str
    supersedes: bool
    reason: str
    detector: str = "lexical"
    similarity: Optional[float] = None
    relatedIds: list[str] = field(default_factory=list)

    @property
    def agreed(self) -> bool:
        return self.expected == self.actual

    def to_dict(self) -> dict[str, Any]:
        return {
            "caseId": self.caseId, "kind": self.kind,
            "expected": self.expected, "actual": self.actual,
            "agreed": self.agreed, "supersedes": self.supersedes,
            "detector": self.detector, "similarity": self.similarity,
            "reason": self.reason,
        }


def load_contradiction_dataset(path: Optional[str] = None) -> dict[str, Any]:
    with open(path or CONTRADICTION_DATASET_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def run_contradiction_evaluation(path: Optional[str] = None) -> dict[str, Any]:
    """Run the labeled set against the real detector. Returns a report."""
    dataset = load_contradiction_dataset(path)
    cases = [ContradictionCase(**case) for case in dataset["cases"]]
    results: list[ContradictionResult] = []
    for case in cases:
        existing = [{**case.existing, "id": "mem_existing", "status": case.existing.get("status", "active")}]
        assessment = detect_conflict(
            memory_type=case.new["memoryType"],
            scope=case.new["scope"],
            scope_id=case.new.get("scopeId"),
            subject=case.new.get("subject"),
            content=case.new["content"],
            existing=existing,
            new_authority=case.newAuthority,
        )
        supersedes = assessment.decision == DECISION_SUPERSEDE
        results.append(ContradictionResult(
            caseId=case.caseId, kind=case.kind, expected=case.expectDecision,
            actual=assessment.decision, supersedes=supersedes,
            reason=assessment.reason,
            relatedIds=[m["id"] for m in assessment.related],
        ))

    conflict_cases = [r for r in results if r.kind in _CONFLICT_KINDS]
    no_conflict_cases = [r for r in results if r.kind in _NO_CONFLICT_KINDS]
    confirmation_cases = [r for r in results if r.kind == "confirmation"]
    unrelated_cases = [r for r in results if r.kind in ("unrelated", "different-subject")]
    scope_cases = [r for r in results if r.kind == "different-scope"]
    authority_cases = [r for r in results if r.kind == "authority"]

    def _rate(hit: int, total: int) -> float:
        return round(hit / total, 3) if total else 1.0

    recall_hits = sum(1 for r in conflict_cases if r.actual in ("supersede", "propose"))
    false_conflicts = sum(1 for r in no_conflict_cases if r.actual in ("supersede", "propose"))
    confirm_hits = sum(1 for r in confirmation_cases if r.actual == "confirm")
    unrelated_safe = sum(1 for r in unrelated_cases if r.actual in ("none", "confirm"))
    scope_safe = sum(1 for r in scope_cases if r.actual == "none")
    authority_ok = sum(1 for r in authority_cases if r.actual == r.expected)
    # An unauthorized supersede is either a scope leak or an automatic statement
    # superseding an explicit one.
    unauthorized = 0
    for case, result in zip(cases, results):
        if not result.supersedes:
            continue
        if case.kind == "different-scope":
            unauthorized += 1
        if case.newAuthority == "automatic" and case.existing.get("authority") == "explicit":
            unauthorized += 1

    by_kind: dict[str, dict[str, Any]] = {}
    for result in results:
        bucket = by_kind.setdefault(result.kind, {"total": 0, "agreed": 0})
        bucket["total"] += 1
        bucket["agreed"] += 1 if result.agreed else 0
    for bucket in by_kind.values():
        bucket["accuracy"] = _rate(bucket["agreed"], bucket["total"])

    return {
        "datasetName": dataset.get("name"),
        "datasetVersion": dataset.get("version"),
        "cases": [r.to_dict() for r in results],
        "metrics": {
            "contradictionRecall": _rate(recall_hits, len(conflict_cases)),
            "falseConflictRate": round(false_conflicts / len(no_conflict_cases), 3)
            if no_conflict_cases else 0.0,
            "confirmationAccuracy": _rate(confirm_hits, len(confirmation_cases)),
            "unrelatedMemorySafety": _rate(unrelated_safe, len(unrelated_cases)),
            "scopeIsolation": _rate(scope_safe, len(scope_cases)),
            "authorityCorrectness": _rate(authority_ok, len(authority_cases)),
            "unauthorizedSupersessions": unauthorized,
            "cases": len(results),
            "byKind": by_kind,
        },
    }


def check_contradiction_thresholds(report: dict[str, Any]) -> dict[str, Any]:
    """Compare a report's metrics against the release thresholds."""
    metrics = report.get("metrics", {})
    failures: list[str] = []
    for key, limit in CONTRADICTION_THRESHOLDS.items():
        value = metrics.get(key)
        if value is None:
            continue
        if limit == 0:
            if value != 0:
                failures.append(f"{key}: expected 0, got {value!r}")
        else:
            if float(value) < float(limit):
                failures.append(f"{key}: expected >= {limit}, got {value!r}")
    return {"passed": not failures, "failures": failures}


def format_contradiction_report(report: dict[str, Any]) -> str:
    lines = [
        f"Memory contradiction eval — {report.get('datasetName')} v{report.get('datasetVersion')}",
        "",
    ]
    for case in report["cases"]:
        flag = "" if case["agreed"] else f"  EXPECT={case['expected']} GOT={case['actual']}"
        lines.append(
            f"  [{case['kind']:>24}] {case['caseId']:<34} {case['actual']}{flag}"
        )
    metrics = report["metrics"]
    lines += [
        "",
        f"  contradictionRecall={metrics['contradictionRecall']} "
        f"falseConflictRate={metrics['falseConflictRate']} "
        f"confirmationAccuracy={metrics['confirmationAccuracy']} "
        f"scopeIsolation={metrics['scopeIsolation']} "
        f"authorityCorrectness={metrics['authorityCorrectness']} "
        f"unauthorizedSupersessions={metrics['unauthorizedSupersessions']}",
    ]
    return "\n".join(lines)


__all__ = [
    "CONTRADICTION_DATASET_PATH",
    "CONTRADICTION_THRESHOLDS",
    "ContradictionCase",
    "ContradictionResult",
    "check_contradiction_thresholds",
    "format_contradiction_report",
    "load_contradiction_dataset",
    "run_contradiction_evaluation",
]
