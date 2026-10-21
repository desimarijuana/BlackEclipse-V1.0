"""Post-landing canary for an RSL promotion.

Pre-landing verification proves a candidate is better on a frozen suite. It
does not prove the running process still boots. This module closes that gap:

    apply -> restart -> health probe -> keep
                     \\-> failed -> rollback -> restart -> re-probe

Every side effect (restart, probe, rollback) is INJECTED. The runtime cannot
restart itself cleanly, so the front door / supervisor owns the restart seam.
When that seam is absent the result is recorded as `unverified` -- never as a
success. Nothing here promotes a change; rollback is the only automatic action.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..async_timeout import await_bounded
from ..persistence import now_iso

STATUSES: tuple[str, ...] = (
    "running",
    "healthy",
    "rolled_back",
    "rollback_failed",
    "restart_failed",
    "unverified",
)


@dataclass(frozen=True)
class PostLandingPolicy:
    """Bounded limits for one post-landing probe.

    `critical_tasks` is reserved for a follow-up that replays a tiny critical
    suite after the restart. P0 probes runtime health only; it never fabricates
    a benchmark result.
    """

    timeout_seconds: float = 120.0
    health_timeout_seconds: float = 5.0
    restart_timeout_seconds: float = 60.0
    critical_tasks: tuple[str, ...] = ()


def _new_id() -> str:
    return "postland_" + uuid.uuid4().hex[:16]


def _loads(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "runId": row["runId"],
        "activationId": row["activationId"],
        "rollbackId": row["rollbackId"],
        "status": row["status"],
        "reason": row["reason"],
        "evidence": _loads(row["evidenceJson"]),
        "startedAt": row["startedAt"],
        "finishedAt": row["finishedAt"],
        "createdAt": row["createdAt"],
    }


class PostLandingStore:
    """Bounded probe records on the ONE agent-memory database."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS HarnessPostLanding (
      id           TEXT PRIMARY KEY,
      runId        TEXT NOT NULL,
      activationId TEXT,
      rollbackId   TEXT NOT NULL,
      status       TEXT NOT NULL,
      reason       TEXT,
      evidenceJson TEXT,
      startedAt    TEXT NOT NULL,
      finishedAt   TEXT,
      createdAt    TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_post_landing_run
      ON HarnessPostLanding(runId, createdAt);
    """

    def __init__(self, store: Any) -> None:
        self._store = store
        self._db.executescript(self._SCHEMA)

    @property
    def _db(self):
        return self._store._db

    def start(
        self,
        *,
        run_id: str,
        rollback_id: str,
        activation_id: str = "",
    ) -> dict[str, Any]:
        record_id = _new_id()
        now = now_iso()
        self._db.execute(
            """INSERT INTO HarnessPostLanding
               (id, runId, activationId, rollbackId, status, reason,
                evidenceJson, startedAt, finishedAt, createdAt)
               VALUES (?, ?, ?, ?, 'running', NULL, '{}', ?, NULL, ?)""",
            (record_id, run_id, activation_id or None, rollback_id, now, now),
        )
        return {
            "id": record_id,
            "runId": run_id,
            "activationId": activation_id,
            "rollbackId": rollback_id,
            "status": "running",
            "reason": "",
            "evidence": {},
            "startedAt": now,
            "finishedAt": None,
            "createdAt": now,
        }

    def finish(
        self,
        record_id: str,
        *,
        status: str,
        reason: str = "",
        evidence: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if status not in STATUSES:
            status = "unverified"
        now = now_iso()
        self._db.execute(
            """UPDATE HarnessPostLanding
               SET status = ?, reason = ?, evidenceJson = ?, finishedAt = ?
               WHERE id = ?""",
            (status, reason or "", json.dumps(evidence or {}), now, record_id),
        )
        row = self._db.execute(
            "SELECT * FROM HarnessPostLanding WHERE id = ?", (record_id,),
        ).fetchone()
        return _row(row) if row is not None else {
            "id": record_id, "status": status, "reason": reason,
            "evidence": evidence or {}, "finishedAt": now,
        }

    def get(self, record_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM HarnessPostLanding WHERE id = ?", (record_id,),
        ).fetchone()
        return _row(row) if row is not None else None

    def list(self, *, run_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        bound = max(1, min(int(limit), 200))
        if run_id:
            rows = self._db.execute(
                "SELECT * FROM HarnessPostLanding WHERE runId = ? "
                "ORDER BY createdAt DESC LIMIT ?",
                (run_id, bound),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM HarnessPostLanding ORDER BY createdAt DESC LIMIT ?",
                (bound,),
            ).fetchall()
        return [_row(row) for row in rows]


def runtime_health(
    *, url: Optional[str] = None, timeout_seconds: float = 5.0,
) -> bool:
    """Probe the local runtime's `/health` endpoint.

    A missing endpoint, a non-200 response or a transport error is `False`.
    This is intentionally a process-level probe, not a quality claim.
    """
    import os

    base = url or os.environ.get("HARNESS_HEALTH_URL")
    if not base:
        runtime_url = str(os.environ.get("HARNESS_PY_URL") or "").rstrip("/")
        base = (
            f"{runtime_url}/health" if runtime_url
            else "http://127.0.0.1:8765/health"
        )
    try:
        with urllib.request.urlopen(base, timeout=max(0.5, float(timeout_seconds))) as res:
            return int(getattr(res, "status", 0) or 0) == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


async def _invoke(
    fn: Callable[[], Any],
    *,
    timeout_seconds: float,
) -> Any:
    """Run a sync or async callable off the event loop under the hard deadline."""
    if inspect.iscoroutinefunction(fn):
        return await await_bounded(fn(), timeout_seconds)
    result = await await_bounded(
        asyncio.to_thread(fn), timeout_seconds,
    )
    # An async callable object (not a coroutine function) returns an awaitable
    # from the thread; await it here under the same deadline.
    if inspect.isawaitable(result):
        return await await_bounded(result, timeout_seconds)
    return result


def _default_rollback(rollback_id: str) -> dict[str, Any]:
    from ..code import promotion  # noqa: PLC0415 - one-way import

    return promotion.rollback_promotion(rollback_id)


async def run_post_landing(
    *,
    store: Any,
    run_id: str,
    rollback_id: str,
    activation_id: str = "",
    restart: Optional[Callable[[], Any]] = None,
    verify: Optional[Callable[[], Any]] = None,
    rollback: Optional[Callable[[str], Any]] = None,
    policy: Optional[PostLandingPolicy] = None,
    restart_already_done: bool = False,
) -> dict[str, Any]:
    """Restart, probe and (only on failure) roll a promoted change back.

    `restart_already_done` is the front-door protocol: the supervisor has
    already restarted the runtime, so this call probes only (and rolls back on
    failure). Without either a restart callable or that flag the result is
    `unverified` -- never a successful landing.
    """
    settings = policy or PostLandingPolicy()
    records = PostLandingStore(store)
    record = records.start(
        run_id=run_id, rollback_id=rollback_id, activation_id=activation_id,
    )
    evidence: dict[str, Any] = {
        "restart": "not_attempted",
        "health": None,
        "rollback": "not_attempted",
        "secondHealth": None,
    }

    if restart is None and not restart_already_done:
        return records.finish(
            record["id"], status="unverified", reason="NO_RESTART_SEAM",
            evidence=evidence,
        )

    probe = verify or (lambda: runtime_health(
        timeout_seconds=settings.health_timeout_seconds,
    ))
    undo = rollback or _default_rollback

    if restart_already_done:
        evidence["restart"] = "already_done"
    else:
        try:
            await _invoke(
                restart, timeout_seconds=settings.restart_timeout_seconds,
            )
            evidence["restart"] = "ok"
        except Exception as exc:  # noqa: BLE001 - a failed restart is a recorded refusal
            evidence["restart"] = f"error:{type(exc).__name__}"
            # The new files are on disk but not running. Put the previous files
            # back so a later restart cannot silently load a change we could not
            # prove. The failure itself remains visible.
            try:
                await _invoke(
                    lambda: undo(rollback_id),
                    timeout_seconds=settings.restart_timeout_seconds,
                )
                evidence["rollback"] = "ok"
                reason = "The runtime did not restart; the previous files were put back."
            except Exception as rollback_exc:  # noqa: BLE001 - recorded below
                evidence["rollback"] = f"error:{type(rollback_exc).__name__}"
                reason = (
                    "The runtime did not restart and the previous files could not "
                    "be put back."
                )
            return records.finish(
                record["id"], status="restart_failed",
                reason=reason, evidence=evidence,
            )

    try:
        healthy = bool(await _invoke(
            probe, timeout_seconds=settings.timeout_seconds,
        ))
        evidence["health"] = healthy
    except asyncio.TimeoutError:
        evidence["health"] = "timeout"
        healthy = False
    except Exception as exc:  # noqa: BLE001 - a broken probe is a failure
        evidence["health"] = f"error:{type(exc).__name__}"
        healthy = False

    if healthy:
        return records.finish(
            record["id"], status="healthy", reason="", evidence=evidence,
        )

    # The new code is live but unhealthy. Put the previous files back, restart
    # again and re-probe. Nothing is re-promoted; rollback is the only action.
    try:
        await _invoke(
            lambda: undo(rollback_id),
            timeout_seconds=settings.restart_timeout_seconds,
        )
        evidence["rollback"] = "ok"
    except Exception as exc:  # noqa: BLE001 - a failed rollback must be visible
        evidence["rollback"] = f"error:{type(exc).__name__}"
        return records.finish(
            record["id"], status="rollback_failed",
            reason=f"The unhealthy change could not be put back: {type(exc).__name__}",
            evidence=evidence,
        )

    if restart is None:
        evidence["secondRestart"] = "required"
        return records.finish(
            record["id"], status="rolled_back",
            reason="Files restored; restart the runtime to load the previous version.",
            evidence=evidence,
        )

    try:
        await _invoke(
            restart, timeout_seconds=settings.restart_timeout_seconds,
        )
        evidence["secondRestart"] = "ok"
    except Exception as exc:  # noqa: BLE001 - the old code is on disk; report it
        evidence["secondRestart"] = f"error:{type(exc).__name__}"
        return records.finish(
            record["id"], status="rolled_back",
            reason="Files restored, but the runtime did not restart again.",
            evidence=evidence,
        )

    try:
        recovered = bool(await _invoke(
            probe, timeout_seconds=settings.timeout_seconds,
        ))
        evidence["secondHealth"] = recovered
    except asyncio.TimeoutError:
        evidence["secondHealth"] = "timeout"
        recovered = False
    except Exception as exc:  # noqa: BLE001 - a broken probe is not a success
        evidence["secondHealth"] = f"error:{type(exc).__name__}"
        recovered = False

    return records.finish(
        record["id"],
        status="rolled_back" if recovered else "unverified",
        reason=(
            "The change was put back after a failed health probe."
            if recovered else
            "The change was put back, but the restored runtime did not report healthy."
        ),
        evidence=evidence,
    )


__all__ = [
    "PostLandingPolicy",
    "PostLandingStore",
    "STATUSES",
    "run_post_landing",
    "runtime_health",
]
