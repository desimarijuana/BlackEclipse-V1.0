"""Post-landing canary: restart -> probe -> keep/rollback, never auto-promote."""

from __future__ import annotations

import asyncio

import pytest

from harness.persistence import AgentMemoryStore
from harness.self_improvement.post_landing import (
    PostLandingPolicy,
    PostLandingStore,
    run_post_landing,
)


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


@pytest.mark.asyncio
async def test_healthy_restart_is_kept(store):
    calls = {"restart": 0, "rollback": 0}

    def restart():
        calls["restart"] += 1

    record = await run_post_landing(
        store=store,
        run_id="rsl-cand-1",
        rollback_id="rollback-1",
        restart=restart,
        verify=lambda: True,
        rollback=lambda _id: calls.update(rollback=calls["rollback"] + 1),
    )

    assert record["status"] == "healthy"
    assert calls == {"restart": 1, "rollback": 0}
    assert PostLandingStore(store).get(record["id"])["status"] == "healthy"


@pytest.mark.asyncio
async def test_unhealthy_landing_is_rolled_back_and_reprobed(store):
    calls = {"restart": 0, "rollback": 0}
    probes = [False, True]

    def restart():
        calls["restart"] += 1

    def verify():
        return probes.pop(0)

    record = await run_post_landing(
        store=store,
        run_id="rsl-cand-2",
        rollback_id="rollback-2",
        restart=restart,
        verify=verify,
        rollback=lambda _id: calls.update(rollback=calls["rollback"] + 1),
    )

    assert record["status"] == "rolled_back"
    assert calls == {"restart": 2, "rollback": 1}
    assert record["evidence"]["health"] is False
    assert record["evidence"]["secondHealth"] is True
    assert "put back" in record["reason"].lower()


@pytest.mark.asyncio
async def test_failed_restart_puts_the_previous_files_back(store):
    calls = {"rollback": 0}

    def restart():
        raise RuntimeError("supervisor refused")

    record = await run_post_landing(
        store=store,
        run_id="rsl-cand-7",
        rollback_id="rollback-7",
        restart=restart,
        verify=lambda: True,
        rollback=lambda _id: calls.update(rollback=calls["rollback"] + 1),
    )

    assert record["status"] == "restart_failed"
    assert calls["rollback"] == 1
    assert record["evidence"]["rollback"] == "ok"
    assert "put back" in record["reason"].lower()


@pytest.mark.asyncio
async def test_no_restart_seam_is_unverified_not_success(store):
    record = await run_post_landing(
        store=store,
        run_id="rsl-cand-3",
        rollback_id="rollback-3",
        restart=None,
        verify=lambda: True,
    )

    assert record["status"] == "unverified"
    assert record["reason"] == "NO_RESTART_SEAM"


@pytest.mark.asyncio
async def test_failed_rollback_is_visible(store):
    calls = {"restart": 0}

    def restart():
        calls["restart"] += 1

    def rollback(_id):
        raise RuntimeError("disk locked")

    record = await run_post_landing(
        store=store,
        run_id="rsl-cand-4",
        rollback_id="rollback-4",
        restart=restart,
        verify=lambda: False,
        rollback=rollback,
    )

    assert record["status"] == "rollback_failed"
    assert "disk locked" not in record["reason"]
    assert record["evidence"]["rollback"].startswith("error:RuntimeError")


@pytest.mark.asyncio
async def test_front_door_restart_probes_without_restarting_again(store):
    calls = {"rollback": 0}

    record = await run_post_landing(
        store=store,
        run_id="rsl-cand-6",
        rollback_id="rollback-6",
        restart=None,
        verify=lambda: False,
        rollback=lambda _id: calls.update(rollback=calls["rollback"] + 1),
        restart_already_done=True,
    )

    assert calls["rollback"] == 1
    assert record["status"] == "rolled_back"
    assert record["evidence"]["restart"] == "already_done"
    assert record["evidence"]["secondRestart"] == "required"


@pytest.mark.asyncio
async def test_verify_timeout_is_a_failure(store):
    calls = {"restart": 0, "rollback": 0}

    def restart():
        calls["restart"] += 1

    async def verify():
        await asyncio.sleep(5)
        return True

    record = await run_post_landing(
        store=store,
        run_id="rsl-cand-5",
        rollback_id="rollback-5",
        restart=restart,
        verify=verify,
        rollback=lambda _id: calls.update(rollback=calls["rollback"] + 1),
        policy=PostLandingPolicy(timeout_seconds=0.05),
    )

    # The first probe timed out; rollback ran; the second probe also timed out.
    assert calls == {"restart": 2, "rollback": 1}
    assert record["status"] == "unverified"
    assert record["evidence"]["health"] == "timeout"
