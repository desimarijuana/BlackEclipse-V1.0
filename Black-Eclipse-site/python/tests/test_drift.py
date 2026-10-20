"""Drift detection: recent vs preceding runs, honest unmeasured and scoped reads."""

from __future__ import annotations

from harness.persistence import AgentMemoryStore
from harness.self_improvement.drift import (
    DRIFT,
    STABLE,
    UNMEASURED,
    detect_store_drift,
    drift_signal,
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
