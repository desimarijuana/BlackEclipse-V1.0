"""Deterministic skill maintenance: staleness, usage and retirement.

Every skill Eclipse creates is permanent: there is lifecycle governance
(state machine, patch, canary, rollback) but no *maintenance*. This module
computes — from EXISTING persisted data only — which skills are stale and which
may be archived, and (only when an operator explicitly enables it) performs the
reversible archive transition. It never deletes, never promotes, never enables.

Derivation (the exact rule; no new tracking tables)
---------------------------------------------------
For each stored `SkillVersion`, using only `SkillExecution` rows, the version
history and the skill's `updatedAt`/activation timestamps:

  * ``last_used``  = the most recent ``finishedAt`` among this version's
    ``SkillExecution`` rows whose ``status == 'succeeded'`` (a failed or running
    execution is not usage). ``None`` when the version has never run.
  * ``has_run``    = whether this version has EVER been executed (any status).
  * ``anchor``     = ``activatedAt`` or ``updatedAt`` or ``createdAt`` (first
    non-null) — the point from which "how long has this been sitting unused" is
    measured.
  * ``age_days``   = days since ``last_used`` when it exists, else since
    ``anchor``.
  * ``stale``      = the version's status is ``enabled`` and ``age_days`` >=
    ``skill_stale_after_days`` (threshold > 0).
  * ``archive_eligible`` = the version is ``enabled``, ``stale``,
    ``age_days >= skill_archive_after_days`` and the threshold > 0.

Safety
------
  * **Pinned versions are exempt from EVERY automatic transition.** A pinned
    version is never archived by the pass, and the pass cannot bypass the pin.
  * **Archive, never delete.** Archiving goes through the existing lifecycle
    machinery (`SkillRegistry.set_status`), so the version remains restorable.
  * **Report-only by default.** The pass computes recommendations; it performs a
    transition only when ``skill_maintenance_enabled`` AND
    ``skill_maintenance_auto_archive`` are both true.
  * **Never raises, never blocks boot, idempotent.** Mirrors the retention
    sweep: it records its outcome in `SkillMaintenance` and returns a result.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

# The store status values that mean "installed and available to run". A version
# in any other state (draft/evaluating/canary/disabled/deprecated/archived/…)
# is not eligible: maintenance only ages ENABLED skills.
_ENABLED_STATUS = "enabled"
# The reversible retirement state the pass may move a stale skill into. A
# distinct `archived` lifecycle status separates maintenance retirement from an
# operator's deliberate `deprecated`; it is fully restorable via
# `SkillRegistry.set_status(..., "enabled")`.
_ARCHIVED_STATUS = "archived"
# Execution statuses that count as real usage. A failed/cancelled/running run is
# not usage of the skill.
_SUCCESS_STATUSES = frozenset({"succeeded", "completed", "ok", "success"})

OPERATION = "skill_maintenance"

# The recent-usage trend window: executions inside this many days count as
# "recent" usage, so a skill that is old AND unused reads differently from one
# that is old but actively used.
_TREND_WINDOW_DAYS = 30.0


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Accept a trailing 'Z' and fractional seconds; tolerate a missing zone.
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text[:19])
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days_since(when: Optional[datetime]) -> Optional[float]:
    if when is None:
        return None
    delta = _now() - when
    return max(0.0, delta.total_seconds() / 86400.0)


def _first(*values: Optional[str]) -> Optional[datetime]:
    for value in values:
        parsed = _parse_iso(value)
        if parsed is not None:
            return parsed
    return None


def _usage_index(store: Any) -> dict[tuple[str, str], dict[str, Any]]:
    """(skillId, version) -> {lastUsed, everRun, runs, successes, recentRuns} from rows.

    Reads `SkillExecution` directly (bounded) — the same table the operator sees
    in the execution activity view. No new tracking table is introduced.
    `recentRuns` counts executions in the last `_TREND_WINDOW_DAYS` days so a
    usage TREND (not just last-use age) is available.
    """
    index: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        rows = store._db.execute(
            "SELECT skillId, version, status, finishedAt, createdAt FROM SkillExecution"
        ).fetchall()
    except Exception:  # noqa: BLE001 - an unreadable ledger means "never used"
        return index
    for row in rows:
        key = (row["skillId"], row["version"])
        entry = index.setdefault(
            key, {"lastUsed": None, "everRun": True, "runs": 0, "successes": 0, "recentRuns": 0}
        )
        entry["runs"] += 1
        when = _parse_iso(row["finishedAt"]) or _parse_iso(row["createdAt"])
        if when is not None:
            age = _days_since(when)
            if age is not None and age <= _TREND_WINDOW_DAYS:
                entry["recentRuns"] += 1
        if str(row["status"] or "").lower() in _SUCCESS_STATUSES:
            entry["successes"] += 1
            if when is not None and (entry["lastUsed"] is None or when > entry["lastUsed"]):
                entry["lastUsed"] = when
    return index


def _version_assessment(
    version: dict[str, Any],
    usage: dict[str, Any],
    *,
    stale_after_days: float,
    archive_after_days: float,
) -> dict[str, Any]:
    """The bounded, content-free assessment of ONE version."""
    skill_id = version.get("skillId")
    ver = version.get("version")
    status = str(version.get("status") or "")
    pinned = bool(version.get("pinned"))
    last_used = usage.get("lastUsed")
    anchor = _first(
        version.get("activatedAt"), version.get("updatedAt"), version.get("createdAt")
    )
    reference = last_used or anchor
    age_days = _days_since(reference)
    enabled = status == _ENABLED_STATUS

    reasons: list[str] = []
    stale = False
    if enabled and age_days is not None and stale_after_days > 0 and age_days >= stale_after_days:
        stale = True
        if usage.get("everRun") and last_used is not None:
            reasons.append(f"last successful execution {age_days:.0f} days ago")
        elif usage.get("everRun"):
            reasons.append("executed, but no successful run recorded")
        else:
            reasons.append(f"never executed ({age_days:.0f} days since activation)")
    elif not enabled:
        reasons.append(f"status is {status!r}, not enabled")

    archive_eligible = (
        stale
        and archive_after_days > 0
        and age_days is not None
        and age_days >= archive_after_days
    )

    return {
        "skillId": skill_id,
        "version": ver,
        "status": status,
        "pinned": pinned,
        "enabled": enabled,
        "everRun": bool(usage.get("everRun")),
        "runs": int(usage.get("runs") or 0),
        "successes": int(usage.get("successes") or 0),
        "lastUsedAt": last_used.isoformat() if last_used else None,
        "anchorAt": anchor.isoformat() if anchor else None,
        "ageDays": round(age_days, 1) if age_days is not None else None,
        "stale": stale,
        "archiveEligible": archive_eligible,
        "pinnedExempt": pinned and (stale or archive_eligible),
        "recentRuns": int(usage.get("recentRuns") or 0),
        "trend": _usage_trend(usage),
        "reasons": reasons,
    }


def _usage_trend(usage: dict[str, Any]) -> str:
    """A coarse, honest usage direction from a single window.

    `active` when the skill ran recently, `dormant` when it has run before but
    not recently, `never` when it has never run. Deliberately not a fitted slope:
    with few executions a direction would be noise.
    """
    if not usage.get("everRun"):
        return "never"
    return "active" if int(usage.get("recentRuns") or 0) > 0 else "dormant"


def assess_skills(store: Any, policy: dict[str, Any]) -> list[dict[str, Any]]:
    """Assess every stored version. Read-only; never raises.

    Returns a bounded, content-free list ordered by (archiveEligible, stale,
    ageDays desc) so the most retired-worthy skills come first.
    """
    try:
        stale_after = float(policy.get("skill_stale_after_days") or 0)
        archive_after = float(policy.get("skill_archive_after_days") or 0)
    except Exception:  # noqa: BLE001
        stale_after, archive_after = 0.0, 0.0
    try:
        rows = store._db.execute(
            "SELECT * FROM SkillVersion ORDER BY skillId, version"
        ).fetchall()
        versions = [store._version_row(r) for r in rows]
    except Exception:  # noqa: BLE001 - an unreadable store yields no assessment
        return []
    usage = _usage_index(store)
    out: list[dict[str, Any]] = []
    for version in versions:
        key = (version.get("skillId"), version.get("version"))
        out.append(_version_assessment(
            version, usage.get(key, {}),
            stale_after_days=stale_after, archive_after_days=archive_after,
        ))
    out.sort(key=lambda a: (
        not a["archiveEligible"], not a["stale"],
        -(a["ageDays"] or 0.0), a["skillId"] or "", a["version"] or "",
    ))
    return out


def _archive_version(store: Any, registry: Any, skill_id: str, version: str, actor: Any) -> dict[str, Any]:
    """Retire one version through the existing lifecycle, or the store directly.

    Prefers `SkillRegistry.set_status` (the operator lifecycle path, with its
    permission/validation checks). A skill present only in the store (no
    in-memory registry entry) falls back to a direct store transition, so
    maintenance never fails merely because the registry was not loaded.
    """
    manifest = registry.manifest(skill_id) if registry is not None else None
    if manifest is not None:
        return registry.set_status(skill_id, _ARCHIVED_STATUS, actor, version=version)
    if store.get_version(skill_id, version) is None:
        return {"ok": False, "error": "version not found"}
    store.set_version_status(skill_id, version, _ARCHIVED_STATUS)
    store.save_review(
        skill_id=skill_id, version=version, actor=getattr(actor, "id", "operator"),
        decision="archived", notes="stale: unused past archive threshold",
    )
    return {"ok": True, "skillId": skill_id, "version": version, "status": _ARCHIVED_STATUS}


def _near_duplicate_skills(store: Any, limit: int = 20) -> list[dict[str, Any]]:
    """Bounded, content-free detector of near-duplicate skill ids.

    A skill id that differs from another only by separator/case/trailing version
    (`finance.reporting` vs `finance_reporting`) is a strong retirement/merge
    signal: one is likely a stale duplicate. Returns id groups only — never
    instructions or manifest content.
    """
    try:
        rows = store._db.execute("SELECT id, latestVersion FROM Skill ORDER BY id").fetchall()
    except Exception:  # noqa: BLE001
        return []
    def norm(skill_id: str) -> str:
        import re

        return re.sub(r"[^a-z0-9]", "", (skill_id or "").lower())

    buckets: dict[str, list[str]] = {}
    for row in rows:
        buckets.setdefault(norm(row["id"]), []).append(row["id"])
    groups = [
        {"normalized": key, "skillIds": ids}
        for key, ids in buckets.items()
        if len(ids) > 1
    ]
    groups.sort(key=lambda g: (-len(g["skillIds"]), g["normalized"]))
    return groups[:limit]


def maintenance_report(store: Any, policy: dict[str, Any]) -> dict[str, Any]:
    """A read-only maintenance report: stale skills, reasons, recommended action.

    No memory/skill content, no mutation. Includes the last recorded pass and the
    policy state so the UI can show whether the pass is report-only.
    """
    enabled = bool(policy.get("skill_maintenance_enabled"))
    auto_archive = bool(policy.get("skill_maintenance_auto_archive"))
    assessments = assess_skills(store, policy)
    stale = [a for a in assessments if a["stale"]]
    archive_eligible = [a for a in assessments if a["archiveEligible"]]
    pinned_exempt = [a for a in assessments if a["pinnedExempt"]]
    recommendations = []
    for a in archive_eligible:
        if a["pinned"]:
            recommendations.append({**a, "recommendedAction": "keep (pinned)"})
        elif auto_archive and enabled:
            recommendations.append({**a, "recommendedAction": "archive"})
        else:
            recommendations.append({**a, "recommendedAction": "review — archive"})
    for a in stale:
        if a["archiveEligible"]:
            continue
        recommendations.append({
            **a,
            "recommendedAction": "keep (pinned)" if a["pinned"] else "review",
        })
    return {
        "enabled": enabled,
        "autoArchive": auto_archive,
        "reportOnly": not (enabled and auto_archive),
        "thresholds": {
            "staleAfterDays": policy.get("skill_stale_after_days"),
            "archiveAfterDays": policy.get("skill_archive_after_days"),
        },
        "counts": {
            "versions": len(assessments),
            "stale": len(stale),
            "archiveEligible": len(archive_eligible),
            "pinnedExempt": len(pinned_exempt),
        },
        "recommendations": recommendations,
        "nearDuplicates": _near_duplicate_skills(store),
        "lastRun": store.skill_maintenance_status(OPERATION),
    }


def run_skill_maintenance(
    store: Any, registry: Any, policy: dict[str, Any], *, actor: Any = None,
) -> dict[str, Any]:
    """The maintenance pass. Idempotent, never raises, never blocks boot.

    Computes the assessment and, ONLY when ``skill_maintenance_enabled`` AND
    ``skill_maintenance_auto_archive`` are true, archives the eligible unpinned
    versions through the existing lifecycle machinery. Pinned versions are
    always exempt. Records its outcome in `SkillMaintenance`.
    """
    try:
        enabled = bool(policy.get("skill_maintenance_enabled"))
        auto_archive = bool(policy.get("skill_maintenance_auto_archive"))
        assessments = assess_skills(store, policy)
        archive_eligible = [a for a in assessments if a["archiveEligible"]]
        pinned_exempt = sum(1 for a in assessments if a["pinnedExempt"])
        stale_count = sum(1 for a in assessments if a["stale"])

        archived: list[dict[str, Any]] = []
        skipped = 0
        if enabled and auto_archive:
            if actor is None:
                from ..skills.permissions import OPERATOR_ACTOR  # noqa: PLC0415

                actor = OPERATOR_ACTOR
            for item in archive_eligible:
                # Defense in depth: re-check the pin immediately before acting so
                # the pass can never bypass it, even under a concurrent pin.
                if store.is_version_pinned(item["skillId"], item["version"]):
                    skipped += 1
                    continue
                try:
                    result = _archive_version(
                        store, registry, item["skillId"], item["version"], actor,
                    )
                except Exception as exc:  # noqa: BLE001
                    result = {"ok": False, "error": str(exc)}
                if result.get("ok"):
                    archived.append({
                        "skillId": item["skillId"], "version": item["version"],
                        "ageDays": item["ageDays"],
                    })
                    try:
                        store.append_event(
                            "skill.archived", skill_id=item["skillId"],
                            version=item["version"],
                            data={"reason": "stale: unused past archive threshold",
                                  "ageDays": item["ageDays"], "automatic": True},
                        )
                    except Exception:  # noqa: BLE001 - audit is best-effort
                        pass
                else:
                    skipped += 1

        store.record_skill_maintenance(
            OPERATION, ok=True, inspected=len(assessments), stale=stale_count,
            archived=len(archived), pinned_exempt=pinned_exempt,
            changed=len(archived), skipped=skipped,
        )
        return {
            "ok": True,
            "enabled": enabled,
            "autoArchive": auto_archive,
            "reportOnly": not (enabled and auto_archive),
            "inspected": len(assessments),
            "stale": stale_count,
            "archiveEligible": len(archive_eligible),
            "pinnedExempt": pinned_exempt,
            "archived": archived,
            "skipped": skipped,
        }
    except Exception as exc:  # noqa: BLE001 - maintenance must never block boot
        try:
            store.record_skill_maintenance(OPERATION, ok=False, error=str(exc))
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": False, "error": str(exc), "inspected": 0, "stale": 0,
            "archiveEligible": 0, "pinnedExempt": 0, "archived": [], "skipped": 0,
        }


__all__ = [
    "OPERATION",
    "assess_skills",
    "maintenance_report",
    "run_skill_maintenance",
]
