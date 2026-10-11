"""Background runner — submit, progress, result, cancel, persistence mirror."""

from __future__ import annotations

import asyncio

import pytest

from harness.stats.runner import StatsRunner, reset_runner


@pytest.fixture(autouse=True)
def _reset():
    reset_runner()
    yield
    reset_runner()


async def test_submit_and_complete():
    runner = StatsRunner(max_concurrent=2)

    async def factory(progress):
        progress("stage1", 1, 2)
        await asyncio.sleep(0)
        progress("stage2", 2, 2)
        return {"ok": True}

    run_id = runner.submit("analysis", factory)
    for _ in range(50):
        if runner.get(run_id)["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.01)
    run = runner.get(run_id, include_result=True)
    assert run["status"] == "completed"
    assert run["result"] == {"ok": True}
    assert run["percent"] == 100.0


async def test_failure_is_data_not_crash():
    runner = StatsRunner()

    async def factory(progress):
        raise ValueError("boom")

    run_id = runner.submit("analysis", factory)
    for _ in range(50):
        if runner.get(run_id)["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.01)
    run = runner.get(run_id)
    assert run["status"] == "failed"
    assert "boom" in run["error"]["message"]


async def test_cancel_running_job():
    runner = StatsRunner()

    async def factory(progress):
        await asyncio.sleep(5)
        return {}

    run_id = runner.submit("analysis", factory)
    await asyncio.sleep(0.01)
    assert runner.cancel(run_id) is True
    assert runner.get(run_id)["status"] == "cancelled"


async def test_states_mirror_to_store(tmp_path):
    from harness.persistence import AgentMemoryStore
    from harness.stats.store import StatsStore

    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = StatsStore(ams, artifact_root=str(tmp_path / "art"))
    runner = StatsRunner(store=store)

    async def factory(progress):
        progress("go", 1, 1)
        return {"done": True}

    run_id = runner.submit("analysis", factory)
    for _ in range(50):
        if runner.get(run_id)["status"] == "completed":
            break
        await asyncio.sleep(0.01)
    row = store._db.execute("SELECT status FROM StatsRun WHERE id=?", (run_id,)).fetchone()
    assert row is not None and row["status"] == "completed"
