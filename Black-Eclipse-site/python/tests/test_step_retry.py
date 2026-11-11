"""Round 5 / C1: one retry policy and the one model-call path.

These tests are deliberately fast: the policy is injected with jitter off and
zero delay, so a retry is a scheduling hop rather than a sleep.
"""

from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessageChunk

from harness.retry_policy import (
    RetryPolicy,
    RunDeadline,
    is_retryable,
    retry_async,
)
from harness.step import effective_call_timeout, invoke_model_step


class _Emitter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.deltas: list[str] = []

    async def emit(self, event_type: str, data: dict | None = None) -> None:
        self.events.append((event_type, data or {}))

    def emit_sync(self, event_type: str, data: dict | None = None) -> None:
        self.events.append((event_type, data or {}))

    def emit_transient(self, event_type: str, data: dict | None = None) -> None:
        if event_type == "model.delta" and data and data.get("text"):
            self.deltas.append(str(data["text"]))


class _FlakyModel:
    """Fails `failures` times, then streams one chunk."""

    def __init__(self, failures: int, message: str = "429 rate limit exceeded") -> None:
        self.failures = failures
        self.message = message
        self.calls = 0

    async def astream(self, _messages):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError(self.message)
        yield AIMessageChunk(content="ok")

    async def ainvoke(self, _messages):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError(self.message)
        return AIMessageChunk(content="ok")


class _PartialThenFailModel:
    """Streams one delta, then fails. A retry would duplicate the text."""

    def __init__(self) -> None:
        self.stream_calls = 0
        self.invoke_calls = 0

    async def astream(self, _messages):
        self.stream_calls += 1
        yield AIMessageChunk(content="partial")
        raise RuntimeError("500 server error")

    async def ainvoke(self, _messages):
        self.invoke_calls += 1
        raise RuntimeError("500 server error")


def _policy(attempts: int = 3, budget: float = 5.0) -> RetryPolicy:
    return RetryPolicy(
        attempts=attempts,
        base_delay_s=0.0,
        max_delay_s=0.0,
        max_elapsed_s=budget,
        jitter=False,
    )


def test_effective_call_timeout_never_exceeds_the_ceiling():
    assert effective_call_timeout(10.0) == 10.0
    assert effective_call_timeout(10_000.0) == 300.0
    assert effective_call_timeout(0.0) == 1.0


def test_retryable_classification_uses_the_shared_error_vocabulary():
    assert is_retryable(RuntimeError("429 rate limit exceeded")) is True
    assert is_retryable(RuntimeError("invalid api key")) is False
    assert is_retryable(RuntimeError("maximum context length exceeded")) is False
    assert is_retryable(asyncio.CancelledError()) is False


@pytest.mark.asyncio
async def test_retry_async_retries_then_returns():
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("503 service unavailable")
        return "done"

    assert await retry_async(flaky, _policy()) == "done"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_async_does_not_retry_a_bad_request():
    calls = {"n": 0}

    async def bad() -> str:
        calls["n"] += 1
        raise RuntimeError("invalid api key")

    with pytest.raises(RuntimeError):
        await retry_async(bad, _policy())
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_retry_async_stops_when_the_run_deadline_is_spent():
    deadline = RunDeadline(0.01)
    calls = {"n": 0}

    async def slow_failure() -> str:
        calls["n"] += 1
        await asyncio.sleep(0.02)
        raise RuntimeError("503 service unavailable")

    with pytest.raises(RuntimeError):
        await retry_async(slow_failure, _policy(attempts=10), deadline=deadline)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_invoke_model_step_retries_and_emits_a_durable_event():
    # Each failed attempt costs two calls: `astream` fails and
    # `ainvoke_streaming` falls back to `ainvoke`, which fails too.
    model = _FlakyModel(failures=4)
    emitter = _Emitter()

    response = await invoke_model_step(
        model,
        [],
        timeout_s=5.0,
        emitter=emitter,
        finalizing=False,
        policy=_policy(),
        step=1,
    )

    assert response.content == "ok"
    retries = [e for e in emitter.events if e[0] == "model.retry"]
    assert len(retries) == 2
    assert retries[0][1]["attempt"] == 1
    assert retries[0][1]["errorClass"] == "rate_limit"


@pytest.mark.asyncio
async def test_invoke_model_step_does_not_retry_after_text_was_streamed():
    model = _PartialThenFailModel()
    emitter = _Emitter()

    with pytest.raises(RuntimeError):
        await invoke_model_step(
            model,
            [],
            timeout_s=5.0,
            emitter=emitter,
            finalizing=False,
            policy=_policy(),
            step=1,
        )

    # One stream attempt, and exactly one fallback ainvoke inside
    # `ainvoke_streaming`; no second step attempt (which would duplicate text).
    assert model.stream_calls == 1
    assert model.invoke_calls == 1
    assert emitter.deltas == ["partial"]
    assert not [e for e in emitter.events if e[0] == "model.retry"]
