"""ExecutionManager routing: DIRECT / CONCURRENT / BACKGROUND / DURABLE."""

from __future__ import annotations

import pytest

from harness.fabric import JobState

from fabric_helpers import function_worker, make_manager, make_store, wait_terminal


@pytest.fixture()
def store(tmp_path):
    s = make_store(tmp_path)
    yield s
    s.close()


async def test_direct_runs_inline_and_persists_nothing(store):
    manager = make_manager(store)

    async def handler(ctx):
        return {"status": "succeeded", "output": {"echo": ctx.job.input}}

    manager.register_worker(function_worker("tool", ["user"], handler))
    result = await manager.submit("tool", {"a": 1}, mode="DIRECT")
    assert result["status"] == "succeeded"
    assert result["output"] == {"echo": {"a": 1}}
    assert result["mode"] == "DIRECT"
    assert manager.stats()["totalJobs"] == 0


async def test_background_returns_id_and_outlives_the_call(store):
    manager = make_manager(store)

    async def handler(ctx):
        return {"status": "succeeded", "output": "later"}

    manager.register_worker(function_worker("tool", ["user"], handler))
    await manager.start()
    submitted = await manager.submit("tool", {}, mode="BACKGROUND", queue="user")
    assert submitted["mode"] == "BACKGROUND"
    assert submitted["jobId"]
    job = await wait_terminal(manager, submitted["jobId"])
    assert job["status"] == JobState.SUCCEEDED.value
    assert job["output"] == "later"
    await manager.stop()


async def test_concurrent_awaits_the_result(store):
    manager = make_manager(store)

    async def handler(ctx):
        return {"status": "succeeded", "output": "sync-result"}

    manager.register_worker(function_worker("agent", ["agent"], handler))
    await manager.start()
    result = await manager.submit("agent", {"query": "hi"}, mode="CONCURRENT")
    assert result["status"] == JobState.SUCCEEDED.value
    assert result["output"] == "sync-result"
    assert result["mode"] == "CONCURRENT"
    await manager.stop()


async def test_durable_is_persisted_and_idempotent(store):
    manager = make_manager(store)
    first = await manager.submit("market", {"symbols": ["AAPL"]}, mode="DURABLE")
    second = await manager.submit("market", {"symbols": ["AAPL"]}, mode="DURABLE")
    assert first["jobId"] == second["jobId"]
    assert second.get("deduplicated") is True
    job = manager.get(first["jobId"])
    assert job["durable"] is True
    # A different payload is a different job.
    third = await manager.submit("market", {"symbols": ["MSFT"]}, mode="DURABLE")
    assert third["jobId"] != first["jobId"]


async def test_parent_and_root_job_lineage(store):
    manager = make_manager(store)
    parent = await manager.submit("agent", {"query": "parent"}, mode="BACKGROUND")
    child = await manager.submit("agent", {"query": "child"}, mode="BACKGROUND",
                                 parent_job_id=parent["jobId"])
    got = manager.get(child["jobId"])
    assert got["parentJobId"] == parent["jobId"]
    assert got["rootJobId"] == parent["jobId"]
    assert [j["jobId"] for j in manager.children(parent["jobId"])] == [child["jobId"]]


async def test_admin_retry_replays_a_failed_job(store):
    manager = make_manager(store)

    async def handler(ctx):
        return {"status": "failed", "error": "deterministic", "errorClass": "INVALID_INPUT"}

    manager.register_worker(function_worker("tool", ["user"], handler))
    await manager.start()
    submitted = await manager.submit("tool", {}, mode="BACKGROUND", queue="user")
    job = await wait_terminal(manager, submitted["jobId"])
    assert job["status"] == JobState.FAILED.value
    replay = await manager.retry(submitted["jobId"])
    assert replay["retried"] is True
    # It was re-queued (and would be re-claimed by the still-running worker).
    assert manager.get(submitted["jobId"])["status"] in (
        JobState.QUEUED.value, JobState.RUNNING.value, JobState.FAILED.value,
    )
    await manager.stop()


async def test_cancel_unknown_job_is_honest(store):
    manager = make_manager(store)
    result = await manager.cancel("job_missing")
    assert result["cancelled"] is False


async def test_submit_dag_reports_unavailable_without_orchestration(store):
    manager = make_manager(store)  # service=None -> no orchestration layer
    result = await manager.submit_dag([{"id": "a", "kind": "noop"}])
    assert result["status"] == "failed"
    assert result["errorClass"] == "RUNTIME_UNAVAILABLE"


async def test_health_and_stats_shapes(store):
    manager = make_manager(store)
    health = manager.health()
    assert health["available"] is True
    assert "workers" in health and "metrics" in health
    stats = manager.stats()
    assert "queues" in stats and "statusCounts" in stats and "config" in stats
