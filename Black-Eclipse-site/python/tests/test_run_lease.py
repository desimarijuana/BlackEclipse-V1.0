"""Run leases: one live owner, atomic claims, fencing epochs, recovery safety."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.persistence import AgentMemoryStore, DB_FILENAME
from harness.run_lease import RunLeaseManager
from harness.run_recovery import fail_orphaned_runs


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-lease-py-")
    s = AgentMemoryStore(os.path.join(directory, DB_FILENAME))
    yield s
    s.close()


def _manager(store, runtime_id: str, environment: str = "prod", ttl_ms: int = 5_000):
    return RunLeaseManager(
        store, runtime_id=runtime_id, environment=environment, ttl_ms=ttl_ms
    )


def test_one_live_owner_and_monotonic_epoch(store):
    a = _manager(store, "rt-a")
    b = _manager(store, "rt-b")

    assert a.claim("run_1") == 1
    assert b.claim("run_1") is None  # a live lease cannot be stolen
    assert a.heartbeat("run_1", 1) is True
    assert b.heartbeat("run_1", 1) is False  # not the owner

    a.release("run_1", 1)
    assert b.claim("run_1") == 2  # epoch advances; the old token is fenced
    assert b.heartbeat("run_1", 1) is False
    assert b.heartbeat("run_1", 2) is True


def test_expired_lease_is_reclaimable(store):
    a = _manager(store, "rt-a", ttl_ms=5_000)
    b = _manager(store, "rt-b", ttl_ms=5_000)
    assert a.claim("run_exp") == 1
    lease = a.owner("run_exp")
    assert lease and lease["runtimeId"] == "rt-a"
    # Expire it without waiting: the manager's clock is authoritative.
    store._db.execute(
        "UPDATE RunLease SET expiresAtMs=0 WHERE runId=?", ("run_exp",)
    )
    store._db.commit()
    assert b.is_live("run_exp") is False
    assert b.claim("run_exp") == 2


def test_recovery_never_touches_a_live_leased_run(store):
    store.create_run("run_live", "eclipse-agent", {"query": "x"})
    store.update_run("run_live", status="running")
    manager = _manager(store, "rt-a")
    assert manager.claim("run_live") == 1

    assert fail_orphaned_runs(store, "restarted", environment="prod") == 0
    assert store.get_run("run_live")["status"] == "running"

    manager.release("run_live", 1)
    assert fail_orphaned_runs(store, "restarted", environment="prod") == 1
    # No checkpoint -> terminal orphan, not a live overwrite.
    assert store.get_run("run_live")["status"] == "failed"


def test_recovery_skips_another_environment(store):
    _manager(store, "rt-env", environment="prod")  # ensures the schema columns
    store.create_run("run_dev", "eclipse-agent", {"query": "x"})
    store.update_run("run_dev", status="running")
    store._db.execute(
        "UPDATE HarnessRun SET environment='dev' WHERE id='run_dev'"
    )
    store._db.commit()
    assert fail_orphaned_runs(store, "restarted", environment="prod") == 0
    assert store.get_run("run_dev")["status"] == "running"


def test_guard_holds_the_lease_for_the_block_and_releases_it(store):
    from harness.run_lease import RunLeaseGuard

    with RunLeaseGuard(store, "run_guard", runtime_id="rt-guard") as guard:
        assert guard.owned is True
        manager = _manager(store, "rt-other")
        assert manager.is_live("run_guard") is True
        assert manager.claim("run_guard") is None
    # Released on exit: the next owner can claim (with a new epoch).
    assert _manager(store, "rt-other").is_live("run_guard") is False
    assert _manager(store, "rt-other").claim("run_guard") == 2


def test_guard_degrades_for_a_store_without_sqlite(store):
    from harness.run_lease import RunLeaseGuard

    class _Stub:
        pass

    with RunLeaseGuard(_Stub(), "run_stub") as guard:
        assert guard.owned is True


def test_fenced_terminal_write_requires_the_current_owner(store):
    from harness.run_lease import fenced_update_run

    a = _manager(store, "rt-a")
    store.create_run("run_fence", "eclipse-agent", {"query": "x"})
    store.update_run("run_fence", status="running")
    assert a.claim("run_fence") == 1

    # A stale/other worker cannot finalize the run.
    assert fenced_update_run(
        store, "run_fence", runtime_id="rt-b", status="completed", output="stolen"
    ) is False
    assert store.get_run("run_fence")["status"] == "running"

    # The owner can.
    assert fenced_update_run(
        store, "run_fence", runtime_id="rt-a", status="completed", output="ok"
    ) is True
    assert store.get_run("run_fence")["output"] == "ok"


def test_unleased_run_remains_writable_for_compatibility(store):
    from harness.run_lease import fenced_update_run

    store.create_run("run_plain", "eclipse-agent", {"query": "x"})
    store.update_run("run_plain", status="running")
    assert fenced_update_run(store, "run_plain", status="completed", output="ok") is True
    assert store.get_run("run_plain")["status"] == "completed"


def test_fenced_progress_stops_a_stale_worker(store):
    from harness.run_lease import LeaseLost, fenced_progress

    a = _manager(store, "rt-a")
    store.create_run("run_progress", "eclipse-agent", {"query": "x"})
    store.update_run("run_progress", status="running")
    assert a.claim("run_progress") == 1

    fenced_progress(store, "run_progress", runtime_id="rt-a", modelSteps=1)
    assert store.get_run("run_progress")["modelSteps"] == 1

    with pytest.raises(LeaseLost):
        fenced_progress(store, "run_progress", runtime_id="rt-b", modelSteps=99)
    assert store.get_run("run_progress")["modelSteps"] == 1


def test_fenced_progress_flag_off_restores_update_run(store, monkeypatch):
    from harness.run_lease import fenced_progress

    monkeypatch.setenv("HARNESS_FENCED_PROGRESS", "off")
    a = _manager(store, "rt-a")
    store.create_run("run_legacy", "eclipse-agent", {"query": "x"})
    store.update_run("run_legacy", status="running")
    assert a.claim("run_legacy") == 1

    # The rollback path is deliberately unfenced (today's behaviour).
    fenced_progress(store, "run_legacy", runtime_id="rt-b", modelSteps=7)
    assert store.get_run("run_legacy")["modelSteps"] == 7


def test_fenced_progress_allows_an_unleased_run(store):
    from harness.run_lease import fenced_progress

    store.create_run("run_free", "eclipse-agent", {"query": "x"})
    fenced_progress(store, "run_free", modelSteps=3)
    assert store.get_run("run_free")["modelSteps"] == 3

