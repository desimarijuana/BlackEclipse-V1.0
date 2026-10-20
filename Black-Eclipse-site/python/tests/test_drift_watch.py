"""Drift watch: one read-only cadence, transition-only publication."""

from __future__ import annotations

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
    finally:
        store.close()
