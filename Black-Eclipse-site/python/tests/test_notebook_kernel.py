"""Phase 21 — a notebook keeps its variables; an ordinary analysis does not.

The kernel process is shared, but the NAMESPACE is a deliberate choice: a
notebook cell opts in (`persist_namespace=True`) and a later cell can use an
earlier cell's variable; `analysis_run` never sends the flag, so an agent
analysis still starts from a clean dictionary.
"""

from __future__ import annotations

import pytest

from harness.code import sandbox as sandbox_mod
from harness.code.execution import AnalysisRequest, interpreter_path
from harness.code.kernel import KernelPool


def _has_runner() -> bool:
    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        return False
    return bool(interpreter_path())


pytestmark = pytest.mark.skipif(not _has_runner(), reason="no isolation primitive")


def _request(source: str, *, persist: bool) -> AnalysisRequest:
    return AnalysisRequest(
        source=source,
        purpose="notebook namespace test",
        timeout_s=30,
        persist_namespace=persist,
    )


@pytest.fixture()
def pool():
    item = KernelPool(max_kernels=2, idle_s=30.0)
    try:
        yield item
    finally:
        item.close_all()


def test_notebook_variables_survive_between_cells(pool):
    kernel = pool.acquire("session:nb|agent:eclipse-agent")
    assert kernel is not None
    first = kernel.execute(_request("x = 41\nresult = {'x': x}", persist=True))
    assert first.status == "ok", first.stderr
    second = kernel.execute(_request("result = {'x': x + 1}", persist=True))
    assert second.status == "ok", second.stderr
    assert second.outputs["x"] == 42


def test_an_ordinary_analysis_starts_with_a_fresh_namespace(pool):
    kernel = pool.acquire("session:nb|agent:eclipse-agent")
    assert kernel is not None
    assert kernel.execute(_request("x = 41\nresult = {'x': x}", persist=True)).status == "ok"
    # `analysis_run` path: persistent=False, so `x` must be absent.
    fresh = kernel.execute(_request("result = {'x': x}", persist=False))
    assert fresh.status != "ok"
    # ... and the notebook namespace is still intact.
    again = kernel.execute(_request("result = {'x': x}", persist=True))
    assert again.status == "ok", again.stderr
    assert again.outputs["x"] == 41


def test_restart_drops_the_namespace(pool):
    key = "session:nb-restart|agent:eclipse-agent"
    kernel = pool.acquire(key)
    assert kernel is not None
    assert kernel.execute(_request("x = 7\nresult = {'x': x}", persist=True)).status == "ok"
    pool.drop(key)
    replacement = pool.acquire(key)
    assert replacement is not None
    result = replacement.execute(_request("result = {'x': x}", persist=True))
    assert result.status != "ok"
