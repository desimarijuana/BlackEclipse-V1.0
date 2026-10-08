"""Tests for the in-process background run runner (status, progress, cancel)."""

from __future__ import annotations

import asyncio

from harness.quant.runner import get_runner, reset_runner


async def _wait_terminal(runner, run_id, timeout=2.0):
    for _ in range(int(timeout / 0.01)):
        view = runner.get(run_id)
        if view and view["status"] in ("completed", "failed", "cancelled"):
            return view
        await asyncio.sleep(0.01)
    return runner.get(run_id)


async def test_run_completes_with_result_and_progress():
    reset_runner()
    runner = get_runner()

    async def work(progress):
        progress("evaluating", 1, 2)
        progress("evaluating", 2, 2)
        return {"value": 42}

    run_id = runner.submit("optimization", work)
    view = await _wait_terminal(runner, run_id)
    assert view["status"] == "completed"
    assert view["percent"] == 100.0
    assert runner.get(run_id, include_result=True)["result"] == {"value": 42}
    assert runner.result(run_id) == {"value": 42}


async def test_run_failure_is_recorded():
    reset_runner()
    runner = get_runner()

    async def boom(progress):
        raise ValueError("nope")

    run_id = runner.submit("backtest", boom)
    view = await _wait_terminal(runner, run_id)
    assert view["status"] == "failed"
    assert "nope" in view["error"]["message"]
    assert runner.result(run_id) is None


async def test_run_can_be_cancelled():
    reset_runner()
    runner = get_runner()
    started = asyncio.Event()

    async def forever(progress):
        started.set()
        await asyncio.sleep(10)
        return {}

    run_id = runner.submit("monte_carlo", forever)
    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert runner.cancel(run_id) is True
    view = await _wait_terminal(runner, run_id)
    assert view["status"] == "cancelled"
    # A terminal run cannot be cancelled twice.
    assert runner.cancel(run_id) is False


async def test_list_returns_runs():
    reset_runner()
    runner = get_runner()

    async def work(progress):
        return {"ok": True}

    run_id = runner.submit("sensitivity", work)
    await _wait_terminal(runner, run_id)
    listed = runner.list()
    assert any(r["runId"] == run_id for r in listed)
    assert runner.get("does_not_exist") is None
