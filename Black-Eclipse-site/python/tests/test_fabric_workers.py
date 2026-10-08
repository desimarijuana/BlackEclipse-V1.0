"""WorkerManager: retries, DLQ, timeouts, cancellation, concurrency, recovery."""

from __future__ import annotations

import asyncio
import time

import pytest

from harness.fabric import JobState

from fabric_helpers import function_worker, make_manager, make_store, wait_terminal


@pytest.fixture()
def store(tmp_path):
    s = make_store(tmp_path)
    yield s
    s.close()


async def test_retry_then_success(store):
    manager = make_manager(store)
    calls = {"n": 0}

    async def handler(ctx):
        calls["n"] += 1
        if ctx.job.attempts < 2:
            return {"status": "failed", "error": "transient", "errorClass": "NETWORK_ERROR",
                    "retryable": True}
        return {"status": "succeeded", "output": "done"}

    manager.register_worker(function_worker("tool", ["user"], handler))
    await manager.start()
    submitted = await manager.submit("tool", {"x": 1}, mode="BACKGROUND",
                                     queue="user", max_attempts=3)
    job = await wait_terminal(manager, submitted["jobId"])
    assert job["status"] == JobState.SUCCEEDED.value
    assert job["attempts"] == 2
    assert calls["n"] == 2
    assert len(manager.attempts(job["jobId"])) == 2
    await manager.stop()


async def test_retryable_exhausted_routes_to_dlq(store):
    manager = make_manager(store)

    async def handler(ctx):
        return {"status": "failed", "error": "always", "errorClass": "PROVIDER_ERROR",
                "retryable": True}

    manager.register_worker(function_worker("tool", ["user"], handler))
    await manager.start()
    submitted = await manager.submit("tool", {}, mode="BACKGROUND", queue="user", max_attempts=2)
    job = await wait_terminal(manager, submitted["jobId"])
    assert job["status"] == JobState.DEAD_LETTER.value
    assert job["attempts"] == 2
    assert [j["jobId"] for j in manager.dlq()] == [submitted["jobId"]]
    await manager.stop()


async def test_non_retryable_fails_immediately(store):
    manager = make_manager(store)

    async def handler(ctx):
        return {"status": "failed", "error": "bad input", "errorClass": "INVALID_INPUT"}

    manager.register_worker(function_worker("tool", ["user"], handler))
    await manager.start()
    submitted = await manager.submit("tool", {}, mode="BACKGROUND", queue="user", max_attempts=3)
    job = await wait_terminal(manager, submitted["jobId"])
    assert job["status"] == JobState.FAILED.value
    assert job["attempts"] == 1
    assert manager.dlq() == []
    await manager.stop()


async def test_timeout_is_recorded_as_timed_out(store):
    manager = make_manager(store)

    async def handler(ctx):
        await asyncio.sleep(5)
        return {"status": "succeeded"}

    manager.register_worker(function_worker("tool", ["user"], handler))
    await manager.start()
    submitted = await manager.submit("tool", {}, mode="BACKGROUND", queue="user",
                                     timeout_ms=150, max_attempts=1)
    job = await wait_terminal(manager, submitted["jobId"], timeout=4)
    assert job["status"] == JobState.TIMED_OUT.value
    await manager.stop()


async def test_cancellation_propagates_to_the_handler(store):
    manager = make_manager(store)
    observed = {"cancelled": False}

    async def handler(ctx):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            observed["cancelled"] = True
            raise
        return {"status": "succeeded"}

    manager.register_worker(function_worker("agent", ["agent"], handler))
    await manager.start()
    submitted = await manager.submit("agent", {}, mode="BACKGROUND")
    jid = submitted["jobId"]
    for _ in range(100):
        if manager.get(jid)["status"] == JobState.RUNNING.value:
            break
        await asyncio.sleep(0.02)
    result = await manager.cancel(jid)
    assert result["cancelled"]
    job = await wait_terminal(manager, jid)
    assert job["status"] == JobState.CANCELLED.value
    assert observed["cancelled"] is True
    await manager.stop()


async def test_managed_concurrency_runs_slots_in_parallel(store):
    manager = make_manager(store)
    state = {"active": 0, "max": 0}

    async def handler(ctx):
        state["active"] += 1
        state["max"] = max(state["max"], state["active"])
        await asyncio.sleep(0.25)
        state["active"] -= 1
        return {"status": "succeeded"}

    manager.register_worker(function_worker("tool", ["user"], handler, concurrency=3))
    await manager.start()
    jobs = [
        await manager.submit("tool", {"i": i}, mode="BACKGROUND", queue="user")
        for i in range(5)
    ]
    for submitted in jobs:
        await wait_terminal(manager, submitted["jobId"], timeout=6)
    assert state["max"] == 3
    await manager.stop()


async def test_recovery_requeues_a_dead_workers_job(store):
    manager = make_manager(store)
    submitted = await manager.submit("tool", {}, mode="BACKGROUND", queue="user", max_attempts=3)
    # Simulate a worker that claimed the job then died: force its lease to lapse.
    manager._store.claim_job(["user"], worker_id="dead", worker_kind="tool", lease_seconds=5)
    manager._store.update_job(submitted["jobId"], leaseExpiresAt=time.time() - 1)
    recovered = await manager.recover()
    assert submitted["jobId"] in recovered
    assert manager.get(submitted["jobId"])["status"] == JobState.QUEUED.value


async def test_graceful_shutdown_leaves_durable_work_recoverable(store):
    manager = make_manager(store)

    async def handler(ctx):
        await asyncio.sleep(10)
        return {"status": "succeeded"}

    manager.register_worker(function_worker("tool", ["user"], handler))
    await manager.start()
    submitted = await manager.submit("tool", {}, mode="BACKGROUND", queue="user", max_attempts=3)
    for _ in range(100):
        if manager.get(submitted["jobId"])["status"] == JobState.RUNNING.value:
            break
        await asyncio.sleep(0.02)
    await manager.stop(timeout=0.3)
    # Not silently completed or failed; the lease will be recovered.
    assert not manager.get(submitted["jobId"])["terminal"]
    manager._store.update_job(submitted["jobId"], leaseExpiresAt=time.time() - 1)
    recovered = await manager.recover()
    assert submitted["jobId"] in recovered
    assert manager.get(submitted["jobId"])["status"] == JobState.QUEUED.value
