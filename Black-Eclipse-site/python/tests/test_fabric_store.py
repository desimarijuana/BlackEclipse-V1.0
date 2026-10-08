"""FabricStore: durable jobs, atomic claim, leases, locks, idempotency, DLQ."""

from __future__ import annotations

import time

import pytest

from harness.fabric import Job, JobState, QueueName
from harness.fabric.models import WorkerInfo

from fabric_helpers import make_store


@pytest.fixture()
def store(tmp_path):
    s = make_store(tmp_path)
    from harness.fabric import FabricStore

    wrapper = FabricStore(s)
    yield wrapper
    s.close()


def _job(**kw) -> Job:
    base = dict(type="tool", queue=QueueName.USER.value, status=JobState.QUEUED.value, priority=500)
    base.update(kw)
    return Job(**base)


def test_create_and_get_roundtrip(store):
    job = _job(input={"a": 1}, metadata={"k": "v"})
    store.create_job(job)
    got = store.get_job(job.id)
    assert got is not None
    assert got.input == {"a": 1}
    assert got.metadata == {"k": "v"}
    assert got.state == JobState.QUEUED


def test_set_state_validates_transitions(store):
    job = _job()
    store.create_job(job)
    store.set_state(job.id, JobState.RUNNING)
    with pytest.raises(Exception):
        store.set_state(job.id, JobState.QUEUED)  # RUNNING -> QUEUED is illegal
    store.set_state(job.id, JobState.SUCCEEDED)
    assert store.get_job(job.id).state == JobState.SUCCEEDED


def test_claim_is_atomic_exactly_once(store):
    job = _job()
    store.create_job(job)
    winners = [
        store.claim_job([QueueName.USER.value], worker_id=f"w{i}") for i in range(50)
    ]
    claimed = [w for w in winners if w is not None]
    assert len(claimed) == 1
    assert claimed[0].id == job.id
    assert claimed[0].attempts == 1


def test_claim_respects_priority_then_fifo(store):
    low = _job(priority=100, type="low")
    high = _job(priority=900, type="high")
    mixed = _job(priority=500, type="mid")
    for j in (low, high, mixed):
        store.create_job(j)
    first = store.claim_job([QueueName.USER.value], worker_id="w")
    assert first.type == "high"
    second = store.claim_job([QueueName.USER.value], worker_id="w")
    assert second.type == "mid"
    third = store.claim_job([QueueName.USER.value], worker_id="w")
    assert third.type == "low"


def test_claim_honours_available_at(store):
    future = _job(available_at=time.time() + 3600)
    store.create_job(future)
    assert store.claim_job([QueueName.USER.value], worker_id="w") is None


def test_lease_expiry_and_renew(store):
    job = _job()
    store.create_job(job)
    claimed = store.claim_job([QueueName.USER.value], worker_id="w1", lease_seconds=5)
    assert claimed is not None
    assert store.expired_running_jobs(moment=time.time() + 1) == []
    expired = store.expired_running_jobs(moment=time.time() + 10)
    assert [j.id for j in expired] == [job.id]
    assert store.renew_lease(job.id, worker_id="w1", lease_seconds=30)
    assert store.expired_running_jobs(moment=time.time() + 10) == []


def test_requeue_for_retry_then_claimable(store):
    job = _job()
    store.create_job(job)
    store.claim_job([QueueName.USER.value], worker_id="w1")
    store.requeue_for_retry(job.id, available_at=time.time() - 1, error="boom",
                            error_class="NETWORK_ERROR")
    got = store.get_job(job.id)
    assert got.state == JobState.QUEUED
    again = store.claim_job([QueueName.USER.value], worker_id="w2")
    assert again is not None and again.attempts == 2


def test_dead_letter_and_listing(store):
    job = _job()
    store.create_job(job)
    store.claim_job([QueueName.USER.value], worker_id="w1")
    store.to_dead_letter(job.id, error="exhausted", error_class="NETWORK_ERROR")
    assert [j.id for j in store.dlq_jobs()] == [job.id]


def test_idempotency_store(store):
    assert store.idempotency_get("k") is None
    store.idempotency_put("k", "job_1")
    assert store.idempotency_get("k") == "job_1"
    # A second put does not overwrite.
    store.idempotency_put("k", "job_2")
    assert store.idempotency_get("k") == "job_1"


def test_distributed_lock_ownership_and_expiry(store):
    now = time.time()
    assert store.try_acquire_lock("universe", owner="a", token="ta", ttl_ms=1000, moment=now)
    # Held: another owner is refused.
    assert not store.try_acquire_lock("universe", owner="b", token="tb", ttl_ms=1000, moment=now + 0.1)
    # Wrong token cannot release.
    assert not store.release_lock("universe", token="tb")
    # After expiry the lock is stealable.
    assert store.try_acquire_lock("universe", owner="b", token="tb", ttl_ms=1000, moment=now + 2)
    assert store.release_lock("universe", token="tb")
    assert store.get_lock("universe") is None


def test_queue_stats_and_counts(store):
    a = _job(queue=QueueName.MARKET.value)
    b = _job(queue=QueueName.MARKET.value)
    store.create_job(a)
    store.create_job(b)
    store.claim_job([QueueName.MARKET.value], worker_id="w")
    stats = {row["queue"]: row for row in store.queue_stats()}
    assert stats[QueueName.MARKET.value]["waiting"] == 1
    assert stats[QueueName.MARKET.value]["active"] == 1
    assert store.status_counts()[JobState.QUEUED.value] == 1


def test_worker_registry_persistence(store):
    info = WorkerInfo(id="wrk_1", kind="agent", queue="agent", concurrency=2, pid=1234)
    store.upsert_worker(info)
    assert store.list_workers()[0]["id"] == "wrk_1"
    store.heartbeat_worker("wrk_1", status="BUSY", active_jobs=1)
    assert store.list_workers()[0]["activeJobs"] == 1
    store.remove_worker("wrk_1")
    assert store.list_workers() == []
