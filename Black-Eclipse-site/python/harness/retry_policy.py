"""One retry policy for the whole harness (Round 5 / C1).

Before this module, retry semantics were spread across `ModelRuntime.invoke`
(which the agent loop did not use), `recovery/hotpath.py` (read-only tools), the
Fabric worker, and the graph's own ad-hoc branches. This module is the ONE
policy shape; callers pass it in, so a test can make retries instant.

Rules:
  * never retry `asyncio.CancelledError` (the run was cancelled);
  * never retry a non-retryable provider class (auth, bad request, ...);
  * never retry when the run deadline would be crossed by the wait;
  * honor a provider's `Retry-After` when it supplies one.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, TypeVar

from .model_runtime import ErrorClass, classify_exception

T = TypeVar("T")

# The classes worth a second attempt on the SAME model. Context overflow is
# excluded on purpose: the caller must shrink context, not repeat the request.
RETRYABLE_CLASSES = frozenset({
    ErrorClass.RATE_LIMIT,
    ErrorClass.TIMEOUT,
    ErrorClass.NETWORK_ERROR,
    ErrorClass.SERVER_ERROR,
    ErrorClass.UNKNOWN_ERROR,
})


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class RetryPolicy:
    """A bounded, jittered exponential retry schedule.

    `attempts` counts the FIRST try, so `attempts=3` means up to two retries.
    """

    attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 10.0
    max_elapsed_s: float = 90.0
    jitter: bool = True

    @classmethod
    def from_env(cls) -> "RetryPolicy":
        """The operator-tunable model policy (safe defaults, hard caps)."""
        attempts = max(1, min(_env_int("HARNESS_MODEL_ATTEMPTS", 3), 10))
        return cls(
            attempts=attempts,
            base_delay_s=max(0.0, min(_env_float("HARNESS_MODEL_RETRY_BASE_S", 1.0), 30.0)),
            max_delay_s=max(0.0, min(_env_float("HARNESS_MODEL_RETRY_MAX_S", 10.0), 120.0)),
            max_elapsed_s=max(0.0, min(_env_float("HARNESS_MODEL_RETRY_BUDGET_S", 90.0), 600.0)),
        )

    def delay(self, attempt: int) -> float:
        """Seconds to wait after the `attempt`-th failure (0-based)."""
        window = min(self.max_delay_s, self.base_delay_s * (2 ** max(0, attempt)))
        return random.uniform(0.0, window) if self.jitter else window


@dataclass
class RunDeadline:
    """The wall clock for ONE run, independent of any single model call."""

    seconds: float
    _expires_at: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._expires_at = time.monotonic() + max(0.0, float(self.seconds))

    def remaining(self) -> float:
        return max(0.0, self._expires_at - time.monotonic())

    def expired(self) -> bool:
        return self.remaining() <= 0.0


def retry_after_seconds(exc: BaseException) -> Optional[float]:
    """The provider's own `Retry-After`, when it carries one (bounded)."""
    for attr in ("retry_after", "retry_after_s", "retry_after_seconds"):
        value = getattr(exc, attr, None)
        if isinstance(value, (int, float)) and value >= 0:
            return min(float(value), 60.0)
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        try:
            raw = headers.get("retry-after") or headers.get("Retry-After")
        except Exception:  # noqa: BLE001 - a foreign headers object
            raw = None
        if raw is not None:
            try:
                return min(float(str(raw).strip()), 60.0)
            except (TypeError, ValueError):
                return None
    return None


def is_retryable(exc: BaseException) -> bool:
    """Whether a failure is worth retrying on the same model."""
    if isinstance(exc, asyncio.CancelledError):
        return False
    error = classify_exception(exc)
    return bool(error.retryable) and error.error_class in RETRYABLE_CLASSES


async def retry_async(
    call: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    *,
    on_retry: Optional[Callable[[int, float, BaseException], Any]] = None,
    deadline: Optional[RunDeadline] = None,
    retryable: Optional[Callable[[BaseException], bool]] = None,
) -> T:
    """Run `call`, retrying per `policy`.

    `on_retry(attempt, delay, exc)` may be sync or async; it is awaited when it
    returns an awaitable. `retryable` overrides the class check (the step
    executor uses it to refuse a retry after text has already streamed).
    """
    predicate = retryable or is_retryable
    started = time.monotonic()
    attempts = max(1, int(policy.attempts))
    for attempt in range(attempts):
        try:
            return await call()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001 - re-raised unless retried
            if attempt >= attempts - 1 or not predicate(exc):
                raise
            if deadline is not None and deadline.expired():
                raise
            if (time.monotonic() - started) >= policy.max_elapsed_s:
                raise
            delay = policy.delay(attempt)
            hinted = retry_after_seconds(exc)
            if hinted is not None:
                delay = max(delay, hinted)
            if deadline is not None and delay >= deadline.remaining():
                raise
            if on_retry is not None:
                outcome = on_retry(attempt, delay, exc)
                if asyncio.iscoroutine(outcome):
                    await outcome
            await asyncio.sleep(max(0.0, delay))
    raise AssertionError("unreachable: retry loop always returns or raises")


__all__ = [
    "RETRYABLE_CLASSES",
    "RetryPolicy",
    "RunDeadline",
    "is_retryable",
    "retry_after_seconds",
    "retry_async",
]
