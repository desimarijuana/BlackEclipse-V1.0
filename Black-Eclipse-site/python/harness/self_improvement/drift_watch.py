"""Bounded background drift watch.

The operator surfaces can read drift on demand, but a regression that only shows
up when someone opens the card is not monitored. This task reads the same
`detect_store_drift` signal for every configured scope on a cadence, publishes
`self_improvement.drift_detected` on a transition into `drift`, and never creates
a candidate or changes the harness. Read-only and best-effort.
"""

from __future__ import annotations

import asyncio
import logging
import os
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

    def _load_last(self) -> None:
        """Restore the last status per scope so a restart does not re-alert."""
        db = getattr(getattr(self.service, "store", None), "_db", None)
        if db is None:
            return
        try:
            db.execute(
                "CREATE TABLE IF NOT EXISTS DriftWatchState ("
                "scope TEXT PRIMARY KEY, status TEXT NOT NULL, updatedAt TEXT NOT NULL)"
            )
            rows = db.execute("SELECT scope, status FROM DriftWatchState").fetchall()
            self._last.update({str(row["scope"]): str(row["status"]) for row in rows})
        except Exception:  # noqa: BLE001 - a missing state table is a cold start
            self._last = {}

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
                await asyncio.sleep(self.interval_seconds)
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
            self._load_last()
            self._loaded = True
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
        return {"checked": len(scopes), "drifted": drifted}

    def health(self) -> dict[str, Any]:
        return {
            "enabled": self.interval_seconds > 0,
            "intervalSeconds": self.interval_seconds,
            "running": bool(self._task is not None and not self._task.done()),
            "last": dict(self._last),
        }


__all__ = ["DEFAULT_INTERVAL_SECONDS", "DriftWatcher"]
