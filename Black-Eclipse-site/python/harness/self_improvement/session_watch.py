"""The unattended RSL session watcher.

The drift watch already proves that a background task inside the runtime can
carry a bounded cadence. This is the same pattern for the self-improvement
loop: on a cadence, run ONE measured surface session and stage its winner as an
inert candidate.

It is OFF by default (`HARNESS_RSL_SESSION_SECONDS=0`). When it is on it is
still bounded three ways: the surface budget (a separate daily allowance), the
session itself (a fixed number of variants on one split), and the fact that a
session only ever STAGES a candidate - the operator queues, verifies and
activates it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any, Optional

log = logging.getLogger("harness.self_improvement.session_watch")

DEFAULT_INTERVAL_SECONDS = 0  # off by default


def _interval_seconds() -> int:
    raw = os.getenv("HARNESS_RSL_SESSION_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL_SECONDS
    return max(0, value)


class SessionWatcher:
    """One background task; runs bounded surface sessions on a cadence."""

    def __init__(self, service: Any = None, *, interval_seconds: Optional[int] = None) -> None:
        self.service = service
        self.interval_seconds = (
            _interval_seconds() if interval_seconds is None
            else max(0, int(interval_seconds))
        )
        self._task: Optional[asyncio.Task[Any]] = None
        self._stopping = False
        self._last: dict[str, Any] = {}

    async def start(self) -> None:
        if self.interval_seconds <= 0:
            return
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="rsl-session-watch")

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._task = None

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await asyncio.sleep(
                    self.interval_seconds + random.uniform(0, self.interval_seconds * 0.1)
                )
            except asyncio.CancelledError:
                return
            if self._stopping:
                return
            try:
                await self.check()
            except Exception:  # noqa: BLE001 - one session never kills the watch
                log.warning("[harness-py] the RSL session failed", exc_info=True)

    async def check(self) -> dict[str, Any]:
        """Run one session now, if the surface budget allows it."""
        loop = getattr(self.service, "_rsl_loop", None)
        if loop is None:
            self._last = {"skipped": "loop_unavailable"}
            return self._last
        budget_ok = getattr(loop, "surface_budget_ok", None)
        if callable(budget_ok) and not budget_ok():
            self._last = {"skipped": "budget"}
            return self._last
        run = getattr(loop, "run_surface_session", None)
        if not callable(run):
            self._last = {"skipped": "session_unavailable"}
            return self._last
        lab = await run()
        self._last = {
            "winner": lab.get("winner"),
            "staged": bool((lab.get("staged") or {}).get("staged")),
            "variants": len(lab.get("variants") or []),
        }
        if self._last["staged"]:
            log.warning(
                "[harness-py] an RSL session staged a surface candidate: %s",
                self._last.get("winner"),
            )
        return self._last

    def health(self) -> dict[str, Any]:
        return {
            "enabled": self.interval_seconds > 0,
            "intervalSeconds": self.interval_seconds,
            "running": bool(self._task is not None and not self._task.done()),
            "last": dict(self._last),
        }


__all__ = ["DEFAULT_INTERVAL_SECONDS", "SessionWatcher"]
