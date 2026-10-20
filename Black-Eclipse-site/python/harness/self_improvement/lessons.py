"""Adopted lessons: the cue/evidence gate and deterministic retrieval.

A lesson is a *verified* transferable note, not a transcript of an evaluation.
The upstream rule is strict and is enforced here:

* `cue` (when the lesson applies), `lesson` (what to do) and `evidence` (why it
  is believed) are all required; a missing field discards the lesson;
* the lesson text passes the evaluation verdict tripwire before it is stored, so
  an answer key can never become reusable context;
* adoption records the artifact and the validation run that proved it;
* retrieval is deterministic and scoped, and only considers a lesson whose
  validation run COMPLETED. An unverified lesson is inert.

This module adds no model call, no second database and no authority: a lesson is
a labelled, non-authoritative prompt hint at most.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Optional

from ..evaluation.verdict_guard import (
    assert_text_has_no_verdict_leaks,
    find_marker_in_text,
)

LESSON_STATUS = "adopted"

ACCEPTED_DECISIONS = frozenset({
    "accepted", "adopted", "benchmark", "landed", "tests_passed", "validated",
})

_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "into", "is", "it", "its", "of", "on", "or", "that", "the",
    "their", "then", "this", "to", "was", "were", "when", "with", "after",
    "before", "always", "never", "should", "must", "use", "using", "task",
    "run", "runs", "lesson",
})

_WORD = re.compile(r"[a-z0-9]+")
_IGNORED_SCOPE_KEYS = frozenset({"scopeclaim", "regressioncase", "note", "limitations"})
_MARKET_KEYS = frozenset({"market", "markets"})
_SCOPE_TEXT_KEYS = frozenset({"capability", "domain", "region", "subject"})


def _normalize(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def lesson_signature(cue: str, lesson: str) -> str:
    """The deterministic dedupe identity: the same cue + lesson is one row."""
    raw = f"{_normalize(cue)}|{_normalize(lesson)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _has_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _has_evidence(evidence: Any) -> bool:
    if evidence is None:
        return False
    if isinstance(evidence, str):
        return bool(evidence.strip())
    if isinstance(evidence, (list, tuple, set, dict)):
        return bool(evidence)
    return bool(evidence)


def _accepted(decision: Any) -> bool:
    if isinstance(decision, str):
        return decision.strip().lower() in ACCEPTED_DECISIONS
    if isinstance(decision, Mapping):
        label = str(decision.get("decision") or "").strip().lower()
        return bool(
            decision.get("accepted")
            or decision.get("passed")
            or label in ACCEPTED_DECISIONS
        )
    return bool(decision)


def _cue_tokens(text: Any) -> set[str]:
    tokens = {
        token for token in _WORD.findall(_normalize(text))
        if len(token) >= 3 and token not in _STOPWORDS
    }
    # A four-character stem makes "timeout"/"timed out" and
    # "retrieval"/"retrieved" match without a stemming dependency.
    return {token[:4] if len(token) >= 4 else token for token in tokens}


def cue_match_score(lesson_cue: Any, task_cue: Any) -> int:
    """How many meaningful cue tokens overlap (0 means no match)."""
    return len(_cue_tokens(lesson_cue) & _cue_tokens(task_cue))


def _text_mentions(value: Any, text: Any) -> bool:
    return cue_match_score(value, text) > 0


def _market_mentioned(market: Any, text: Any) -> bool:
    token = str(market or "").strip()
    if not token:
        return False
    if len(token) <= 2:
        pattern = rf"(?<![A-Za-z0-9]){re.escape(token.upper())}(?![A-Za-z0-9])"
        return re.search(pattern, str(text or "")) is not None
    return _text_mentions(token, text)


def _as_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _scope_dict(scope: Any) -> dict[str, Any]:
    if isinstance(scope, Mapping):
        return {str(key): value for key, value in scope.items()}
    if isinstance(scope, str) and scope.strip():
        return {"domain": scope.strip()}
    return {}


def _scope_matches(lesson_scope: Any, task_scope: Any, cue: str) -> bool:
    scope = _scope_dict(lesson_scope)
    if not scope:
        return True
    requested = _scope_dict(task_scope)
    for key, raw_value in scope.items():
        lowered = key.lower()
        if lowered in _IGNORED_SCOPE_KEYS:
            continue
        values = _as_values(raw_value)
        if not values:
            continue
        if lowered in _MARKET_KEYS:
            requested_markets = set(
                _as_values(requested.get("markets") or requested.get("market"))
            )
            observed = {value.upper() for value in values}
            if requested_markets:
                if not observed <= {value.upper() for value in requested_markets}:
                    return False
            elif not all(_market_mentioned(value, cue) for value in values):
                return False
        elif lowered in _SCOPE_TEXT_KEYS:
            requested_values = _as_values(
                requested.get(key) or requested.get("domain")
            )
            if requested_values:
                if not {
                    _normalize(value) for value in values
                } <= {_normalize(value) for value in requested_values}:
                    return False
            elif not all(_text_mentions(value, cue) for value in values):
                return False
        else:
            if key in requested:
                if _normalize(requested.get(key)) != _normalize(raw_value):
                    return False
            elif not all(_text_mentions(value, cue) for value in values):
                return False
    return True


def _validation_completed(lesson: Mapping[str, Any], eval_store: Any) -> bool:
    run_id = str(lesson.get("validationRunId") or "").strip()
    if not run_id or eval_store is None:
        return False
    try:
        run = eval_store.get_run(run_id)
    except Exception:  # noqa: BLE001 - an unreadable run is not verified
        return False
    return bool(run) and str(run.get("status") or "").lower() == "completed"


def distill_lesson(
    store: Any,
    candidate: Mapping[str, Any],
    decision: Any,
    evidence: Any = None,
    *,
    cue: Optional[str] = None,
    lesson: Optional[str] = None,
    scope: Any = None,
    eval_store: Any = None,
    validation_run_id: Optional[str] = None,
    adopted_artifact_type: Optional[str] = None,
    adopted_artifact_id: Optional[str] = None,
    experiment: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Adopt a verified lesson, or discard/refuse it.

    Mandatory: a non-empty `cue`, `lesson` and `evidence` (the upstream gate).
    A non-adopted `decision` is discarded: a lesson is a record of a verified
    change, never a proposal. A verdict leak raises `VerdictLeakError` (a hard
    error, not a warning). Dedupe is by the normalized cue + lesson signature.
    """
    candidate = dict(candidate or {})
    experiment = dict(experiment or {})

    resolved_cue = str(cue or candidate.get("cue") or "").strip()
    if not _has_text(resolved_cue):
        return {"stored": False, "discarded": True, "reason": "missing_cue"}

    resolved_lesson = str(
        lesson or candidate.get("lesson") or candidate.get("proposedLesson") or ""
    ).strip()
    if not _has_text(resolved_lesson):
        return {"stored": False, "discarded": True, "reason": "missing_lesson"}

    resolved_evidence = (
        evidence
        if evidence is not None
        else candidate.get("evidence") or candidate.get("evidenceReferences")
    )
    if not _has_evidence(resolved_evidence):
        return {"stored": False, "discarded": True, "reason": "missing_evidence"}

    if not _accepted(decision):
        return {"stored": False, "discarded": True, "reason": "not_adopted"}

    evidence_text = (
        resolved_evidence
        if isinstance(resolved_evidence, str)
        else json.dumps(resolved_evidence, sort_keys=True, default=str)
    )
    # A leak is a hard error: find the read path that produced it; never widen
    # the marker list or store a transcription of the answer key.
    assert_text_has_no_verdict_leaks(
        f"{resolved_cue}\n{resolved_lesson}\n{evidence_text}",
        label="lesson",
    )

    resolved_run = str(
        validation_run_id
        or candidate.get("validationRunId")
        or candidate.get("runId")
        or experiment.get("validationRunId")
        or experiment.get("runId")
        or ""
    ).strip() or None
    resolved_type = str(
        adopted_artifact_type
        or candidate.get("adoptedArtifactType")
        or candidate.get("artifactType")
        or experiment.get("adoptedArtifactType")
        or "evolution_candidate"
    ).strip()
    resolved_artifact = str(
        adopted_artifact_id
        or candidate.get("adoptedArtifactId")
        or candidate.get("artifactId")
        or experiment.get("adoptedArtifactId")
        or experiment.get("proposalId")
        or candidate.get("id")
        or resolved_run
        or ""
    ).strip() or None

    signature = lesson_signature(resolved_cue, resolved_lesson)
    finder = getattr(store, "find_candidate_by_signature", None)
    existing = finder(signature) if callable(finder) else None
    if existing:
        patch = {
            "status": LESSON_STATUS,
            "cue": resolved_cue,
            "adoptedArtifactType": resolved_type,
            "adoptedArtifactId": resolved_artifact,
            "validationRunId": resolved_run,
        }
        if scope is not None:
            patch["scope"] = scope
        updater = getattr(store, "update_candidate", None)
        if callable(updater):
            updater(str(existing.get("id")), **patch)
        return {
            "stored": False,
            "duplicate": True,
            "reason": "duplicate_cue_lesson",
            "lessonId": existing.get("id"),
            "signature": signature,
            "validationRunId": resolved_run,
            "adoptedArtifactType": resolved_type,
            "adoptedArtifactId": resolved_artifact,
        }

    row = {
        **candidate,
        "id": None,
        "sourceRunId": candidate.get("sourceRunId") or resolved_run,
        "candidateType": candidate.get("candidateType") or "adopted_lesson",
        "title": str(candidate.get("title") or resolved_cue)[:200],
        "problem": candidate.get("problem") or f"Cue: {resolved_cue}",
        "proposedLesson": resolved_lesson,
        "evidenceReferences": resolved_evidence,
        "signature": signature,
        "duplicateGroup": signature,
        "status": LESSON_STATUS,
        "cue": resolved_cue,
        "adoptedArtifactType": resolved_type,
        "adoptedArtifactId": resolved_artifact,
        "validationRunId": resolved_run,
        "scope": scope if scope is not None else candidate.get("scope"),
        "knownLimitations": candidate.get("knownLimitations") or (
            "Adopted from one verified experiment; apply only to the matching "
            "cue and recorded scope."
        ),
    }
    lesson_id = store.save_candidate(row)
    return {
        "stored": True,
        "duplicate": False,
        "lessonId": lesson_id,
        "signature": signature,
        "validationRunId": resolved_run,
        "adoptedArtifactType": resolved_type,
        "adoptedArtifactId": resolved_artifact,
    }


def select_lessons(
    store: Any,
    *,
    cue: str,
    scope: Any = None,
    eval_store: Any = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """The deterministic, scoped, verified lesson set for a later task.

    Eligible = adopted + matching cue + matching scope + a COMPLETED validation
    run + clean of verdict markers. An unknown/unverifiable validation run is
    not eligible (fail closed). Order is match score desc, then createdAt, then
    id, so the same inputs always produce the same order.
    """
    if not _has_text(cue):
        return []
    lister = getattr(store, "list_candidates", None)
    if not callable(lister):
        return []
    try:
        rows = lister(status=LESSON_STATUS, limit=500)
    except Exception:  # noqa: BLE001 - retrieval must never break a run
        return []

    eligible: list[tuple[int, str, str, dict[str, Any]]] = []
    for row in rows:
        lesson_text = row.get("proposedLesson") or row.get("lesson") or ""
        if not _has_text(lesson_text):
            continue
        score = cue_match_score(row.get("cue"), cue)
        if score <= 0:
            continue
        if not _scope_matches(row.get("scope"), scope, cue):
            continue
        if not _validation_completed(row, eval_store):
            continue
        if find_marker_in_text(f"{row.get('cue') or ''}\n{lesson_text}") is not None:
            continue
        eligible.append((
            -score,
            str(row.get("createdAt") or ""),
            str(row.get("id") or ""),
            row,
        ))
    eligible.sort(key=lambda item: (item[0], item[1], item[2]))
    return [row for _, _, _, row in eligible[: max(0, int(limit))]]


__all__ = [
    "ACCEPTED_DECISIONS",
    "LESSON_STATUS",
    "cue_match_score",
    "distill_lesson",
    "lesson_signature",
    "select_lessons",
]
