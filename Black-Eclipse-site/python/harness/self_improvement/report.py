"""The operator digest: what the self-improvement loop actually did.

One read-only summary an operator can look at instead of reading the raw
tables: the experiments that ran, what they cost, what was accepted, which
candidates are in flight, the lessons that were adopted, and where production
is drifting. Everything is measured or `UNKNOWN`; a missing source never
becomes a fabricated zero.
"""

from __future__ import annotations

from typing import Any, Optional

from ..evaluation.repair_metrics import metrics_from_rsl_runs, rsl_runs_from_store


def _iso_days_ago(days: int) -> str:
    import datetime as _dt

    then = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=max(1, int(days)))
    return then.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


def _candidate_counts(store: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        from ..code.evolution_store import EvolutionStore  # noqa: PLC0415

        for candidate in EvolutionStore(store).list_candidates(limit=500):
            status = str(candidate.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
    except Exception:  # noqa: BLE001 - no candidate table means no candidates
        return {}
    return counts


def _recent_candidates(store: Any, limit: int = 10) -> list[dict[str, Any]]:
    try:
        from ..code.evolution_store import EvolutionStore  # noqa: PLC0415

        rows = EvolutionStore(store).list_candidates(limit=max(1, int(limit)))
    except Exception:  # noqa: BLE001 - no candidate table means no candidates
        return []
    return [
        {
            "id": row.get("id"),
            "status": row.get("status"),
            "subjectType": row.get("subjectType"),
            "sourceCategory": row.get("sourceCategory"),
            "createdAt": row.get("createdAt"),
        }
        for row in rows
    ]


def _adopted_lessons(store: Any, limit: int = 5) -> list[dict[str, Any]]:
    """The most recent adopted lessons (cue + lesson text, no private data)."""
    db = getattr(store, "_db", None)
    if db is None:
        return []
    try:
        rows = db.execute(
            "SELECT id, cue, proposedLesson, createdAt FROM LearningCandidate "
            "WHERE status = 'adopted' ORDER BY createdAt DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    except Exception:  # noqa: BLE001 - the learning table may not exist here
        return []
    return [
        {
            "id": row["id"],
            "cue": str(row["cue"] or "")[:200],
            "lesson": str(row["proposedLesson"] or "")[:400],
            "createdAt": row["createdAt"],
        }
        for row in rows
    ]


def _drift(store: Any, scope: Optional[str] = None) -> dict[str, Any]:
    try:
        from .drift import detect_store_drift  # noqa: PLC0415

        signal = detect_store_drift(
            store, scope=None if scope in (None, "global") else scope,
        )
    except Exception:  # noqa: BLE001 - drift is diagnostics
        return {"status": "unmeasured", "scope": scope or "global"}
    return {
        "scope": signal.get("scope"),
        "status": signal.get("status"),
        "drop": signal.get("drop"),
        "window": signal.get("window"),
        "minSamples": signal.get("minSamples"),
    }


def build_digest(
    store: Any, *, days: int = 7, scope: Optional[str] = None, limit: int = 10,
) -> dict[str, Any]:
    """The digest for the last `days` days (read-only, never a fabricated zero)."""
    since = _iso_days_ago(days)
    runs = rsl_runs_from_store(store, limit=1000, since=since)
    metrics = metrics_from_rsl_runs(runs)
    return {
        "days": max(1, int(days)),
        "since": since,
        "experiments": {
            "rsl_experiments": metrics.get("rsl_experiments"),
            "rsl_accepted": metrics.get("rsl_accepted"),
            "rsl_rejected": metrics.get("rsl_rejected"),
            "rsl_unmeasured": metrics.get("rsl_unmeasured"),
            "regression_rate": metrics.get("regression_rate"),
            "cost_usd": metrics.get("rsl_cost_usd"),
            "cost_per_accepted": metrics.get("rsl_cost_per_accepted"),
        },
        "candidates": _candidate_counts(store),
        "recentCandidates": _recent_candidates(store, limit=limit),
        "lessons": _adopted_lessons(store, limit=limit),
        "drift": _drift(store, scope=scope),
    }


def render_markdown(digest: dict[str, Any]) -> str:
    """A readable digest (the operator's weekly view)."""
    experiments = digest.get("experiments") or {}

    def _fmt(value: Any) -> str:
        if value is None:
            return "UNKNOWN"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    lines = [
        "# RSL digest",
        "",
        f"- window: the last {digest.get('days')} day(s) (since {digest.get('since')})",
        "",
        "## Experiments",
        "",
        "| measure | value |",
        "|---|---|",
    ]
    for key in (
        "rsl_experiments", "rsl_accepted", "rsl_rejected", "rsl_unmeasured",
        "regression_rate", "cost_usd", "cost_per_accepted",
    ):
        lines.append(f"| {key} | {_fmt(experiments.get(key))} |")
    lines += ["", "## Candidates", ""]
    candidates = digest.get("candidates") or {}
    if candidates:
        for status in sorted(candidates):
            lines.append(f"- {status}: {candidates[status]}")
    else:
        lines.append("- none recorded")
    lines += ["", "## Recent candidates", ""]
    recent = digest.get("recentCandidates") or []
    if recent:
        for row in recent:
            lines.append(
                f"- `{row.get('id')}` {row.get('status')} "
                f"({row.get('sourceCategory') or 'unknown'})"
            )
    else:
        lines.append("- none")
    lines += ["", "## Adopted lessons", ""]
    lessons = digest.get("lessons") or []
    if lessons:
        for lesson in lessons:
            lines.append(f"- {lesson.get('cue')}: {lesson.get('lesson')}")
    else:
        lines.append("- none adopted yet")
    drift = digest.get("drift") or {}
    lines += [
        "",
        "## Production drift",
        "",
        f"- scope: {drift.get('scope') or 'global'} · status: {drift.get('status') or 'unmeasured'}"
        f" · drop: {_fmt(drift.get('drop'))}",
        "",
    ]
    return "\n".join(lines)


__all__ = ["build_digest", "render_markdown"]
