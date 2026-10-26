"""Run stall watchdog: no run can stay non-terminal past its model budget."""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
import tempfile
import time

import pytest

from harness.persistence import AgentMemoryStore, DB_FILENAME
from harness.run_watchdog import (
    APPROVAL_EVENTS,
    find_stalled,
    stall_threshold_s,
    sweep_stalled_runs,
)


def _iso(epoch: float) -> str:
    stamp = _dt.datetime.fromtimestamp(epoch, tz=_dt.timezone.utc)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


# ── Pure detector ─────────────────────────────────────────────────────────────


def test_threshold_scales_with_the_agent_model_budget():
    # Eclipse Agent declares a 120s per-call budget; Code Agent 600s.
    assert stall_threshold_s("eclipse-agent") == 180.0
    assert stall_threshold_s("code-agent") == 660.0
    assert stall_threshold_s(None) == 180.0  # default 120s + grace


def test_find_stalled_flags_only_silent_runs_and_exempts_approval_waits():
    now = 1_000_000.0
    rows = [
        # Healthy: recent event.
        {"id": "fresh", "agentId": "eclipse-agent", "started": _iso(now - 10), "lastEventAt": _iso(now - 5), "lastEventType": "model.requested"},
        # Stalled: silent for 400s > 180s budget.
        {"id": "old", "agentId": "eclipse-agent", "started": _iso(now - 500), "lastEventAt": _iso(now - 400), "lastEventType": "model.requested"},
        # Waiting on the user's approval decision: exempt.
        {"id": "approval", "agentId": "eclipse-agent", "started": _iso(now - 10_000), "lastEventAt": _iso(now - 10_000), "lastEventType": "approval.requested"},
        # No events at all: age measured from `started`.
        {"id": "never_started", "agentId": "eclipse-agent", "started": _iso(now - 300), "lastEventAt": None, "lastEventType": None},
        # A Code Agent run silent 400s is still healthy (600s budget + 60s).
        {"id": "code_long", "agentId": "code-agent", "started": _iso(now - 400), "lastEventAt": _iso(now - 400), "lastEventType": "model.requested"},
    ]
    stalled = find_stalled(rows, now)
    assert set(stalled) == {"old", "never_started"}
    # A `clarify` question parks the run on the same human-decision gate as an
    # approval, so both are exempt.
    assert APPROVAL_EVENTS == {
        "approval.requested", "user.approval.required", "clarification.requested",
    }


# ── DB sweep ─────────────────────────────────────────────────────────────────


class _StubBus:
    def __init__(self) -> None:
        self.ended: list[str] = []

    def end_stream(self, run_id: str) -> None:
        self.ended.append(run_id)


class _StubService:
    def __init__(self, store: AgentMemoryStore) -> None:
        self.store = store
        self.bus = _StubBus()
        self.cancelled: list[str] = []

    def cancel(self, run_id: str) -> bool:
        self.cancelled.append(run_id)
        return True


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-watchdog-py-")
    s = AgentMemoryStore(os.path.join(directory, DB_FILENAME))
    yield s
    s.close()


def _age_run(store: AgentMemoryStore, run_id: str, seconds: float) -> None:
    old = _iso(time.time() - seconds)
    db = store._db  # noqa: SLF001 - test ages the row on purpose
    db.execute(
        "UPDATE HarnessRun SET createdAt = ?, updatedAt = ?, startedAt = ? WHERE id = ?",
        (old, old, old, run_id),
    )
    db.execute("UPDATE HarnessEvent SET at = ? WHERE runId = ?", (old, run_id))


def test_sweep_fails_a_stalled_run_once_and_leaves_terminal_runs_alone(store):
    store.create_run("run_stuck", "eclipse-agent", {"query": "x"})
    store.update_run("run_stuck", status="running")
    store.append_event("run_stuck", "model.requested", 1, {"step": 1})
    _age_run(store, "run_stuck", 600)

    store.create_run("run_done", "eclipse-agent", {"query": "y"})
    store.update_run("run_done", status="completed", output="ok")
    _age_run(store, "run_done", 600)

    service = _StubService(store)
    stalled = sweep_stalled_runs(service)

    assert stalled == ["run_stuck"]
    stuck = store.get_run("run_stuck")
    assert stuck["status"] == "failed"
    assert stuck["error"]["code"] == "RUN_STALLED"
    assert stuck["finishedAt"]
    events = store.list_events("run_stuck")
    assert events[-1]["type"] == "run.failed"
    assert events[-1]["data"]["code"] == "RUN_STALLED"
    assert events[-1]["seq"] == 2
    assert service.bus.ended == ["run_stuck"]
    assert service.cancelled == ["run_stuck"]
    # Terminal runs untouched; a second sweep is a no-op.
    assert store.get_run("run_done")["status"] == "completed"
    assert sweep_stalled_runs(service) == []


def test_sweep_never_raises_on_a_broken_store():
    class _Broken:
        class store:  # noqa: N801 - minimal stub
            _db = None

        class bus:  # noqa: N801
            def end_stream(self, run_id: str) -> None:  # noqa: ARG002
                raise AssertionError("must not be reached")

        def cancel(self, run_id: str) -> bool:  # noqa: ARG002
            raise AssertionError("must not be reached")

    assert sweep_stalled_runs(_Broken()) == []
