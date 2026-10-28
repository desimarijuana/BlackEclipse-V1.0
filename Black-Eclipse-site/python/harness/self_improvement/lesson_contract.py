"""The typed learning contract.

A review may not end in an unexplained ``no_learning``: it must emit either a
typed lesson (condition -> action -> evidence) or an explicit null that names
what was inspected and why nothing was extractable.

A candidate is falsifiable only when it carries the failed call, the recovered
call, the observable precondition, the exact procedure and a replayable test.
Templated candidates with a constant confidence are rejected at creation.

A signal must be observed at least twice before it can be promoted to a lesson.
This module is pure/deterministic; it stores nothing and calls no model.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

MIN_OCCURRENCES = 2
MAX_CONFIDENCE = 0.9
MIN_CONFIDENCE = 0.2

GENERIC_ACTIONS = frozenset(
    {
        "prefer the alternative that worked",
        "try again",
        "retry",
        "handle the error",
        "use a fallback",
        "the run still completed",
        "be careful",
        "verify before reuse",
        "record the working source preference for this data type/coverage",
    }
)

_TEMPLATED_TITLE = re.compile(r"^recovery after .+ failure$", re.IGNORECASE)
_CONSTANT_CONFIDENCE = 0.55


def _normalize(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _word_count(text: str) -> int:
    return len(re.findall(r"[a-z0-9]+", text.lower()))


@dataclass(frozen=True)
class Lesson:
    """A verified, transferable note: when it applies, what to do, and why."""

    condition: str
    action: str
    evidence: tuple[str, ...] = ()
    failedCall: Optional[str] = None
    recoveredCall: Optional[str] = None
    precondition: Optional[str] = None
    procedure: tuple[str, ...] = ()
    replayTest: Optional[str] = None
    scope: dict[str, Any] = field(default_factory=dict)
    occurrenceCount: int = 1
    confidence: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "condition", str(self.condition or "").strip())
        object.__setattr__(self, "action", str(self.action or "").strip())
        object.__setattr__(
            self,
            "evidence",
            tuple(str(item).strip() for item in (self.evidence or ()) if str(item).strip()),
        )
        object.__setattr__(
            self,
            "procedure",
            tuple(str(item).strip() for item in (self.procedure or ()) if str(item).strip()),
        )
        object.__setattr__(
            self, "occurrenceCount", max(1, int(self.occurrenceCount or 1))
        )
        derived = derive_confidence(
            evidence_count=len(self.evidence),
            occurrence_count=self.occurrenceCount,
            has_replay=bool(self.replayTest),
        )
        if self.confidence <= 0:
            object.__setattr__(self, "confidence", derived)

    def signature(self) -> str:
        return signal_signature(kind="lesson", condition=self.condition, action=self.action)

    def problems(self) -> list[str]:
        problems: list[str] = []
        if not self.condition:
            problems.append("missing_condition")
        if not self.action:
            problems.append("missing_action")
        elif _normalize(self.action).rstrip(".!?") in GENERIC_ACTIONS:
            problems.append("generic_action")
        elif _word_count(self.action) < 4:
            problems.append("action_lacks_method")
        if not self.evidence:
            problems.append("missing_evidence")
        if self.confidence > MAX_CONFIDENCE:
            problems.append("confidence_exceeds_cap")
        return problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature(),
            "condition": self.condition,
            "action": self.action,
            "evidence": list(self.evidence),
            "failedCall": self.failedCall,
            "recoveredCall": self.recoveredCall,
            "precondition": self.precondition,
            "procedure": list(self.procedure),
            "replayTest": self.replayTest,
            "scope": dict(self.scope),
            "occurrenceCount": int(self.occurrenceCount),
            "confidence": round(float(self.confidence), 4),
        }


@dataclass(frozen=True)
class NoLearningVerdict:
    """An explicit null. A reason and the inspected evidence are mandatory."""

    reason: str
    evidenceChecked: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", str(self.reason or "").strip())
        object.__setattr__(
            self,
            "evidenceChecked",
            tuple(
                str(item).strip()
                for item in (self.evidenceChecked or ())
                if str(item).strip()
            ),
        )

    def problems(self) -> list[str]:
        problems: list[str] = []
        if not self.reason:
            problems.append("missing_reason")
        if not self.evidenceChecked:
            problems.append("missing_evidence_checked")
        return problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": "no_learning",
            "justified": not self.problems(),
            "reason": self.reason,
            "evidenceChecked": list(self.evidenceChecked),
        }


def derive_confidence(
    *, evidence_count: int, occurrence_count: int, has_replay: bool
) -> float:
    """Confidence derived from observable evidence, never a fixed template."""
    score = 0.2
    score += min(0.3, 0.1 * max(0, int(evidence_count)))
    score += min(0.3, 0.1 * max(0, int(occurrence_count) - 1))
    if has_replay:
        score += 0.1
    return round(max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, score)), 4)


def lesson_from_candidate(candidate: Mapping[str, Any]) -> Optional[Lesson]:
    """Build a Lesson from a stored candidate, or None when it is not one."""
    condition = candidate.get("condition") or candidate.get("cue") or candidate.get("problem")
    action = candidate.get("action") or candidate.get("proposedLesson")
    if not condition or not action:
        return None
    evidence = candidate.get("evidence") or candidate.get("evidenceReferences") or []
    if isinstance(evidence, Mapping):
        evidence = [evidence]
    if isinstance(evidence, str):
        evidence = [evidence]
    references: list[str] = []
    for item in evidence or []:
        if isinstance(item, Mapping):
            references.append(
                str(item.get("id") or item.get("name") or item.get("type") or item)
            )
        else:
            references.append(str(item))
    procedure = candidate.get("procedure") or candidate.get("proposedProcedure") or []
    steps: list[str] = []
    for step in procedure or []:
        if isinstance(step, Mapping):
            steps.append(str(step.get("detail") or step.get("action") or step))
        else:
            steps.append(str(step))
    return Lesson(
        condition=str(condition),
        action=str(action),
        evidence=tuple(references),
        failedCall=candidate.get("failedCall"),
        recoveredCall=candidate.get("recoveredCall"),
        precondition=candidate.get("precondition"),
        procedure=tuple(steps),
        replayTest=candidate.get("replayTest"),
        scope=candidate.get("scope") if isinstance(candidate.get("scope"), dict) else {},
        occurrenceCount=int(candidate.get("occurrenceCount") or 1),
        confidence=float(candidate.get("confidence") or 0.0),
    )


def candidate_problems(candidate: Mapping[str, Any]) -> list[str]:
    """Why a candidate is not falsifiable. Empty means it may be queued."""
    problems: list[str] = []
    candidate_type = str(candidate.get("candidateType") or "")
    title = str(candidate.get("title") or "")
    if candidate_type == "failure_recovery":
        for field_name in (
            "failedCall",
            "recoveredCall",
            "precondition",
            "proposedProcedure",
            "replayTest",
        ):
            if not candidate.get(field_name):
                problems.append(f"missing_{field_name}")
        if _TEMPLATED_TITLE.match(title.strip()):
            problems.append("templated_title")
    lesson = lesson_from_candidate(candidate)
    if lesson is not None:
        problems.extend(lesson.problems())
    confidence = candidate.get("confidence")
    try:
        confidence_value = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_value = None
    if (
        candidate_type == "failure_recovery"
        and confidence_value is not None
        and abs(confidence_value - _CONSTANT_CONFIDENCE) < 1e-9
    ):
        problems.append("constant_confidence")
    return sorted(set(problems))


def signal_signature(*, kind: str, condition: str, action: str) -> str:
    raw = json.dumps(
        {"kind": _normalize(kind), "condition": _normalize(condition), "action": _normalize(action)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sig_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _lesson_payload(outcome: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    payload = outcome.get("payload")
    if not isinstance(payload, Mapping):
        return None
    lesson = payload.get("lesson") or payload.get("typedLesson")
    return lesson if isinstance(lesson, Mapping) else None


def structural_lesson_signature(lesson: Mapping[str, Any]) -> str:
    """The stable lesson key: procedure/failure evidence, never title text.

    Old reviews stored a templated condition/action and a signature derived from
    it. Reading the recorded procedure/failure fields lets the same keyer fold
    those historical rows correctly without rewriting them.
    """
    kind = str(lesson.get("kind") or "lesson")
    procedure = lesson.get("procedure") or []
    if kind == "successful_procedure" and procedure:
        steps = [
            str(step.get("detail") or step.get("action") or step)
            if isinstance(step, Mapping) else str(step)
            for step in procedure
        ]
        return signal_signature(
            kind=kind, condition="observed sequence", action="->".join(steps),
        )
    if kind == "failure_recovery":
        failed = str(lesson.get("failedCall") or "").strip()
        recovered = str(lesson.get("recoveredCall") or "").strip()
        precondition = str(lesson.get("precondition") or "").strip()
        if failed or recovered or precondition:
            return signal_signature(
                kind=kind, condition=f"{failed}|{precondition}",
                action=recovered or "recovery",
            )
    return signal_signature(
        kind=kind,
        condition=str(lesson.get("condition") or ""),
        action=str(lesson.get("action") or ""),
    )


def aggregate_signals(
    reviews: Iterable[Mapping[str, Any]], *, min_occurrences: int = MIN_OCCURRENCES
) -> list[dict[str, Any]]:
    """Fold typed lessons across reviews into recurring, promotable signals.

    A single observation is retained as evidence but is not eligible. The same
    condition+action seen in two different reviews is.
    """
    groups: dict[str, dict[str, Any]] = {}
    for review in reviews:
        result = review.get("result")
        if not isinstance(result, Mapping):
            continue
        run_id = review.get("runId") or result.get("runId")
        for outcome in result.get("outcomes") or []:
            if not isinstance(outcome, Mapping):
                continue
            lesson = _lesson_payload(outcome)
            if not lesson:
                continue
            condition = str(lesson.get("condition") or "").strip()
            action = str(lesson.get("action") or "").strip()
            if not condition or not action:
                continue
            signature = structural_lesson_signature(lesson)
            group = groups.setdefault(
                signature,
                {
                    "signature": signature,
                    "condition": condition,
                    "action": action,
                    "kind": str(lesson.get("kind") or outcome.get("category") or "lesson"),
                    "occurrences": 0,
                    "evidenceRunIds": [],
                    "confidence": 0.0,
                },
            )
            group["occurrences"] += 1
            if run_id and run_id not in group["evidenceRunIds"]:
                group["evidenceRunIds"].append(str(run_id))
            group["confidence"] = max(
                float(group["confidence"]), float(lesson.get("confidence") or 0.0)
            )
    threshold = max(2, int(min_occurrences))
    aggregated: list[dict[str, Any]] = []
    for group in groups.values():
        distinct = len(group["evidenceRunIds"]) or group["occurrences"]
        group["distinctRuns"] = distinct
        fast = str(group.get("kind") or "") == "user_correction"
        group["eligible"] = distinct >= threshold or (fast and distinct >= 1)
        group["reason"] = (
            "explicit correction fast path"
            if fast and distinct >= 1
            else "recurrence threshold met"
            if group["eligible"]
            else f"seen in {distinct} run(s); at least {threshold} required"
        )
        aggregated.append(group)
    aggregated.sort(key=lambda item: (-int(item["occurrences"]), item["signature"]))
    return aggregated


def aggregate_from_store(
    run_store: Any, *, limit: int = 200, min_occurrences: int = MIN_OCCURRENCES
) -> list[dict[str, Any]]:
    lister = getattr(run_store, "list_learning_reviews", None)
    if not callable(lister):
        return []
    try:
        reviews = lister(status="completed", limit=limit)
    except Exception:  # noqa: BLE001 - aggregation is diagnostic, never load-bearing
        return []
    return aggregate_signals(reviews, min_occurrences=min_occurrences)


def validate_lesson(lesson: Mapping[str, Any]) -> list[str]:
    built = lesson_from_candidate(lesson)
    if built is None:
        return ["missing_condition_or_action"]
    return built.problems()


__all__ = [
    "GENERIC_ACTIONS",
    "Lesson",
    "MIN_OCCURRENCES",
    "NoLearningVerdict",
    "aggregate_from_store",
    "aggregate_signals",
    "candidate_problems",
    "derive_confidence",
    "lesson_from_candidate",
    "signal_signature",
    "validate_lesson",
]
