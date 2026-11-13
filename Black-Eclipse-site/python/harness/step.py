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
    resolution: Any = None,
    fallback_build: Any = None,
    run_id: str = "",
    first_token_timeout_s: Optional[float] = None,
    max_run_tokens: Optional[int] = None,
    credential_pool: Any = None,
    usage_anchor_store: Any = None,
    anchor_id: str = "",
    history_chars: int = 0,
    gateway: Any = None,
) -> Any:
    """Invoke the model for one agent step.

    W1: when a `resolution` is supplied the call goes through the one
    `ModelGateway`/`ModelRuntime` path. The legacy retry path remains for tests
    and direct callers that have no resolution.

    W2.6: the provider cache marker is applied here, immediately before the
    request, so the state/message log keeps plain text and every attempt gets
    the same marker.
    """
    from .prompt_segments import apply_cache_markers  # noqa: PLC0415

    _provider = str(
        provider_id
        or getattr(getattr(resolution, "settings", None), "provider", "")
        or ""
    )
    messages = apply_cache_markers(list(messages or []), provider=_provider)
    if resolution is not None:
        from .config import flags as _flags  # noqa: PLC0415
        from .model_runtime.gateway import GatewayRequest, ModelGateway  # noqa: PLC0415

        request = GatewayRequest(
            model=model,
            messages=messages,
            timeout_s=timeout_s,
            finalizing=finalizing,
            emitter=emitter,
            resolution=resolution,
            run_id=run_id,
            step=step,
            task="agent",
            first_token_timeout_s=first_token_timeout_s,
            fallback_build=fallback_build,
            max_attempts=(policy or RetryPolicy.from_env()).attempts,
            max_run_tokens=max_run_tokens,
            credential_pool=credential_pool,
            usage_anchor_store=usage_anchor_store,
            anchor_id=anchor_id,
            history_chars=history_chars,
        )
        mode = _flags.get_flag("HARNESS_MODEL_GATEWAY")
        if mode == "off":
            pass  # fall through to the legacy path below
        else:
            active = gateway or ModelGateway()
            if mode == "shadow":
                # W1.1: record the plan only. The legacy call remains authoritative.
                await active.plan(request)
            else:
                result = await active.stream(request)
                return result.response

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
