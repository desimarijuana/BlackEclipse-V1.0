"""Bounded background drift watch.

The operator surfaces can read drift on demand, but a regression that only shows
up when someone opens the card is not monitored. This task reads the same
`detect_store_drift` signal for every configured scope on a cadence, publishes
`self_improvement.drift_detected` on a transition into `drift`, and never creates
a candidate or changes the harness. Read-only and best-effort.

One opt-in exception: with `HARNESS_RSL_DRIFT_AUTOCANDIDATE=on` a NEW drift
transition also materializes the SAME inert candidate the operator route
creates. The candidate carries no target and no operations - it is evidence
that enters the existing propose -> verify -> land flow; it never lands,
never activates and never bypasses the operator.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any, Optional

from ..event_system.emit import publish_event

log = logging.getLogger("harness.self_improvement.drift_watch")

DEFAULT_INTERVAL_SECONDS = 300


def _interval_seconds() -> int:
    raw = os.getenv("HARNESS_DRIFT_WATCH_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL_SECONDS
    return max(0, value)


def _autocandidate_enabled() -> bool:
    """Whether a NEW drift transition may open an inert candidate (off by default)."""
    raw = str(os.getenv("HARNESS_RSL_DRIFT_AUTOCANDIDATE", "") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


class DriftWatcher:
    """One background task; publishes only transitions into drift."""

    def __init__(self, service: Any = None, *, interval_seconds: Optional[int] = None) -> None:
        self.service = service
        self.interval_seconds = (
            _interval_seconds() if interval_seconds is None else max(0, int(interval_seconds))
        )
        self._task: Optional[asyncio.Task[Any]] = None
        self._stopping = False
        self._loaded = False
        self._last: dict[str, str] = {}

    async def start(self) -> None:
        if self.interval_seconds <= 0:
            return
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="drift-watch")

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._task = None

    def _load_last(self) -> bool:
        """Restore the last status per scope so a restart does not re-alert."""
        db = getattr(getattr(self.service, "store", None), "_db", None)
        if db is None:
            return False
        try:
            db.execute(
                "CREATE TABLE IF NOT EXISTS DriftWatchState ("
                "scope TEXT PRIMARY KEY, status TEXT NOT NULL, updatedAt TEXT NOT NULL)"
            )
            # A reset database (no terminal runs) must not inherit an old
            # episode's "already alerted" state.
            remaining = db.execute(
                "SELECT COUNT(*) AS n FROM HarnessRun "
                "WHERE status IN ('completed','failed','error','cancelled')"
            ).fetchone()
            if remaining is None or int(remaining["n"]) == 0:
                db.execute("DELETE FROM DriftWatchState")
                db.commit()
                self._last = {}
                return True
            rows = db.execute("SELECT scope, status FROM DriftWatchState").fetchall()
            self._last.update({str(row["scope"]): str(row["status"]) for row in rows})
        except Exception:  # noqa: BLE001 - a missing state table is a cold start
            self._last = {}
        return False

    def _prune(self, scopes: list[str]) -> None:
        """Drop state for scopes that no longer exist (bounded retention)."""
        db = getattr(getattr(self.service, "store", None), "_db", None)
        if db is None or not scopes:
            return
        try:
            placeholders = ",".join("?" for _ in scopes)
            db.execute(
                f"DELETE FROM DriftWatchState WHERE scope NOT IN ({placeholders})",
                scopes,
            )
            db.commit()
        except Exception:  # noqa: BLE001 - retention is best-effort
            pass

    def _save_last(self, scope: str, status: str) -> None:
        db = getattr(getattr(self.service, "store", None), "_db", None)
        if db is None:
            return
        try:
            db.execute(
                "INSERT OR REPLACE INTO DriftWatchState (scope, status, updatedAt) "
                "VALUES (?, ?, ?)",
                (scope, status, datetime.now(timezone.utc).isoformat()),
            )
            db.commit()
        except Exception:  # noqa: BLE001 - persistence is best-effort
            pass

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await asyncio.sleep(self.interval_seconds + random.uniform(0, self.interval_seconds * 0.1))
            except asyncio.CancelledError:
                return
            if self._stopping:
                return
            try:
                await self.check()
            except Exception:  # noqa: BLE001 - one check never kills the watch
                log.warning("drift watch check failed", exc_info=True)

    async def check(self) -> dict[str, Any]:
        """Read every configured scope once and publish new drift transitions."""
        store = getattr(self.service, "store", None)
        if store is None:
            return {"checked": 0, "drifted": []}
        if not self._loaded:
            empty = self._load_last()
            self._loaded = True
            if empty:
                return {"checked": 0, "drifted": []}
        from ..agents import AGENT_PRESETS  # noqa: PLC0415
        from .drift import DRIFT, detect_store_drift  # noqa: PLC0415

        scopes = ["global", *sorted(AGENT_PRESETS.keys())]
        drifted: list[dict[str, Any]] = []
        for scope in scopes:
            signal = await asyncio.to_thread(
                detect_store_drift,
                store,
                scope=None if scope == "global" else scope,
            )
            status = str(signal.get("status") or "unmeasured")
            previous = self._last.get(scope)
            self._last[scope] = status
            self._save_last(scope, status)
            if status == DRIFT and previous != DRIFT:
                drifted.append(signal)
                publish_event(
                    "self_improvement.drift_detected",
                    {
                        "scope": scope,
                        "drop": signal.get("drop"),
                        "current": signal.get("current"),
                        "baseline": signal.get("baseline"),
                    },
                    source="self_improvement",
                )
                log.warning(
                    "[harness-py] drift detected for %s: drop=%s",
                    scope, signal.get("drop"),
                )
                if _autocandidate_enabled():
                    self._open_candidate(store, signal)
        self._prune(scopes)
        return {"checked": len(scopes), "drifted": drifted}

    def _open_candidate(self, store: Any, signal: dict[str, Any]) -> dict[str, Any]:
        """Open the SAME inert candidate the operator route would open.

        The candidate is evidence with no target and no operations; it enters
        the existing propose -> verify -> land flow and lands nothing by
        itself. Failures are recorded, never raised: a watch must not die.
        """
        try:
            from .drift import record_drift_candidate  # noqa: PLC0415

            recorded = record_drift_candidate(store, signal)
            if recorded.get("created"):
                publish_event(
                    "self_improvement.drift_candidate_created",
                    {
                        "candidateId": (recorded.get("candidate") or {}).get("id"),
                        "scope": signal.get("scope"),
                        "anchor": signal.get("anchor"),
                        "drop": signal.get("drop"),
                        "source": "drift-watch",
                    },
                    source="self_improvement",
                )
                log.warning(
                    "[harness-py] drift candidate opened for %s",
                    signal.get("scope"),
                )
            return recorded
        except Exception as exc:  # noqa: BLE001 - a failed candidate never kills the watch
            log.warning("[harness-py] drift candidate failed", exc_info=True)
            return {"created": False, "reason": f"error:{type(exc).__name__}"}

    def health(self) -> dict[str, Any]:
        return {
            "enabled": self.interval_seconds > 0,
            "intervalSeconds": self.interval_seconds,
            "running": bool(self._task is not None and not self._task.done()),
            "autoCandidate": _autocandidate_enabled(),
            "last": dict(self._last),
        }


__all__ = ["DEFAULT_INTERVAL_SECONDS", "DriftWatcher"]
