"""Outcome-linked lesson feedback: the missing measurement for the learning loop.

The lesson manifest currently records that lessons were injected, but not
whether injecting them helped. This module records both cohorts:

* lessons injected into a run (`injected=1`);
* eligible lessons that were NOT injected into that run (`injected=0`).

That matched control is what makes a lift estimate possible without a second
experiment system. Every run starts `unmeasured`; the post-run review writes the
terminal outcome. Thin data stays `UNMEASURED`, never a fabricated zero.

The store lives on the ONE agent-memory database because it keys on run ids. The
lesson rows themselves remain in `eclipse-memory.db`.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Optional

from ..evaluation.stats import wilson_interval
from ..persistence import now_iso

STATUSES = ("measured", "insufficient", "unmeasured")
OUTCOMES = ("success", "failure", "unmeasured")


def new_feedback_id() -> str:
    return "lout_" + uuid.uuid4().hex[:16]


def _normalise(text: Any) -> str:
    return " ".join(str(text or "").strip().lower().split())


def task_signature(cue: Any, scope: Any) -> str:
    """A deterministic task bucket for matched injected/control comparisons."""
    raw = json.dumps(
        {"cue": _normalise(cue), "scope": scope or {}},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _outcome_for_status(status: Any) -> str:
    value = str(status or "").strip().lower()
    if value in ("completed", "success", "succeeded"):
        return "success"
    if value in ("failed", "failure", "error", "errored"):
        return "failure"
    return "unmeasured"


def _rate(successes: int, total: int) -> Optional[float]:
    return (successes / total) if total else None


@dataclass(frozen=True)
class LessonStats:
    lessonId: str
    injected: int
    injectedSuccesses: int
    injectedRate: Optional[float]
    injectedCiLow: Optional[float]
    injectedCiHigh: Optional[float]
    control: int
    controlSuccesses: int
    controlRate: Optional[float]
    controlCiLow: Optional[float]
    controlCiHigh: Optional[float]
    lift: Optional[float]
    status: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LessonOutcomeStore:
    """`LessonOutcome` rows on the shared agent-memory connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS LessonOutcome (
              id            TEXT PRIMARY KEY,
              lessonId      TEXT NOT NULL,
              runId         TEXT NOT NULL,
              injected      INTEGER NOT NULL DEFAULT 0,
              outcome       TEXT NOT NULL DEFAULT 'unmeasured',
              taskSignature TEXT NOT NULL DEFAULT '',
              cue           TEXT NOT NULL DEFAULT '',
              scopeJson     TEXT NOT NULL DEFAULT '{}',
              createdAt     TEXT NOT NULL,
              UNIQUE(lessonId, runId)
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_lesson_outcome_lesson "
            "ON LessonOutcome(lessonId, outcome)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_lesson_outcome_run "
            "ON LessonOutcome(runId)"
        )
        self._db.commit()

    def record_injections(
        self,
        run_id: str,
        lessons: Iterable[Mapping[str, Any]],
        injected_ids: Iterable[str],
        *,
        cue: str = "",
        scope: Any = None,
    ) -> int:
        """Record one injected/control row per eligible lesson for this run.

        `lessons` is the full eligible set (not only the ones that fit the
        manifest). `injected_ids` is the subset actually put in the prompt. A
        repeated call for the same run is idempotent.
        """
        run = str(run_id or "").strip()
        if not run:
            return 0
        injected = {str(item) for item in injected_ids if str(item)}
        signature = task_signature(cue, scope)
        scope_json = json.dumps(scope or {}, sort_keys=True, default=str)
        written = 0
        for lesson in lessons or []:
            if not isinstance(lesson, Mapping):
                continue
            lesson_id = str(lesson.get("id") or "").strip()
            if not lesson_id:
                continue
            self._db.execute(
                """INSERT OR IGNORE INTO LessonOutcome
                   (id, lessonId, runId, injected, outcome, taskSignature, cue,
                    scopeJson, createdAt)
                   VALUES (?, ?, ?, ?, 'unmeasured', ?, ?, ?, ?)""",
                (
                    new_feedback_id(), lesson_id, run,
                    1 if lesson_id in injected else 0,
                    signature, str(cue or "")[:500], scope_json, now_iso(),
                ),
            )
            written += 1
        self._db.commit()
        return written

    def record_run_outcome(self, run_id: str, status: Any) -> int:
        """Write the terminal outcome for every lesson observation of a run."""
        run = str(run_id or "").strip()
        if not run:
            return 0
        outcome = _outcome_for_status(status)
        cursor = self._db.execute(
            "UPDATE LessonOutcome SET outcome=? WHERE runId=? AND outcome='unmeasured'",
            (outcome, run),
        )
        self._db.commit()
        return int(cursor.rowcount or 0)

    def rows(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM LessonOutcome WHERE runId=? ORDER BY lessonId", (run_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def recent(self, lesson_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM LessonOutcome WHERE lessonId=? "
            "ORDER BY createdAt DESC LIMIT ?",
            (str(lesson_id), max(1, min(int(limit), 200))),
        ).fetchall()
        return [dict(row) for row in rows]

    def stats(self, lesson_id: str) -> LessonStats:
        return self._stats(lesson_id, self._rows_for_lesson(lesson_id))

    def stats_for(self, lesson_ids: Iterable[str]) -> dict[str, LessonStats]:
        return {
            str(lesson_id): self.stats(str(lesson_id))
            for lesson_id in lesson_ids
            if str(lesson_id)
        }

    def lesson_ids(self, *, limit: int = 500) -> list[str]:
        rows = self._db.execute(
            "SELECT DISTINCT lessonId FROM LessonOutcome ORDER BY lessonId LIMIT ?",
            (max(1, min(int(limit), 5000)),),
        ).fetchall()
        return [str(row["lessonId"]) for row in rows]

    def _rows_for_lesson(self, lesson_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM LessonOutcome WHERE lessonId=? AND outcome IN "
            "('success','failure') ORDER BY createdAt",
            (str(lesson_id),),
        ).fetchall()
        return [dict(row) for row in rows]

    def _stats(self, lesson_id: str, rows: list[dict[str, Any]]) -> LessonStats:
        injected = [row for row in rows if int(row.get("injected") or 0) == 1]
        control = [row for row in rows if int(row.get("injected") or 0) == 0]
        injected_successes = sum(1 for row in injected if row.get("outcome") == "success")
        control_successes = sum(1 for row in control if row.get("outcome") == "success")
        injected_rate = _rate(injected_successes, len(injected))
        control_rate = _rate(control_successes, len(control))
        injected_low, injected_high = wilson_interval(injected_successes, len(injected))
        control_low, control_high = wilson_interval(control_successes, len(control))
        if not injected:
            status, reason, lift = "unmeasured", "no injected observations", None
        elif len(injected) < 3 or len(control) < 3:
            status = "insufficient"
            reason = "at least 3 injected and 3 control observations are required"
            lift = None
        else:
            status, reason = "measured", "matched injected/control cohorts"
            lift = round(float(injected_rate) - float(control_rate), 6)
        return LessonStats(
            lessonId=str(lesson_id),
            injected=len(injected),
            injectedSuccesses=injected_successes,
            injectedRate=injected_rate,
            injectedCiLow=injected_low,
            injectedCiHigh=injected_high,
            control=len(control),
            controlSuccesses=control_successes,
            controlRate=control_rate,
            controlCiLow=control_low,
            controlCiHigh=control_high,
            lift=lift,
            status=status,
            reason=reason,
        )


def rank_lessons(
    lessons: Iterable[Mapping[str, Any]],
    stats: Mapping[str, LessonStats],
) -> list[dict[str, Any]]:
    """Rank eligible lessons by measured lift, then evidence, then input order.

    A lesson without a measured lift keeps its original relative position; it is
    never promoted on a guess. The sort is stable and deterministic.
    """
    items = [dict(lesson) for lesson in lessons]
    positive = {
        str(key): value for key, value in stats.items()
        if getattr(value, "status", "") == "measured"
        and getattr(value, "lift", None) is not None
        and float(value.lift) > 0.0
    }
    indexed = list(enumerate(items))
    indexed.sort(key=lambda item: (
        0 if str(item[1].get("id") or "") in positive else 1,
        -(
            float(positive[str(item[1].get("id") or "")].lift)
            if str(item[1].get("id") or "") in positive
            else 0.0
        ),
        item[0],
    ))
    return [item for _, item in indexed]


def retire_unhelpful(
    lesson_store: Any,
    outcome_store: LessonOutcomeStore,
    lesson_ids: Optional[Iterable[str]] = None,
    *,
    min_injected: int = 5,
    min_control: int = 5,
    max_lift: float = 0.0,
) -> list[dict[str, Any]]:
    """Mark adopted lessons retired when measured lift is not positive.

    This is a lifecycle action on an inert knowledge artifact. It never deletes
    the row, never changes authority and never enables a skill. A lesson with
    thin data is left untouched.
    """
    ids = list(lesson_ids) if lesson_ids is not None else outcome_store.lesson_ids()
    retired: list[dict[str, Any]] = []
    for lesson_id in ids:
        stats = outcome_store.stats(str(lesson_id))
        if stats.status != "measured":
            continue
        if stats.injected < max(1, int(min_injected)):
            continue
        if stats.control < max(1, int(min_control)):
            continue
        if stats.lift is None or stats.lift > float(max_lift):
            continue
        updater = getattr(lesson_store, "update_candidate", None)
        if not callable(updater):
            continue
        try:
            updater(str(lesson_id), status="retired")
        except Exception:  # noqa: BLE001 - one bad row never stops the sweep
            continue
        retired.append(stats.to_dict())
    return retired


__all__ = [
    "LessonOutcomeStore",
    "LessonStats",
    "OUTCOMES",
    "STATUSES",
    "new_feedback_id",
    "rank_lessons",
    "retire_unhelpful",
    "task_signature",
]
