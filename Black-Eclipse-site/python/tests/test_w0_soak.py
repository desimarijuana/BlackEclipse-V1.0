"""W0 lifecycle soak: every run reaches a terminal state."""

from __future__ import annotations

import pytest

from harness.evaluation.w0_soak import run_soak


@pytest.mark.asyncio
async def test_soak_runs_sequential_and_concurrent():
    report = await run_soak(
        sequential=3,
        concurrent=2,
        label="pytest-soak",
        commit="test",
    )
    assert report["soak"]["runs"] == 5
    assert report["soak"]["byStatus"] == {"completed": 5}
    assert report["soak"]["crashed"] == []
    assert report["metrics"]["runs"]["total"]["value"] == 5
    assert report["metrics"]["runs"]["terminalCorrectness"]["value"] == 1.0
    # The scripted model reports no usage, so token metrics stay honest unknowns.
    assert report["metrics"]["runs"]["promptTokens"]["measured"] is False
