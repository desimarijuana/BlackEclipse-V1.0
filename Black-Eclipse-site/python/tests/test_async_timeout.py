"""The hard-deadline primitive: a deadline that survives swallowed cancellation."""

from __future__ import annotations

import asyncio
import time

import pytest

from harness.async_timeout import await_bounded
from harness.model_stream import ainvoke_streaming


class _Emitter:
    def __init__(self) -> None:
        self.deltas: list[str] = []

    def emit_transient(self, kind: str, data: dict) -> None:  # noqa: ARG002
        if "text" in data:
            self.deltas.append(str(data["text"]))


def _stubborn_until(release: asyncio.Event):
    """A pathological coroutine that swallows CancelledError until released."""

    async def stubborn() -> str:
        while not release.is_set():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                continue  # the exact behavior that made `wait_for` hang forever
        return "late"

    return stubborn


@pytest.mark.asyncio
async def test_returns_the_result_within_the_deadline():
    async def work() -> int:
        await asyncio.sleep(0.01)
        return 42

    assert await await_bounded(work(), 1.0) == 42


@pytest.mark.asyncio
async def test_deadline_holds_even_when_the_coro_swallows_cancellation():
    release = asyncio.Event()
    started = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        await await_bounded(_stubborn_until(release)(), 0.05)
    assert time.monotonic() - started < 1.0
    release.set()
    await asyncio.sleep(0.05)  # let the abandoned task exit cleanly


@pytest.mark.asyncio
async def test_on_timeout_hook_runs_before_the_timeout():
    release = asyncio.Event()
    calls: list[int] = []
    with pytest.raises(asyncio.TimeoutError):
        await await_bounded(_stubborn_until(release)(), 0.02, on_timeout=lambda: calls.append(1))
    assert calls == [1]
    release.set()
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_outer_cancellation_still_cancels_the_inner_task():
    cancelled = asyncio.Event()

    async def work() -> None:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.ensure_future(await_bounded(work(), 10.0))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.01)
    assert cancelled.is_set()


class _SwallowingModel:
    """A provider adapter whose stream ignores cancellation (observed live)."""

    def __init__(self, release: asyncio.Event) -> None:
        self.release = release

    async def astream(self, messages):  # noqa: ANN001, ANN201, ARG002
        while not self.release.is_set():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                continue
        if False:  # pragma: no cover - keeps this an async generator
            yield None


@pytest.mark.asyncio
async def test_model_call_times_out_even_when_the_provider_swallows_cancellation():
    release = asyncio.Event()
    started = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        await ainvoke_streaming(_SwallowingModel(release), [], 0.05, _Emitter(), False)
    assert time.monotonic() - started < 1.0
    release.set()
    await asyncio.sleep(0.05)
