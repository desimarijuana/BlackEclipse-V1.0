"""The ONE model-call path for an agent step (Round 5 / C1).

`graph.agent_node` used to call `model_stream.ainvoke_streaming` directly. That
meant the runtime's retry/backoff/circuit-breaker was bypassed on the only path
that matters, and the per-call timeout was the run timeout.

This module owns the call instead:

  * one `RetryPolicy` (operator-tunable, test-injectable);
  * one hard per-call timeout, clamped by the run deadline;
  * `model.retry` is a durable event, so a retry is visible in the trace;
  * a retry is refused once any text has already streamed (retrying would
    duplicate the user-visible answer).

It deliberately does NOT classify or wrap the final exception: the graph's
existing handling of context overflow / provider failure stays authoritative.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from .model_runtime import ErrorClass, classify_exception
from .model_stream import ainvoke_streaming
from .retry_policy import RetryPolicy, RunDeadline, is_retryable, retry_async

# A single model call may never occupy the whole run budget by default. A
# provider that streams no bytes for this long is treated as dead; the run
# deadline still governs the total.
MODEL_CALL_TIMEOUT_CEILING_S = 300.0


class _CountingEmitter:
    """Forwards to the real emitter and counts streamed text deltas."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.deltas = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def emit(self, event_type: str, data: Optional[dict[str, Any]] = None) -> Any:
        return await self._inner.emit(event_type, data)

    def emit_sync(self, event_type: str, data: Optional[dict[str, Any]] = None) -> None:
        self._inner.emit_sync(event_type, data)

    def emit_transient(self, event_type: str, data: Optional[dict[str, Any]] = None) -> None:
        if event_type == "model.delta" and isinstance(data, dict):
            if str(data.get("text") or ""):
                self.deltas += 1
        self._inner.emit_transient(event_type, data)


async def invoke_model_step(
    model: Any,
    messages: list[Any],
    *,
    timeout_s: float,
    emitter: Any,
    finalizing: bool,
    deadline: Optional[RunDeadline] = None,
    policy: Optional[RetryPolicy] = None,
    step: int = 0,
    provider_id: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Any:
    """Invoke the model for one agent step, with the shared retry policy."""
    retry_policy = policy or RetryPolicy.from_env()
    counted = _CountingEmitter(emitter)

    async def _attempt() -> Any:
        call_timeout = float(timeout_s)
        if deadline is not None:
            remaining = deadline.remaining()
            if remaining <= 0.0:
                raise asyncio.TimeoutError()
            call_timeout = min(call_timeout, remaining)
        return await ainvoke_streaming(
            model, messages, call_timeout, counted, finalizing,
        )

    async def _on_retry(attempt: int, delay: float, exc: BaseException) -> None:
        error = classify_exception(
            exc, provider_id=provider_id, model_id=model_id,
        )
        await emitter.emit("model.retry", {
            "step": step,
            "attempt": attempt + 1,
            "maxAttempts": retry_policy.attempts,
            "delayMs": int(round(delay * 1000.0)),
            "errorClass": error.error_class.value,
            "statusCode": error.status_code,
        })

    def _retryable(exc: BaseException) -> bool:
        # Once any text has been shown to the user, a retry would duplicate it.
        if counted.deltas > 0:
            return False
        return is_retryable(exc)

    return await retry_async(
        _attempt,
        retry_policy,
        on_retry=_on_retry,
        deadline=deadline,
        retryable=_retryable,
    )


def effective_call_timeout(run_timeout_s: float) -> float:
    """The per-call ceiling: never the whole run, never zero."""
    return max(1.0, min(float(run_timeout_s), MODEL_CALL_TIMEOUT_CEILING_S))


__all__ = [
    "MODEL_CALL_TIMEOUT_CEILING_S",
    "effective_call_timeout",
    "invoke_model_step",
]
