"""Per-run latency summary: setup, TTFT and token cadence in ONE trace event."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.events import RunEmitter
from harness.persistence import AgentMemoryStore
from harness.run_timings import RunTimings, percentile


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_summary_measures_setup_ttft_and_cadence():
    clock = FakeClock()
    timings = RunTimings(clock)

    timings.observe("run.started", {})
    clock.advance(0.4)  # prompt/memory/surface assembly
    timings.observe("model.requested", {})
    clock.advance(0.9)  # provider latency
    timings.observe("model.first_token", {"ttftMs": 900})
    for _ in range(3):
        clock.advance(0.05)
        timings.observe("model.delta", {"text": "abc"})
    clock.advance(0.2)
    summary = timings.summary()

    assert summary["setupMs"] == 400
    assert summary["ttftMs"] == 900
    assert summary["firstDeltaMs"] == 1350
    assert summary["deltaCount"] == 3
    assert summary["streamedChars"] == 9
    assert summary["modelCalls"] == 1
    # Two observed gaps (50 ms, 50 ms) plus the gap into the first delta.
    assert summary["deltaGapP50Ms"] == 50
    assert summary["deltaGapMaxMs"] == 50
    assert summary["totalMs"] == 1650


def test_summary_omits_what_was_never_observed():
    timings = RunTimings(FakeClock())
    timings.observe("run.started", {})
    summary = timings.summary()
    assert "setupMs" not in summary
    assert "ttftMs" not in summary
    assert summary["deltaCount"] == 0


def test_percentile_interpolates_and_handles_small_samples():
    assert percentile([], 50) is None
    assert percentile([4.0], 95) == 4.0
    assert percentile([1.0, 2.0, 3.0], 50) == 2.0
    assert percentile([1.0, 2.0], 100) == 2.0


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-run-timings-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


@pytest.mark.asyncio
async def test_emitter_writes_one_run_timings_after_the_terminal_event(store):
    store.create_run("run_t", "a", {"query": "x"})
    emitter = RunEmitter("run_t", store)

    await emitter.emit("run.started", {"maxSteps": 4})
    await emitter.emit("model.requested", {"step": 1})
    await emitter.emit("model.first_token", {"ttftMs": 250})
    emitter.emit_transient("model.delta", {"text": "Hello"})
    emitter.emit_transient("model.delta", {"text": " world"})
    await emitter.emit("run.completed", {"status": "completed"})
    # A second terminal event must not write a second summary.
    await emitter.emit("run.completed", {"status": "completed"})

    persisted = store.list_events("run_t")
    types = [e["type"] for e in persisted]
    assert types.count("run.timings") == 1
    assert types.index("run.timings") > types.index("run.completed")
    # Token deltas stay live-only; the summary carries their cadence instead.
    assert "model.delta" not in types

    summary = next(e for e in persisted if e["type"] == "run.timings")["data"]
    assert summary["ttftMs"] == 250
    assert summary["deltaCount"] == 2
    assert summary["streamedChars"] == 11
    assert "setupMs" in summary
