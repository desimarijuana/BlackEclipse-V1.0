"""Drift watch: one read-only cadence, transition-only publication."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from harness.persistence import AgentMemoryStore
from harness.self_improvement import drift_watch as watch_module
from harness.self_improvement.drift_watch import DriftWatcher


class _Service:
    def __init__(self, store) -> None:
        self.store = store


def _insert(store, *, day: int, completed: int, failed: int) -> None:
    db = store._db
    origin = datetime(2026, 10, day, tzinfo=timezone.utc)
    for index in range(completed):
        stamp = (origin + timedelta(minutes=index)).isoformat()
        db.execute(
            "INSERT INTO HarnessRun (id, agentId, status, input, createdAt, updatedAt) "
            "VALUES (?, 'eclipse-agent', 'completed', '{}', ?, ?)",
            (f"ok-{day}-{index}", stamp, stamp),
        )
    for index in range(failed):
        stamp = (origin + timedelta(minutes=completed + index)).isoformat()
        db.execute(
            "INSERT INTO HarnessRun (id, agentId, status, input, createdAt, updatedAt) "
            "VALUES (?, 'eclipse-agent', 'failed', '{}', ?, ?)",
            (f"bad-{day}-{index}", stamp, stamp),
        )
    db.commit()


@pytest.mark.asyncio
async def test_drift_watch_publishes_only_on_transition(tmp_path, monkeypatch):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    published: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        watch_module, "publish_event",
        lambda type, payload, **_kwargs: published.append((type, payload)),
    )
    try:
        _insert(store, day=21, completed=10, failed=20)
        _insert(store, day=20, completed=100, failed=0)
        watcher = DriftWatcher(_Service(store), interval_seconds=0)

        first = await watcher.check()
        second = await watcher.check()

        assert any(row["scope"] == "eclipse-agent" for row in first["drifted"])
        assert second["drifted"] == []
        assert {event[1]["scope"] for event in published} == {"global", "eclipse-agent"}
        assert all(event[0] == "self_improvement.drift_detected" for event in published)
        assert len(published) == 2
        assert watcher.health()["last"]["eclipse-agent"] == "drift"

        restarted = DriftWatcher(_Service(store), interval_seconds=0)
        third = await restarted.check()
        assert third["drifted"] == []
        assert len(published) == 2

        # A reset database clears the persisted episode instead of inheriting it.
        store._db.execute("DELETE FROM HarnessRun")
        store._db.commit()
        cleaned = DriftWatcher(_Service(store), interval_seconds=0)
        await cleaned.check()
        rows = store._db.execute("SELECT COUNT(*) AS n FROM DriftWatchState").fetchone()
        assert int(rows["n"]) == 0
    finally:
        store.close()


@pytest.mark.asyncio
async def test_start_runs_checks_and_stop_cancels(tmp_path, monkeypatch):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    calls: list[int] = []

    async def fake_check():
        calls.append(1)
        return {"checked": 0, "drifted": []}

    try:
        watcher = DriftWatcher(_Service(store), interval_seconds=1)
        monkeypatch.setattr(watcher, "check", fake_check)
        await watcher.start()
        await asyncio.sleep(1.2)
        assert watcher.health()["running"] is True
        await watcher.stop()
        assert calls
        assert watcher.health()["running"] is False
    finally:
        store.close()

@pytest.mark.asyncio
async def test_drift_watch_opens_an_inert_candidate_only_when_opted_in(tmp_path, monkeypatch):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    published: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        watch_module, "publish_event",
        lambda type, payload, **_kwargs: published.append((type, payload)),
    )
    monkeypatch.delenv("HARNESS_RSL_DRIFT_AUTOCANDIDATE", raising=False)
    try:
        _insert(store, day=21, completed=10, failed=20)
        _insert(store, day=20, completed=100, failed=0)
        watcher = DriftWatcher(_Service(store), interval_seconds=0)

        await watcher.check()

        # OFF by default: a drift transition never opens a candidate.
        assert not any(
            event[0] == "self_improvement.drift_candidate_created"
            for event in published
        )
        assert watcher.health()["autoCandidate"] is False

        # ON: the SAME inert candidate the operator route opens. The watch
        # state is cleared so this is a NEW episode, not the same transition.
        monkeypatch.setenv("HARNESS_RSL_DRIFT_AUTOCANDIDATE", "on")
        assert watcher.health()["autoCandidate"] is True
        store._db.execute("DELETE FROM DriftWatchState")
        store._db.commit()
        watcher2 = DriftWatcher(_Service(store), interval_seconds=0)
        await watcher2.check()
        assert any(
            event[0] == "self_improvement.drift_candidate_created"
            for event in published
        )
        # The candidate carries no target and no operations: it is evidence.
        from harness.code.evolution_store import EvolutionStore

        candidates = [
            row for row in EvolutionStore(store).list_candidates(limit=50)
            if row.get("sourceCategory") == "drift"
        ]
        assert candidates
        assert not candidates[0].get("targetPath")
        assert not candidates[0].get("proposedOps")
    finally:
        store.close()
