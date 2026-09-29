"""Real-usage measurement for Eclipse-Memory (Milestone 7).

The contradiction and compaction evaluations report perfect scores on
SELF-AUTHORED labeled sets. A perfect score on a set authored by the same
reasoning that produced the detector is a smell, not evidence: it proves the
detector implements its rules, not that the rules match reality.

This module is the honest complement: a bounded, READ-ONLY report derived from
ACTUAL persisted rows over a stated window. It counts:

  * durable writes by outcome (saved / suggested / history-only / ignored) and
    the explicit-request rate, from bounded `MemoryEvent` audit rows;
  * how many conflicts the detector RAISED, how many were accepted / dismissed /
    left pending by the operator's actual resolution, and the implied false
    positive rate;
  * how many conflicts were likely MISSED — two active, same-scope, same-type
    records on the same subject dimension that did not conflict — which a human
    can review.

It is content-free where it can be: it never returns memory text wholesale. A
conflict is summarised by ids/counts only. Empty data yields an honest empty
report (zeros with ``insufficientData: true``), never a fake.

Nothing here mutates state. No new table, no daemon.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# Audit event types mapped to a durable-write outcome. Read-only counts.
_SAVE_EVENTS = ("memory.explicit_saved", "memory.conflict_confirmed")
_SUGGEST_EVENTS = ("memory.suggested",)
_HISTORY_ONLY_EVENTS = ("memory.intent_history_only",)
_IGNORE_EVENTS = ("memory.intent_ignored", "memory.intent_refused", "memory.write_refused")
_EXPLICIT_EVENTS = ("memory.explicit_saved",)
# A conflict the detector raised for review.
_CONFLICT_RAISED = ("memory.conflict_needs_review",)
# Resolutions the operator actually took.
_CONFLICT_ACCEPTED = ("memory.conflict_confirmed", "memory.conflict_confirmed_both",
                      "memory.conflict_merged", "memory.conflict_superseded")
_CONFLICT_DISMISSED = ("memory.conflict_kept", "memory.conflict_dismissed")

_MAX_ROWS = 5000  # hard bound on rows read


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _window_start(days: int) -> str:
    start = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    return start.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _counts_by_type(store: Any, since: str) -> dict[str, int]:
    """Bounded counts of MemoryEvent types at/after `since` (no content)."""
    try:
        rows = store._db.execute(
            "SELECT type, COUNT(*) AS n FROM MemoryEvent WHERE at >= ? "
            "GROUP BY type LIMIT ?",
            (since, _MAX_ROWS),
        ).fetchall()
    except Exception:  # noqa: BLE001 - an unreadable ledger is no data, not a crash
        return {}
    return {row["type"]: int(row["n"]) for row in rows}


def _sum_types(counts: dict[str, int], types: tuple[str, ...]) -> int:
    return sum(counts.get(t, 0) for t in types)


def _likely_missed_conflicts(store: Any, limit: int = 50) -> dict[str, Any]:
    """Active same-scope/same-type records on the same subject that did not conflict.

    Two concurrently-active records on one subject dimension is a candidate the
    detector did NOT catch (a human can review). This is a heuristic signal, not a
    verdict; only ids/subject/type are returned, never memory text.
    """
    try:
        rows = store._db.execute(
            """SELECT subject, memoryType, scope, scopeId, COUNT(*) AS n
               FROM MemoryRecord
               WHERE status='active' AND subject IS NOT NULL
               GROUP BY subject, memoryType, scope, scopeId
               HAVING COUNT(*) > 1
               ORDER BY n DESC
               LIMIT ?""",
            (max(1, min(limit, 200)),),
        ).fetchall()
    except Exception:  # noqa: BLE001
        return {"count": 0, "groups": []}
    groups = []
    for row in rows:
        try:
            ids = [
                r["id"] for r in store._db.execute(
                    """SELECT id FROM MemoryRecord
                       WHERE status='active' AND subject=?
                         AND memoryType=? AND scope=?
                         AND (scopeId IS ? OR scopeId = ?)
                       LIMIT 20""",
                    (row["subject"], row["memoryType"], row["scope"],
                     row["scopeId"], row["scopeId"]),
                ).fetchall()
            ]
        except Exception:  # noqa: BLE001
            ids = []
        groups.append({
            "subject": row["subject"],
            "memoryType": row["memoryType"],
            "scope": row["scope"],
            "count": int(row["n"]),
            "memoryIds": ids,
        })
    return {"count": len(groups), "groups": groups}


def _pending_conflicts(store: Any) -> int:
    try:
        row = store._db.execute(
            "SELECT COUNT(*) FROM MemoryRecord WHERE status='proposed'"
        ).fetchone()
        return int(row[0]) if row else 0
    except Exception:  # noqa: BLE001
        return 0


def _ground_truth_labels(store: Any, since: str) -> dict[str, int]:
    """Count operator ground-truth conflict labels (true vs false positive).

    Append-only events; the label is a bounded, content-free operator judgement.
    A memory may be relabelled; the latest label wins, so we take the LAST event
    per memory id within the window.
    """
    try:
        rows = store._db.execute(
            "SELECT memoryId, data, at FROM MemoryEvent "
            "WHERE type='memory.conflict_labeled' AND at >= ? ORDER BY at ASC",
            (since,),
        ).fetchall()
    except Exception:  # noqa: BLE001
        return {"true_conflict": 0, "false_positive": 0}
    latest: dict[str, str] = {}
    for row in rows:
        try:
            import json as _json

            data = _json.loads(row["data"]) if row["data"] else {}
        except (TypeError, ValueError):
            data = {}
        label = str(data.get("label") or "")
        if label in ("true_conflict", "false_positive"):
            latest[str(row["memoryId"])] = label
    return {
        "true_conflict": sum(1 for v in latest.values() if v == "true_conflict"),
        "false_positive": sum(1 for v in latest.values() if v == "false_positive"),
    }


def _windowed_counts(store: Any, days: int) -> dict[str, Any]:
    """Split the window in half and report the delta for the key counters.

    Honest trend: small sample sizes are labelled, never smoothed into a
    misleading direction.
    """
    try:
        mid_days = max(1, days // 2)
    except Exception:  # noqa: BLE001
        mid_days = 1
    recent_since = _window_start(mid_days)
    older_since = _window_start(days)
    recent = _counts_by_type(store, recent_since)
    older_all = _counts_by_type(store, older_since)
    # older half = full window minus recent half.
    older = {k: max(0, older_all.get(k, 0) - recent.get(k, 0)) for k in older_all}

    def _writes(c: dict[str, int]) -> int:
        return _sum_types(c, _SAVE_EVENTS) + _sum_types(c, _SUGGEST_EVENTS) + \
            _sum_types(c, _HISTORY_ONLY_EVENTS) + _sum_types(c, _IGNORE_EVENTS)

    return {
        "recentHalfDays": mid_days,
        "olderHalfDays": days - mid_days,
        "decisionsRecent": _writes(recent),
        "decisionsOlder": _writes(older),
        "conflictsRaisedRecent": _sum_types(recent, _CONFLICT_RAISED),
        "conflictsRaisedOlder": _sum_types(older, _CONFLICT_RAISED),
    }


def build_usage_report(store: Any, *, window_days: int = 30) -> dict[str, Any]:
    """The bounded, read-only real-usage report. Never raises, writes nothing."""
    try:
        days = max(1, min(int(window_days), 3650))
    except Exception:  # noqa: BLE001
        days = 30
    since = _window_start(days)
    counts = _counts_by_type(store, since)

    saved = _sum_types(counts, _SAVE_EVENTS)
    suggested = _sum_types(counts, _SUGGEST_EVENTS)
    history_only = _sum_types(counts, _HISTORY_ONLY_EVENTS)
    ignored = _sum_types(counts, _IGNORE_EVENTS)
    explicit = _sum_types(counts, _EXPLICIT_EVENTS)
    total_decisions = saved + suggested + history_only + ignored

    raised = _sum_types(counts, _CONFLICT_RAISED)
    accepted = _sum_types(counts, _CONFLICT_ACCEPTED)
    dismissed = _sum_types(counts, _CONFLICT_DISMISSED)
    pending = _pending_conflicts(store)
    resolved = accepted + dismissed
    # A conflict the operator DISMISSED (kept the old value / dismissed) is the
    # closest real-usage proxy for a detector false positive.
    false_positive_rate = round(dismissed / raised, 3) if raised else None

    missed = _likely_missed_conflicts(store)
    labels = _ground_truth_labels(store, since)
    labeled_total = labels["true_conflict"] + labels["false_positive"]
    # REAL precision from operator ground truth, when any labels exist. This
    # replaces the dismissed-rate proxy as the primary number; the proxy is kept
    # as a secondary, clearly-labelled signal.
    real_precision = (
        round(labels["true_conflict"] / labeled_total, 3)
        if labeled_total else None
    )
    trend = _windowed_counts(store, days)

    insufficient = total_decisions == 0 and raised == 0

    return {
        "windowDays": days,
        "since": since,
        "insufficientData": insufficient,
        "smallSample": raised < 20 or labeled_total < 10,
        "note": (
            "Numbers are small early on; a synthetic set proves the detector "
            "implements its rules, not that the rules match reality. Real-usage "
            "numbers are the evidence — report them as-is."
        ),
        "durableWrites": {
            "saved": saved,
            "suggested": suggested,
            "historyOnly": history_only,
            "ignored": ignored,
            "totalDecisions": total_decisions,
            "explicitRequestRate": round(explicit / saved, 3) if saved else None,
        },
        "conflicts": {
            "raised": raised,
            "accepted": accepted,
            "dismissed": dismissed,
            "pending": pending,
            "falsePositiveRate": false_positive_rate,
            "resolutionRate": round(resolved / raised, 3) if raised else None,
            # Ground truth (operator-labelled), the honest primary signal.
            "labeled": labeled_total,
            "labeledTrue": labels["true_conflict"],
            "labeledFalsePositive": labels["false_positive"],
            "precision": real_precision,
        },
        "trend": trend,
        "likelyMissedConflicts": {
            "count": missed["count"],
            "groups": missed["groups"],
        },
        "readOnly": True,
    }


__all__ = ["build_usage_report"]
