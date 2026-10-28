"""Loop health: is the self-improvement machinery actually closing?

Recording is not learning. This module reports the joints where a queue has no
consumer, a recommendation has no score, or a candidate has no decision, and it
states the evidence that would prove a change worked in the next 30 days.

Nothing here fabricates a metric: an unavailable input is reported as a gap.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .lesson_contract import candidate_problems

# Rows written before the loop-closure contract shipped are reported as legacy,
# not counted as current defects. Override per deployment if needed.
CONTRACT_SINCE = os.environ.get(
    "HARNESS_LEARNING_CONTRACT_SINCE", "2026-10-28T00:00:00.000Z"
)


def _now(moment: Optional[str] = None) -> datetime:
    if moment:
        stamp = datetime.fromisoformat(str(moment).replace("Z", "+00:00"))
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _parse(stamp: Any) -> Optional[datetime]:
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def nonconforming_candidates(skill_store: Any) -> list[dict[str, Any]]:
    """Stored candidates that violate the falsifiability contract."""
    try:
        rows = skill_store.list_candidates(status="detected", limit=500)
    except Exception:  # noqa: BLE001
        return []
    flagged: list[dict[str, Any]] = []
    for row in rows:
        problems = candidate_problems(row)
        if problems:
            flagged.append({"id": row.get("id"), "problems": problems})
    return flagged


def quarantine_nonconforming_candidates(
    skill_store: Any, *, dry_run: bool = False,
) -> dict[str, Any]:
    """Reject detected candidates that cannot pass the contract.

    Retained with a status reason; never deleted.
    """
    flagged = nonconforming_candidates(skill_store)
    if not dry_run:
        for item in flagged:
            try:
                existing = skill_store.get_candidate(item["id"]) or {}
                prior = str(existing.get("knownLimitations") or "").strip()
                reason = "Quarantined (nonconforming): " + ", ".join(item["problems"])
                skill_store.update_candidate(
                    item["id"], status="rejected",
                    knownLimitations=(reason + (f" {prior}" if prior else ""))[:1000],
                )
            except Exception:  # noqa: BLE001 - one bad row never stops the sweep
                continue
    return {
        "ok": True,
        "dryRun": bool(dry_run),
        "quarantined": flagged,
        "quarantinedCount": len(flagged),
    }


def audit_reviews(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Count typed lessons and justified vs bare nulls in completed reviews."""
    typed = justified = unjustified = 0
    for review in reviews:
        result = review.get("result") or {}
        for outcome in result.get("outcomes") or []:
            if not isinstance(outcome, dict):
                continue
            if outcome.get("category") == "typed_lesson":
                typed += 1
            elif outcome.get("category") == "no_learning":
                reason = str(outcome.get("reason") or "").strip()
                checked = outcome.get("evidenceChecked") or []
                if outcome.get("justified") is True and reason and checked:
                    justified += 1
                else:
                    unjustified += 1
    return {
        "typedLessons": typed,
        "justifiedNulls": justified,
        "unjustifiedNulls": unjustified,
        "reviews": len(reviews),
    }


def gate_report(
    run_store: Any,
    *,
    skill_store: Any = None,
    advisory_service: Any = None,
    learning_mode: Optional[str] = None,
    window_days: int = 30,
    now: Optional[str] = None,
    since: Optional[str] = None,
) -> dict[str, Any]:
    """Report whether every queue has a consumer within the window.

    A growing `detected` backlog with zero accepted decisions over a full window
    is a DESIGN failure, not a backlog to be reported as normal.
    """
    moment = _now(now)
    cutoff = moment - timedelta(days=max(1, int(window_days)))
    since_dt = _parse(since or CONTRACT_SINCE) or cutoff
    report: dict[str, Any] = {
        "windowDays": int(window_days),
        "learningMode": learning_mode,
        "gaps": [],
        "ok": True,
    }
    if learning_mode == "off":
        report["ok"] = False
        report["gaps"].append({
            "code": "intake_disabled",
            "detail": (
                "skill_learning_mode is off: run-analysis candidates cannot be "
                "created, so a correct specimen cannot replace a quarantined one. "
                "This is a policy choice, not a passing state."
            ),
        })

    candidate_store = skill_store
    candidates: Optional[list[dict[str, Any]]] = None
    if candidate_store is not None:
        try:
            candidates = candidate_store.list_candidates(limit=500)
        except Exception:  # noqa: BLE001
            candidates = None
    if candidates is not None:
        by_status = _count_by(candidates, "status")
        detected = [c for c in candidates if str(c.get("status")) == "detected"]
        stale = [
            c for c in detected
            if (_parse(c.get("createdAt")) or moment) <= cutoff
        ]
        accepted = int(by_status.get("accepted", 0))
        nonconforming = nonconforming_candidates(candidate_store)
        report["candidates"] = {
            "total": len(candidates),
            "byStatus": by_status,
            "detected": len(detected),
            "staleDetected": len(stale),
            "accepted": accepted,
            "nonconforming": len(nonconforming),
        }
        if nonconforming:
            report["ok"] = False
            report["gaps"].append({
                "code": "candidates_nonconforming",
                "detail": (
                    f"{len(nonconforming)} detected candidate(s) cannot pass the "
                    "falsifiability contract; quarantine them"
                ),
            })
        if detected and accepted == 0 and stale:
            report["ok"] = False
            report["gaps"].append({
                "code": "candidate_queue_unconsumed",
                "detail": (
                    f"{len(stale)} detected candidate(s) older than {window_days}d "
                    "with zero accepted; nobody is draining the queue"
                ),
            })
    else:
        report["candidates"] = {"available": False, "reason": "skill store unavailable"}
        report["gaps"].append({"code": "candidate_store_unavailable",
                               "detail": "cannot inspect the candidate queue"})

    reviews: Optional[list[dict[str, Any]]] = None
    try:
        reviews = run_store.list_learning_reviews(status="completed", limit=500)
    except Exception:  # noqa: BLE001
        reviews = None
    if reviews is not None:
        current = [
            r for r in reviews
            if (_parse(r.get("finishedAt") or r.get("createdAt")) or moment) >= since_dt
        ]
        legacy = [r for r in reviews if r not in current]
        audit = audit_reviews(current)
        report["reviews"] = {
            "completed": len(current),
            "withTypedLesson": audit["typedLessons"],
            "typedLessonRate": (
                round(audit["typedLessons"] / len(current), 4) if current else None
            ),
            "justifiedNulls": audit["justifiedNulls"],
            "unjustifiedNulls": audit["unjustifiedNulls"],
        }
        report["legacyReviews"] = audit_reviews(legacy)
        report["contractSince"] = since_dt.isoformat()
        if current and audit["typedLessons"] == 0:
            report["ok"] = False
            report["gaps"].append({
                "code": "reviews_emit_no_lessons",
                "detail": (
                    f"{len(current)} current review(s) and none emitted a typed "
                    "lesson; the review is a terminal sink"
                ),
            })
        if audit["unjustifiedNulls"]:
            report["ok"] = False
            report["gaps"].append({
                "code": "reviews_emit_unjustified_nulls",
                "detail": (
                    f"{audit['unjustifiedNulls']} CURRENT no_learning outcome(s) "
                    "lack a reason/evidenceChecked; a bare null is a defect"
                ),
            })
    else:
        report["reviews"] = {"available": False, "reason": "review store unavailable"}

    if advisory_service is not None:
        try:
            store = advisory_service.store
            decisions = store.list_decisions(limit=10_000)
            outcomes = {
                o["decisionId"]: o
                for o in store.outcomes_for([d["id"] for d in decisions])
            }

            def _bucket(rows: list[dict[str, Any]]) -> dict[str, Any]:
                evaluated = sum(1 for d in rows if d["id"] in outcomes)
                unscored = sum(
                    1 for d in rows
                    if d.get("horizon") in (None, "") or d.get("horizon") == "unscored"
                )
                overdue = sum(
                    1 for d in rows
                    if d["id"] not in outcomes
                    and d.get("dueAt")
                    and str(d["dueAt"]) <= moment.isoformat()
                )
                return {
                    "total": len(rows),
                    "evaluated": evaluated,
                    "unscored": unscored,
                    "overdue": overdue,
                }

            current_advice = [
                d for d in decisions
                if (_parse(d.get("createdAt")) or moment) >= since_dt
            ]
            legacy_advice = [d for d in decisions if d not in current_advice]
            current = _bucket(current_advice)
            card = advisory_service.scorecard(now=moment.isoformat())
            report["advisory"] = {
                **current,
                "demotedMethods": card.get("demotedMethods") or [],
            }
            report["legacyAdvisory"] = _bucket(legacy_advice)
            if current["overdue"] > 0:
                report["ok"] = False
                report["gaps"].append({
                    "code": "advice_never_scored",
                    "detail": (
                        f"{current['overdue']} current recommendation(s) are past "
                        "their stated horizon and unscored"
                    ),
                })
            if current["unscored"] > 0:
                report["ok"] = False
                report["gaps"].append({
                    "code": "advice_missing_horizon",
                    "detail": (
                        f"{current['unscored']} current recommendation(s) have no "
                        "scoring horizon"
                    ),
                })
        except Exception as exc:  # noqa: BLE001
            report["advisory"] = {"available": False, "reason": str(exc)[:200]}
    else:
        report["advisory"] = {"available": False, "reason": "no advisory service"}

    if skill_store is not None and callable(getattr(skill_store, "list_memories", None)):
        try:
            from ..eclipse_memory.consolidation import consolidate_active  # noqa: PLC0415

            memory = consolidate_active(skill_store, dry_run=True)
            report["memory"] = {
                "duplicateCount": memory.get("duplicateCount", 0),
                "conflictCount": memory.get("conflictCount", 0),
                "residueCount": memory.get("residueCount", 0),
                "relatedCount": memory.get("relatedCount", 0),
            }
        except Exception as exc:  # noqa: BLE001
            report["memory"] = {"available": False, "reason": str(exc)[:200]}
    else:
        report["memory"] = {"available": False, "reason": "no memory store"}

    return report


def expire_stale_candidates(
    skill_store: Any,
    *,
    days: int = 30,
    now: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Mark a `detected` candidate stale after a full window with no consumer."""
    moment = _now(now)
    cutoff = moment - timedelta(days=max(1, int(days)))
    expired: list[str] = []
    try:
        candidates = skill_store.list_candidates(status="detected", limit=500)
    except Exception:  # noqa: BLE001
        return {"ok": False, "expired": [], "reason": "candidate store unavailable"}
    for candidate in candidates:
        created = _parse(candidate.get("createdAt"))
        if created is None or created > cutoff:
            continue
        if not dry_run:
            try:
                skill_store.update_candidate(
                    candidate["id"], status="expired",
                    statusReason=f"no consumer within {days}d",
                )
            except Exception:  # noqa: BLE001
                continue
        expired.append(candidate["id"])
    return {
        "ok": True,
        "dryRun": bool(dry_run),
        "expired": expired,
        "expiredCount": len(expired),
    }


def loop_metrics(
    run_store: Any,
    *,
    skill_store: Any = None,
    advisory_service: Any = None,
    now: Optional[str] = None,
) -> dict[str, Any]:
    """Current loop measurements. Missing inputs are explicit gaps."""
    metrics: dict[str, Any] = {"measuredAt": _now(now).isoformat()}
    try:
        metrics["reviews"] = run_store.learning_review_health()
    except Exception as exc:  # noqa: BLE001
        metrics["reviews"] = {"available": False, "reason": str(exc)[:200]}
    if skill_store is not None:
        try:
            candidates = skill_store.list_candidates(limit=1000)
            metrics["candidates"] = {
                "total": len(candidates),
                "byStatus": _count_by(candidates, "status"),
            }
        except Exception as exc:  # noqa: BLE001
            metrics["candidates"] = {"available": False, "reason": str(exc)[:200]}
    else:
        metrics["candidates"] = {"available": False, "reason": "no skill store"}
    if advisory_service is not None:
        try:
            metrics["advisory"] = advisory_service.scorecard(now=_now(now).isoformat())
        except Exception as exc:  # noqa: BLE001
            metrics["advisory"] = {"available": False, "reason": str(exc)[:200]}
    else:
        metrics["advisory"] = {"available": False, "reason": "no advisory service"}
    return metrics


EVIDENCE_PLAN: tuple[dict[str, str], ...] = (
    {
        "change": "typed lesson output + justified null",
        "worked": "≥1 review/day emits a typed lesson, and no_learning carries a reason + evidenceChecked",
        "failed": "typed-lesson count stays 0 while reviews keep completing",
    },
    {
        "change": "falsifiable candidates",
        "worked": "every new failure_recovery candidate has failedCall, recoveredCall, precondition, procedure and replayTest",
        "failed": "any new candidate has a templated title or constant 0.55 confidence",
    },
    {
        "change": "discriminating evaluation",
        "worked": "a candidate version beats or regresses its base on named outcome metrics; repeated identical passes stop",
        "failed": "evaluations keep passing with no metric comparison or identical results",
    },
    {
        "change": "advice scoring",
        "worked": "overdue recommendations trend to zero and per-method hit rate becomes non-null",
        "failed": "unscored/overdue counts grow while new recommendations are issued",
    },
    {
        "change": "route diagnosis",
        "worked": "routing defects are rerouted and no longer re-logged as provider failures",
        "failed": "the same source×capability generic route keeps failing while specific markets succeed",
    },
    {
        "change": "memory consolidation",
        "worked": "active duplicate/conflict count is zero after a sweep",
        "failed": "new active contradictions are written between sweeps",
    },
    {
        "change": "gate reachability",
        "worked": "candidate queue age stays below the window and acceptance is non-zero",
        "failed": "detected backlog grows with accepted still 0",
    },
)


def evidence_plan() -> list[dict[str, str]]:
    return [dict(item) for item in EVIDENCE_PLAN]


__all__ = [
    "EVIDENCE_PLAN",
    "audit_reviews",
    "evidence_plan",
    "expire_stale_candidates",
    "gate_report",
    "loop_metrics",
    "nonconforming_candidates",
    "quarantine_nonconforming_candidates",
]
