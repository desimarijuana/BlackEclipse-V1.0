"""Drift detection: recent vs preceding runs, honest unmeasured and scoped reads."""

from __future__ import annotations

from harness.code.evolution_store import EvolutionStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.drift import (
    DRIFT,
    STABLE,
    UNMEASURED,
    detect_store_drift,
    drift_history,
    drift_signal,
    record_drift_candidate,
)


def _runs(*, completed=0, failed=0, agent="eclipse-agent", start=0):
    rows = []
    for index in range(completed):
        rows.append({
            "runId": f"ok-{start + index}", "agentId": agent,
            "status": "completed", "createdAt": f"2026-10-20T00:{index:02d}:00Z",
        })
    for index in range(failed):
        rows.append({
            "runId": f"bad-{start + index}", "agentId": agent,
            "status": "failed", "createdAt": f"2026-10-20T00:{completed + index:02d}:00Z",
        })
    return rows


def test_stable_window_has_no_signal():
    signal = drift_signal(_runs(completed=30) + _runs(completed=100, start=30))
    assert signal["status"] == STABLE
    assert signal["drop"] == 0.0


def test_a_large_drop_is_drift():
    current = _runs(completed=10, failed=20)
    baseline = _runs(completed=90, failed=10, start=30)
    signal = drift_signal(current + baseline, window=30, baseline=100)
    assert signal["status"] == DRIFT
    assert signal["drop"] > 0.5
    assert signal["current"]["n"] == 30
    assert signal["baseline"]["n"] == 100


def test_thin_data_is_unmeasured_never_zero():
    signal = drift_signal(_runs(completed=2) + _runs(failed=2, start=2))
    assert signal["status"] == UNMEASURED
    assert signal["drop"] is None
    assert any("need" in reason for reason in signal["reasons"])


def test_scope_filters_the_windows():
    mixed = (
        _runs(completed=10, agent="code-agent")
        + _runs(completed=30, agent="eclipse-agent")
        + _runs(completed=100, agent="eclipse-agent", start=30)
    )
    signal = drift_signal(
        mixed, scope="eclipse-agent", window=30, baseline=100,
    )
    assert signal["status"] == STABLE
    assert signal["current"]["n"] == 30
    assert signal["baseline"]["n"] == 100


def test_store_detection_reads_terminal_runs(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        db = store._db
        for index in range(30):
            stamp = f"2026-10-20T01:{index:02d}:00Z"
            db.execute(
                "INSERT INTO HarnessRun (id, agentId, status, input, createdAt, updatedAt) "
                "VALUES (?, ?, ?, '{}', ?, ?)",
                (f"recent-{index}", "eclipse-agent", "completed" if index < 10 else "failed", stamp, stamp),
            )
        for index in range(100):
            stamp = f"2026-10-20T00:{index:02d}:00Z"
            db.execute(
                "INSERT INTO HarnessRun (id, agentId, status, input, createdAt, updatedAt) "
                "VALUES (?, ?, ?, '{}', ?, ?)",
                (f"base-{index}", "eclipse-agent", "completed", stamp, stamp),
            )
        db.commit()

        signal = detect_store_drift(
            store, scope="eclipse-agent", window=30, baseline=100, min_samples=10,
        )
        assert signal["status"] == DRIFT
        assert signal["current"]["n"] == 30
        assert signal["baseline"]["n"] == 100
    finally:
        store.close()


def test_drift_candidate_is_inert_and_deduplicated(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        signal = drift_signal(
            _runs(completed=10, failed=20)
            + _runs(completed=90, failed=10, start=30),
            window=30, baseline=100,
        )
        first = record_drift_candidate(store, signal)
        second = record_drift_candidate(store, signal)

        assert first["created"] is True
        assert first["candidate"]["subjectType"] == "drift"
        assert first["candidate"]["sourceCategory"] == "drift"
        assert first["candidate"]["scope"] == "global"
        assert first["candidate"]["targetPath"] is None
        assert first["candidate"]["status"] == "inert"
        assert second["created"] is False
        assert second["reason"] == "already_exists"
        assert second["candidate"]["id"] == first["candidate"]["id"]
        assert len(EvolutionStore(store).list_candidates()) == 1

        new_episode = record_drift_candidate(
            store, {**signal, "anchor": "newest-run-after-recovery"},
        )
        assert new_episode["created"] is True
        assert new_episode["candidate"]["id"] != first["candidate"]["id"]
        assert len(EvolutionStore(store).list_candidates()) == 2
    finally:
        store.close()


def test_history_walks_back_through_the_same_runs(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        db = store._db
        for index in range(30):
            stamp = f"2026-10-20T01:{index:02d}:00Z"
            db.execute(
                "INSERT INTO HarnessRun (id, agentId, status, input, createdAt, updatedAt) "
                "VALUES (?, 'eclipse-agent', ?, '{}', ?, ?)",
                (
                    f"recent-{index}",
                    "completed" if index < 10 else "failed",
                    stamp, stamp,
                ),
            )
        for index in range(100):
            stamp = f"2026-10-20T00:{index:02d}:00Z"
            db.execute(
                "INSERT INTO HarnessRun (id, agentId, status, input, createdAt, updatedAt) "
                "VALUES (?, 'eclipse-agent', 'completed', '{}', ?, ?)",
                (f"base-{index}", stamp, stamp),
            )
        db.commit()

        history = drift_history(
            store, scope="eclipse-agent", window=30, baseline=100,
            min_samples=10, limit=3, step=30,
        )
        assert history["scope"] == "eclipse-agent"
        assert history["points"][0]["status"] == DRIFT
        assert history["points"][0]["offset"] == 0
        assert history["points"][1]["offset"] == 30
        assert len(history["points"]) >= 2
        assert history["computedPoints"] == len(history["points"])
        assert history["requestedPoints"] == 3

        older = drift_history(
            store, scope="eclipse-agent", window=30, baseline=100,
            min_samples=10, limit=1, step=30, offset=30,
        )
        assert older["offset"] == 30
        assert older["points"][0]["offset"] == 30
    finally:
        store.close()


def test_stable_or_unmeasured_signals_create_no_candidate(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        stable = drift_signal(_runs(completed=30) + _runs(completed=100, start=30))
        assert record_drift_candidate(store, stable)["created"] is False
        unmeasured = drift_signal(_runs(completed=2))
        assert record_drift_candidate(store, unmeasured)["created"] is False
        assert EvolutionStore(store).list_candidates() == []
    finally:
        store.close()
