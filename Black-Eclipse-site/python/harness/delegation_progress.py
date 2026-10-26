"""Live progress for a delegated child run.

A delegated child is a normal `execute_run` with its OWN run id, so its events
are published on that id and never reach the parent's SSE stream. This module
bridges them: it reads the child's own event queue, keeps a small running
snapshot, and re-emits ONE bounded `delegation.progress` event on the PARENT's
emitter, throttled. That is what lets the chat show parallel agents working.

What this module will NOT do:

* it never copies a child's raw event payloads (no tool arguments, no content);
* it never invents a progress fraction — `step`/`maxSteps` are the runtime's,
  and a surface with no known ceiling renders indeterminate;
* it never guesses a cost — an unknown price stays `None`, never `0`.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Optional

#: Minimum gap between snapshots for one child. A run can emit dozens of events
#: per second; the UI needs a readable row, not a flood.
SNAPSHOT_INTERVAL_S = 0.25

EmitFn = Callable[[str, dict[str, Any]], Awaitable[Any]]

_DEFAULT_REGISTRIES: Optional[tuple[Any, Any, Any, Any]] = None


def _default_registries() -> tuple[Any, Any, Any, Any]:
    """The process-wide provider/model/capability/pricing registries, built once.

    Lazily constructed so importing this module costs nothing on a run that does
    not delegate.
    """
    global _DEFAULT_REGISTRIES
    if _DEFAULT_REGISTRIES is None:
        from .model_runtime.registry import build_default_registries  # noqa: PLC0415

        _DEFAULT_REGISTRIES = build_default_registries()
    return _DEFAULT_REGISTRIES


def estimate_cost_usd(
    provider: Optional[str],
    model: Optional[str],
    prompt_tokens: int,
    completion_tokens: int,
) -> Optional[float]:
    """The declared price for the tokens used, or `None` when the price is unknown.

    Uses the SAME pricing registry the model runtime reports from. Unknown
    pricing is never rounded to zero — an unpriced model shows no cost.
    """
    if not model or (prompt_tokens <= 0 and completion_tokens <= 0):
        return None
    try:
        from .model_runtime.types import Usage  # noqa: PLC0415
        from .model_runtime.usage import CostTracker  # noqa: PLC0415

        _, models, _, pricing = _default_registries()
        info = models.get_model(f"{provider}/{model}") if provider else models.get_model(model)
        if info is None:
            return None
        estimate = CostTracker(pricing).estimate(
            info,
            Usage(input_tokens=prompt_tokens, output_tokens=completion_tokens),
        )
        if estimate is None:
            return None
        return round(float(estimate.total_cost), 6)
    except Exception:  # noqa: BLE001 - cost is advisory; never break a run
        return None


def _num(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not isinstance(value, int):
        value = int(value)
    return value if value >= 0 else None


def _activity_from(event_type: str, data: dict[str, Any]) -> Optional[str]:
    """The plain activity phrase a row shows, derived only from runtime fields."""
    if event_type == "tool.requested":
        detail = data.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()[:120]
        name = data.get("name")
        return f"Using {name}" if isinstance(name, str) and name else "Using a tool"
    if event_type == "model.requested":
        return "Thinking"
    if event_type == "model.completed":
        return "Writing the answer"
    if event_type == "retrieval.source_start":
        source = data.get("source")
        return f"Checking {source}" if isinstance(source, str) and source else "Checking sources"
    if event_type == "run.started":
        return "Starting"
    return None


class ChildProgressBridge:
    """One child run's progress, bridged to the parent's emitter.

    ``start()`` opens the child stream; ``finish()`` closes it and emits the
    terminal snapshot. Both are safe to call when no bus is attached (the bridge
    then does nothing).
    """

    def __init__(
        self,
        *,
        bus: Any,
        child_run_id: str,
        delegation_id: str,
        child_index: int,
        goal: str,
        approach: Optional[str] = None,
        agent_id: Optional[str] = None,
        provider: Optional[str],
        model: Optional[str],
        emit: EmitFn,
    ) -> None:
        self._bus = bus
        self._run_id = child_run_id
        self._emit = emit
        self._delegation_id = delegation_id
        self._child_index = child_index
        self._goal = goal[:200]
        self._approach = approach[:300] if approach else None
        self._agent_id = agent_id
        self._provider = provider
        self._model = model
        self._queue: Optional[asyncio.Queue[Any]] = None
        self._task: Optional[asyncio.Task[Any]] = None
        self._last_emit = 0.0
        self._started = False

        self.status = "running"
        self.activity: Optional[str] = None
        # Last distinct activities, oldest first — the timeline the popup shows.
        self.recent: list[str] = []
        self.step: Optional[int] = None
        self.max_steps: Optional[int] = None
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.tokens = 0
        self.reason: Optional[str] = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._bus is None or self._started:
            return
        self._started = True
        try:
            self._queue = self._bus.open_stream(self._run_id)
            self._task = asyncio.create_task(self._pump())
        except Exception:  # noqa: BLE001 - progress must never break the child
            self._queue = None
            self._task = None

    async def finish(
        self,
        status: str,
        *,
        tokens: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> None:
        self.status = status
        if reason:
            self.reason = reason[:200]
        if tokens is not None:
            self.tokens = max(self.tokens, max(0, tokens))
        if self._queue is not None and self._bus is not None:
            try:
                self._bus.close_stream(self._run_id, self._queue)
            except Exception:  # noqa: BLE001
                pass
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await self._emit_snapshot()

    async def _pump(self) -> None:
        queue = self._queue
        if queue is None:
            return
        try:
            while True:
                event = await queue.get()
                if event is None:  # the bus signalled this run finished
                    break
                self.observe(event)
                await self._emit_throttled()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a broken bridge must not break a run
            return

    # ── observation ──────────────────────────────────────────────────────────

    def observe(self, event: dict[str, Any]) -> None:
        """Fold one raw child event into the snapshot (bounded, content-free)."""
        event_type = event.get("type")
        data = event.get("data")
        if not isinstance(event_type, str) or not isinstance(data, dict):
            return

        if event_type == "run.started":
            self.max_steps = _num(data.get("maxSteps")) or self.max_steps
            provider = data.get("provider")
            if isinstance(provider, str) and provider:
                self._provider = provider
        elif event_type == "model.requested":
            self.step = _num(data.get("step")) or self.step
        elif event_type == "model.completed":
            self.step = _num(data.get("step")) or self.step
            prompt = _num(data.get("promptTokens")) or 0
            completion = _num(data.get("completionTokens")) or 0
            total = _num(data.get("totalTokens"))
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            self.tokens = max(self.tokens, self.prompt_tokens + self.completion_tokens)
            if total and total > prompt + completion:
                self.tokens = max(self.tokens, self.tokens + (total - prompt - completion))
        elif event_type == "tool.requested":
            self.step = _num(data.get("step")) or self.step
        elif event_type in ("run.completed", "run.failed", "run.cancelled"):
            self.status = (
                "completed" if event_type == "run.completed"
                else "failed" if event_type == "run.failed" else "cancelled"
            )

        activity = _activity_from(event_type, data)
        if activity and activity != self.activity:
            self.activity = activity
            if not self.recent or self.recent[-1] != activity:
                self.recent.append(activity)
                del self.recent[:-12]

    # ── emission ─────────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        return {
            "delegationId": self._delegation_id,
            "childIndex": self._child_index,
            "runId": self._run_id,
            "agentId": self._agent_id,
            "model": self._model,
            "goal": self._goal,
            **({"approach": self._approach} if self._approach else {}),
            "status": self.status,
            "activity": self.activity,
            "recent": self.recent,
            "step": self.step,
            "maxSteps": self.max_steps,
            "tokens": self.tokens,
            "costUsd": estimate_cost_usd(
                self._provider, self._model, self.prompt_tokens, self.completion_tokens,
            ),
            **({"reason": self.reason} if self.reason else {}),
        }

    async def _emit_throttled(self) -> None:
        now = time.monotonic()
        if now - self._last_emit < SNAPSHOT_INTERVAL_S:
            return
        self._last_emit = now
        await self._emit_snapshot()

    async def _emit_snapshot(self) -> None:
        try:
            await self._emit("delegation.progress", self.snapshot())
        except Exception:  # noqa: BLE001 - an event must never break a run
            pass


__all__ = [
    "SNAPSHOT_INTERVAL_S",
    "ChildProgressBridge",
    "estimate_cost_usd",
]
