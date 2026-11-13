"""Session-scoped loops and heartbeats (W4).

A loop is a HEARTBEAT, not a scheduler: it rides the automation engine's existing
tick, starts at most one session run at a time, never fires mid-run, defers to
user activity, coalesces a missed tick to one, and suppresses an unchanged reply.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import hashlib
import logging
import os
import uuid
from typing import Any, Optional

from ..config import flags
from ..persistence import now_iso
from ..schemas import ModelSettings, RunInput, RunRequest
from .goal_runtime import GoalError, _model_snapshot, loop_mode
from .model import LOOP_KINDS, LOOP_MODES
from .store import GoalStore

log = logging.getLogger("harness.goals.loop_runtime")

_SELF_PACED = (60, 120, 240, 480, 900)


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _iso(moment: _dt.datetime) -> str:
    return moment.astimezone(_dt.timezone.utc).isoformat()


def _plus(seconds: float, *, start: Optional[_dt.datetime] = None) -> str:
    return _iso((start or _now()) + _dt.timedelta(seconds=max(1, int(seconds))))


def _digest(text: str) -> str:
    normalized = " ".join(str(text or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _settings_for(loop: Any) -> ModelSettings:
    provider = str(getattr(loop, "model_provider", "") or "") \
        or os.environ.get("HARNESS_TASK_PROVIDER") \
        or os.environ.get("HARNESS_JOB_PROVIDER", "ollama")
    model = str(getattr(loop, "model_name", "") or "") \
        or os.environ.get("HARNESS_TASK_MODEL") \
        or os.environ.get("HARNESS_JOB_MODEL", "llama3.1")
    base_url = str(getattr(loop, "model_base_url", "") or "") \
        or os.environ.get("HARNESS_TASK_BASE_URL") \
        or os.environ.get("HARNESS_JOB_BASE_URL", "")
    return ModelSettings(
        provider=provider, model=model, base_url=base_url or None,
        api_key=os.environ.get("HARNESS_TASK_API_KEY")
        or os.environ.get("HARNESS_JOB_API_KEY"),
    )


class LoopRuntime:
    def __init__(self, service: Any, store: Optional[GoalStore] = None) -> None:
        self.service = service
        self.store = store or GoalStore(service.store)
        self._inflight: set[str] = set()

    # ── Creation / control ───────────────────────────────────────────────────
    def create(
        self, session_id: str, *, kind: str, prompt: str,
        interval_seconds: Optional[int] = None, mode: str = "fixed",
        max_ticks: Optional[int] = None, model: Optional[Any] = None,
        workspace_id: Optional[str] = None,
    ) -> Any:
        if not session_id:
            raise GoalError("MISSING_SESSION", "a loop needs a session")
        if kind not in LOOP_KINDS:
            raise GoalError("INVALID_LOOP_KIND", f"unknown loop kind {kind!r}")
        if mode not in LOOP_MODES:
            raise GoalError("INVALID_LOOP_MODE", f"unknown loop mode {mode!r}")
        text = str(prompt or "").strip()
        if not text:
            raise GoalError("MISSING_PROMPT", "a loop needs a prompt")
        minimum = flags.get_int("HARNESS_LOOP_MIN_INTERVAL_S")
        interval = int(interval_seconds or minimum)
        interval = max(minimum, min(interval, 86_400))
        cap = int(max_ticks or flags.get_int("HARNESS_LOOP_MAX_TICKS"))
        cap = max(1, min(cap, 1_000))
        snapshot = _model_snapshot(model)
        loop = self.store.create_loop(
            session_id, kind=kind, prompt=text, mode=mode,
            interval_seconds=interval, next_tick_at=_plus(interval),
            max_ticks=cap, model_provider=snapshot["provider"],
            model_name=snapshot["model"], model_base_url=snapshot["baseUrl"],
            workspace_id=workspace_id,
        )
        self._emit("loop.created", {
            "loopId": loop.id, "sessionId": session_id, "kind": kind,
            "mode": mode, "intervalSeconds": interval,
        })
        return loop

    def list(self, *, session_id: Optional[str] = None, status: Optional[str] = None) -> list[Any]:
        return self.store.list_loops(session_id=session_id, status=status)

    def get(self, loop_id: str) -> Any:
        loop = self.store.get_loop(loop_id)
        if loop is None:
            raise GoalError("LOOP_NOT_FOUND", f"no loop {loop_id!r}")
        return loop

    def pause(self, loop_id: str, reason: str = "operator") -> Any:
        self.get(loop_id)
        self.store.update_loop_fields(loop_id, {"status": "paused"})
        self._emit("loop.paused", {"loopId": loop_id, "reason": reason})
        return self.store.get_loop(loop_id)

    def resume(self, loop_id: str) -> Any:
        loop = self.get(loop_id)
        if loop.status in ("cancelled", "completed"):
            raise GoalError("LOOP_TERMINAL", f"loop is {loop.status}")
        self.store.update_loop_fields(loop_id, {
            "status": "active", "nextTickAt": _plus(loop.interval_seconds),
        })
        return self.store.get_loop(loop_id)

    def cancel(self, loop_id: str) -> Any:
        loop = self.get(loop_id)
        self.store.update_loop_fields(loop_id, {"status": "cancelled"})
        if loop.last_run_id:
            try:
                self.service.cancel(loop.last_run_id)
            except Exception:  # noqa: BLE001 - cooperative cancellation
                pass
        self._emit("loop.cancelled", {"loopId": loop_id})
        return self.store.get_loop(loop_id)

    def cancel_for_session(self, session_id: str) -> int:
        return self.store.cancel_loops_for_session(session_id)

    # ── Tick ─────────────────────────────────────────────────────────────────
    async def tick(self, now: Optional[_dt.datetime] = None) -> dict[str, int]:
        moment = now or _now()
        report = {"due": 0, "started": 0, "deferred": 0, "completed": 0}
        # `shadow` records goal verdicts but starts no autonomous work; loops are
        # autonomous work, so they require the live mode.
        if loop_mode() != "on":
            return report
        loops = self.store.due_loops(_iso(moment), limit=8)
        report["due"] = len(loops)
        for loop in loops:
            if loop.status != "active":
                continue
            if loop.used_ticks >= loop.max_ticks:
                self.store.update_loop_fields(loop.id, {"status": "completed"})
                self._emit("loop.completed", {"loopId": loop.id, "reason": "max ticks"})
                report["completed"] += 1
                continue
            if loop.id in self._inflight or self._session_busy(loop):
                self._defer(loop, min(loop.interval_seconds, 60), moment)
                report["deferred"] += 1
                continue
            if loop.kind == "heartbeat" and self._user_active(loop):
                self._defer(loop, min(loop.interval_seconds, 60), moment)
                report["deferred"] += 1
                continue
            self._dispatch(loop, moment)
            report["started"] += 1
        return report

    def _session_busy(self, loop: Any) -> bool:
        try:
            run_ids = self.service.store.session_runs(loop.session_id)
        except Exception:  # noqa: BLE001 - a missing session is not busy
            return False
        for run_id in run_ids:
            try:
                if self.service.is_active(run_id):
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def _user_active(self, loop: Any) -> bool:
        """A heartbeat defers when the newest session run is not its own."""
        try:
            run_ids = self.service.store.session_runs(loop.session_id)
        except Exception:  # noqa: BLE001
            return False
        if not run_ids:
            return False
        latest = run_ids[-1]
        if loop.last_run_id and latest == loop.last_run_id:
            return False
        if not loop.last_tick_at:
            return False
        try:
            run = self.service.store.get_run(latest)
        except Exception:  # noqa: BLE001
            return False
        created = str((run or {}).get("createdAt") or "")
        return bool(created and created > loop.last_tick_at)

    def _defer(self, loop: Any, seconds: float, moment: _dt.datetime) -> None:
        self.store.update_loop_fields(loop.id, {"nextTickAt": _plus(seconds, start=moment)})
        self._emit("loop.tick", {"loopId": loop.id, "action": "deferred"})

    def _dispatch(self, loop: Any, moment: _dt.datetime) -> None:
        tick = loop.used_ticks + 1
        fixed_next = _plus(loop.interval_seconds, start=moment)
        try:
            task = asyncio.create_task(self._run(loop, tick))
        except RuntimeError:  # no asyncio loop (a synchronous test): run inline is unsafe
            log.warning("loop %s could not be dispatched: no running loop", loop.id)
            return
        self._inflight.add(loop.id)
        task.add_done_callback(lambda _t, loop_id=loop.id: self._inflight.discard(loop_id))
        self.store.update_loop_fields(loop.id, {
            "usedTicks": tick, "lastTickAt": _iso(moment),
            # A fixed loop schedules its next tick now; a self-paced loop adjusts
            # after the reply digest is known.
            "nextTickAt": fixed_next if loop.mode == "fixed" else _plus(60, start=moment),
        })
        self._emit("loop.tick", {"loopId": loop.id, "tick": tick, "action": "started"})

    async def _run(self, loop: Any, tick: int) -> None:
        run_id = f"loop_{loop.id}_{tick}_{uuid.uuid4().hex[:6]}"
        request = RunRequest(
            runId=run_id,
            input=RunInput(
                query=loop.prompt,
                context={
                    "source": "autonomy-loop", "loopId": loop.id,
                    "loopKind": loop.kind, "tick": tick,
                },
            ),
            modelSettings=_settings_for(loop),
            sessionId=loop.session_id,
            workspaceId=loop.workspace_id,
            callbackBaseUrl=os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1"),
            callbackToken=os.environ.get("HARNESS_CALLBACK_TOKEN") or None,
        )
        try:
            result = await self.service.run(request)
            output = str(getattr(result, "output", "") or "")
            status = str(getattr(result, "status", "") or "")
        except Exception as exc:  # noqa: BLE001 - a failed tick is reported, not retried
            log.warning("loop %s run failed", loop.id, exc_info=True)
            self.store.update_loop_fields(loop.id, {
                "lastRunId": run_id, "lastDigest": None,
                "nextTickAt": self._next_after(loop, loop.no_change_count),
            })
            self._emit("loop.tick", {"loopId": loop.id, "action": "failed",
                                     "error": str(exc)[:500]})
            return

        digest = _digest(output if status == "completed" else f"{status}:{output}")
        if digest == loop.last_digest:
            no_change = loop.no_change_count + 1
            self._emit("loop.no_change", {
                "loopId": loop.id, "digest": digest, "runId": run_id,
            })
            maximum = flags.get_int("HARNESS_LOOP_MAX_NO_CHANGE")
            if no_change >= maximum:
                self.store.update_loop_fields(loop.id, {
                    "lastRunId": run_id, "noChangeCount": no_change,
                    "lastDigest": digest, "status": "paused",
                })
                self._emit("loop.paused", {"loopId": loop.id, "reason": "no change"})
                return
        else:
            no_change = 0
            self.store.update_loop_fields(loop.id, {"lastDigest": digest})
            self._emit("loop.delivered", {
                "loopId": loop.id, "digest": digest, "runId": run_id,
            })
        self.store.update_loop_fields(loop.id, {
            "lastRunId": run_id, "noChangeCount": no_change,
            "nextTickAt": self._next_after(loop, no_change),
        })

    @staticmethod
    def _next_after(loop: Any, no_change: int) -> str:
        if loop.mode == "fixed":
            return _plus(loop.interval_seconds)
        ladder = _SELF_PACED[min(max(0, no_change), len(_SELF_PACED) - 1)]
        return _plus(min(ladder, loop.interval_seconds) if loop.interval_seconds else ladder)

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        bus = getattr(self.service, "bus", None)
        if bus is None:
            return
        try:
            bus.publish({"type": event_type, "at": now_iso(), "data": data})
        except Exception:  # noqa: BLE001
            pass


__all__ = ["LoopRuntime"]
