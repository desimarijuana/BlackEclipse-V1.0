"""Contradiction-detection evaluation — a small, versioned, labeled set.

This is the measurement seam for the conflict detector. `contradictions_v1.json`
is a human-labeled set of (existing memory, new statement, authority) tuples with
the SAFE expected disposition. `run_contradiction_evaluation()` runs the REAL
`eclipse_memory.conflicts.detect_conflict` for each case and reports:

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
    {
        "direct-polarity", "paraphrase-conflict", "ambiguous", "authority",
        # Phase 3 expansion: numeric-value substitution, explicit negation,
        # subject-alias conflict, and time-bounded value change.
        "numeric-value", "negation", "subject-alias", "temporal",
    }
)
# Kinds where NO action (none) is the SAFE expectation.
_NO_CONFLICT_KINDS = frozenset(
    {"unrelated", "different-subject", "different-scope", "temporary", "observation-vs-preference"}
)

# Release thresholds for the contradiction gate. Safety is absolute: lexical
# handling must never introduce a false conflict, a scope leak, or an
# unauthorized/automatic-over-explicit supersede. Recall/confirmation are floors.
# `CONTRADICTION_THRESHOLDS` are MINIMUMS (0 means "must be exactly 0").
CONTRADICTION_THRESHOLDS: dict[str, Any] = {
    "falseConflictRate": 0.0,
    "scopeIsolation": 1.0,
    "scopeLeakage": 0.0,
    "forbiddenHits": 0,
    "authorityCorrectness": 1.0,
    "unauthorizedSupersessions": 0,
    "confirmationAccuracy": 1.0,
    "contradictionRecall": 0.6,
}

# MAXIMUMS (a higher value is worse). A missed conflict is the residual risk the
# lexical detector accepts; the ceiling keeps it visible and bounded.
CONTRADICTION_MAX_THRESHOLDS: dict[str, Any] = {
    "missedConflictRate": 0.4,
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
    explanation: str = ""

    @property
    def agreed(self) -> bool:
        return self.expected == self.actual

    def to_dict(self) -> dict[str, Any]:
        return {
            "caseId": self.caseId, "kind": self.kind,
            "expected": self.expected, "actual": self.actual,
            "agreed": self.agreed, "supersedes": self.supersedes,
            "detector": self.detector, "similarity": self.similarity,
            "reason": self.reason, "explanation": self.explanation,
        }


def _explain(kind: str, expected: str, actual: str, reason: str, related: int, supersedes: bool) -> str:
    """A plain-language explanation that is explicit about uncertainty.

    Prefers a visible review over an unsafe replacement, and says so when the
    detector is unsure rather than presenting a guess as fact.
    """
    if actual == "supersede":
        return f"replaced the existing record via {reason}" if supersedes else f"resolved by {reason}"
    if actual == "propose":
        return (
            "possible conflict detected but not certain — stored inert for review "
            f"({reason}); the existing record keeps authority."
        )
    if actual == "confirm":
        return f"recognised as the same statement ({reason}); refreshed, not duplicated."
    # actual == none
    if expected in ("supersede", "propose") and related:
        return (
            "a related memory was found but no opposing polarity/concept axis fired — "
            "left active rather than replace (a missed conflict is preferred over an "
            "unsafe replacement)."
        )
    if expected in ("supersede", "propose"):
        return "no related memory was eligible, so no conflict was raised."
    return "no conflict expected or found."


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
            explanation=_explain(
                case.kind, case.expectDecision, assessment.decision,
                assessment.reason, len(assessment.related), supersedes,
            ),
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
    # Scope leakage: a conflict was raised across two different scopes (should
    # never happen — scope isolation is absolute).
    scope_leakage = sum(
        1 for r in scope_cases if r.actual in ("supersede", "propose")
    )
    # Forbidden hits: a conflict on ANY case whose safe disposition is "none"
    # (unrelated/different-subject/different-scope/temporary).
    forbidden_hits = sum(
        1 for r in no_conflict_cases if r.actual in ("supersede", "propose")
    )
    # Missed conflicts: a case where a conflict was the safe expectation but the
    # detector returned none. The complement of recall over the conflict kinds.
    missed_conflicts = sum(1 for r in conflict_cases if r.actual == "none")
    # How often the detector, when it DID flag a conflict, was correct: a conflict
    # flagged on a conflict-case or a no-conflict case. A high precision means the
    # false-conflict rate is low; reported so an operator can judge reliance.
    flagged = [r for r in results if r.actual in ("supersede", "propose")]
    flagged_correct = sum(1 for r in flagged if r.kind in _CONFLICT_KINDS)
    precision = round(flagged_correct / len(flagged), 3) if flagged else 1.0

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
            "missedConflictRate": round(missed_conflicts / len(conflict_cases), 3)
            if conflict_cases else 0.0,
            "falseConflictRate": round(false_conflicts / len(no_conflict_cases), 3)
            if no_conflict_cases else 0.0,
            "confirmationAccuracy": _rate(confirm_hits, len(confirmation_cases)),
            "unrelatedMemorySafety": _rate(unrelated_safe, len(unrelated_cases)),
            "scopeIsolation": _rate(scope_safe, len(scope_cases)),
            "scopeLeakage": scope_leakage,
            "forbiddenHits": forbidden_hits,
            "authorityCorrectness": _rate(authority_ok, len(authority_cases)),
            "conflictPrecision": precision,
            "unauthorizedSupersessions": unauthorized,
            "cases": len(results),
            "byKind": by_kind,
        },
        # Honest interpretation: where semantic assistance would help and where it
        # cannot. Deterministic lexical detection cannot see an unlisted
        # paraphrase with no shared token and no concept axis; those are the
        # residual misses. Semantic candidates are not enabled to close them.
        "interpretation": _interpretation(results, conflict_cases, no_conflict_cases),
    }


def _interpretation(
    results: list[ContradictionResult],
    conflict_cases: list[ContradictionResult],
    no_conflict_cases: list[ContradictionResult],
) -> dict[str, Any]:
    """Explain when semantic assistance is useful and when it is not.

    A missed conflict whose text shares a concept axis or a token with the
    existing memory is a *lexical* miss that semantic candidate generation could
    surface for review. A miss with no shared signal at all is the residual risk
    the local system accepts; enabling similarity here would risk a false
    conflict, so it stays off.
    """
    lexical_misses = [
        r.caseId for r in conflict_cases
        if r.actual == "none" and r.relatedIds
    ]
    deep_misses = [
        r.caseId for r in conflict_cases
        if r.actual == "none" and not r.relatedIds
    ]
    return {
        "conflictCases": len(conflict_cases),
        "noConflictCases": len(no_conflict_cases),
        "lexicalMisses": lexical_misses,
        "deepMisses": deep_misses,
        "honestConclusion": (
            "A perfect score on this self-authored set proves the detector "
            "implements its rules, not that the rules match reality. Real usage is "
            "the evidence: see GET /eclipse-memory/usage-report. The optional "
            "semantic candidate layer was removed on the evidence that deterministic "
            "normalization closed the measured gap."
        ),
    }


def check_contradiction_thresholds(report: dict[str, Any]) -> dict[str, Any]:
    """Compare a report's metrics against the release thresholds.

    Minimum thresholds fail when the value drops below the floor (or is non-zero
    for an absolute-0 safety metric). Maximum thresholds fail when the value
    exceeds the ceiling. Never raises.
    """
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
    for key, limit in CONTRADICTION_MAX_THRESHOLDS.items():
        value = metrics.get(key)
        if value is None:
            continue
        if float(value) > float(limit):
            failures.append(f"{key}: expected <= {limit}, got {value!r}")
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
        f"missedConflictRate={metrics.get('missedConflictRate')} "
        f"falseConflictRate={metrics['falseConflictRate']} "
        f"conflictPrecision={metrics.get('conflictPrecision')} "
        f"confirmationAccuracy={metrics['confirmationAccuracy']} "
        f"scopeIsolation={metrics['scopeIsolation']} "
        f"scopeLeakage={metrics.get('scopeLeakage')} "
        f"forbiddenHits={metrics.get('forbiddenHits')} "
        f"authorityCorrectness={metrics['authorityCorrectness']} "
        f"unauthorizedSupersessions={metrics['unauthorizedSupersessions']}",
    ]
    interpretation = report.get("interpretation")
    if interpretation:
        lines += [
            "",
            "  interpretation:",
            f"    lexical misses (missed conflicts with a shared signal): "
            f"{interpretation.get('lexicalMisses')}",
            f"    deep misses (no shared signal): "
            f"{interpretation.get('deepMisses')}",
        ]
        if interpretation.get("honestConclusion"):
            lines.append(f"    note: {interpretation['honestConclusion']}")
    return "\n".join(lines)


__all__ = [
    "CONTRADICTION_DATASET_PATH",
    "CONTRADICTION_MAX_THRESHOLDS",
    "CONTRADICTION_THRESHOLDS",
    "ContradictionCase",
    "ContradictionResult",
    "check_contradiction_thresholds",
    "format_contradiction_report",
    "load_contradiction_dataset",
    "run_contradiction_evaluation",
]
