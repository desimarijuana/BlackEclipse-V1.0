"""A hard deadline that cannot be defeated by a coroutine that swallows cancellation.

`asyncio.wait_for` waits for the cancellation of the inner task to COMPLETE
before raising `TimeoutError`. A provider adapter or tool handler that suppresses
`CancelledError` (observed live: one run sat on `model.requested` for 10+ minutes
and never emitted a terminal event) can therefore hang the await forever — and
with it the whole run and the user's chat stream.

`await_bounded` instead races the work against a plain timer: on expiry it
requests cancellation and raises `TimeoutError` WITHOUT waiting for the
cancellation to be acknowledged. The abandoned task is drained by a done
callback so asyncio never logs an unretrieved exception. The outer-cancellation
path (user cancels the run) still cancels the inner task and re-raises.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine, Optional


def _drain(task: "asyncio.Task[Any]") -> None:
    """Retrieve an abandoned task's result/exception so asyncio stays quiet."""
    if task.cancelled():
        return
    try:
        task.exception()
    except BaseException:  # noqa: BLE001 - the outcome no longer has an owner
        pass


async def await_bounded(
    coro: Coroutine[Any, Any, Any],
    timeout_s: float,
    *,
    on_timeout: Optional[Callable[[], None]] = None,
) -> Any:
    """Await `coro` with a HARD deadline of `timeout_s` seconds.

    Raises `asyncio.TimeoutError` at the deadline even when the underlying
    coroutine ignores cancellation. `on_timeout` (optional) runs first so the
    caller can flag the abandoned work (e.g. stop it emitting deltas).
    """
    task = asyncio.ensure_future(coro)
    task.add_done_callback(_drain)
    try:
        done, _pending = await asyncio.wait({task}, timeout=timeout_s)
    except asyncio.CancelledError:
        # Outer cancellation (run cancelled): propagate after requesting the
        # inner task's cancellation, exactly like wait_for's normal path.
        task.cancel()
        raise
    if task not in done:
        if on_timeout is not None:
            on_timeout()
        task.cancel()
        raise asyncio.TimeoutError()
    return task.result()


__all__ = ["await_bounded"]
