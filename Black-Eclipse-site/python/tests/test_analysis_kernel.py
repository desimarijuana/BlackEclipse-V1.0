"""The persistent analysis kernel: reuse, isolation, bounds and honest failure.

The kernel is an EXECUTION STRATEGY for `run_analysis`, so these tests pin the
things the one-shot runner cannot show: the same process serves repeated rounds
in one conversation, different conversations never share a process, the pool is
bounded and idle-expires, a crash is reported (`KERNEL_CRASHED`) instead of being
silently retried, and a spawn failure degrades to the one-shot runner.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from harness.code import kernel as kernel_mod
from harness.code import sandbox as sandbox_mod
from harness.code.execution import (
    AnalysisRequest,
    interpreter_path,
    run_analysis,
)
from harness.code.kernel import Kernel, KernelPool, kernel_key


def _has_runner() -> bool:
    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        return False
    return bool(interpreter_path())


pytestmark = pytest.mark.skipif(not _has_runner(), reason="no isolation primitive")


def _request(source: str, **overrides) -> AnalysisRequest:
    base = dict(source=source, purpose="kernel test", timeout_s=30)
    base.update(overrides)
    return AnalysisRequest(**base)


@pytest.fixture()
def pool():
    pools: list[KernelPool] = []

    def make(max_kernels: int = 4, idle_s: float = 300.0) -> KernelPool:
        item = KernelPool(max_kernels=max_kernels, idle_s=idle_s)
        pools.append(item)
        return item

    yield make
    for item in pools:
        item.close_all()


def _pid(kernel: Kernel) -> int:
    return int(kernel.spawned.proc.pid or 0)


def test_same_conversation_reuses_one_process(pool):
    item = pool()
    first = item.acquire("session:s1|agent:a")
    assert first is not None
    try:
        assert first.execute(_request("result = {'n': 1}")).status == "ok"
        second = item.acquire("session:s1|agent:a")
        assert second is first
        assert _pid(second) == _pid(first)
        result = second.execute(_request("result = {'n': int(inputs['n']) + 1}",
                                         inputs=[{"name": "n", "kind": "scalar", "value": 2}]))
        assert result.status == "ok"
        assert result.outputs["n"] == 3
        assert _pid(second) == _pid(first)
    finally:
        item.close_all()


def test_conversations_do_not_share_a_process(pool):
    item = pool()
    left = item.acquire("session:left|agent:a")
    right = item.acquire("session:right|agent:a")
    assert left is not None and right is not None
    try:
        assert _pid(left) != _pid(right)
        left.execute(_request("result = {'who': 'left'}"))
        right.execute(_request("result = {'who': 'right'}"))
        assert _pid(left) != _pid(right)
    finally:
        item.close_all()


def test_tool_replay_works_across_kernel_rounds(pool):
    item = pool()
    kernel = item.acquire("session:tools|agent:a")
    assert kernel is not None
    calls: list[str] = []

    def resolver(capability: str, params: dict) -> dict:
        calls.append(capability)
        return {"status": "OK", "price": 10.0}

    source = (
        "import eclipse_tools\n"
        "quote = eclipse_tools.live_quote(symbol='AAPL')\n"
        "result = {'price': quote['price']}\n"
    )
    try:
        result = kernel.execute(
            _request(source, allow_tools=True), tool_resolver=resolver,
        )
        assert result.status == "ok", result.stderr
        assert result.outputs["price"] == 10.0
        assert calls == ["live_quote"]
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "live_quote"
        assert result.tool_calls[0].status == "OK"
        # The replay channel records metadata only: the fetched payload itself is
        # never part of the tool-call record.
        assert "10.0" not in result.tool_calls[0].model_dump_json()
    finally:
        item.close_all()


def test_dead_kernel_reports_crashed_and_pool_respawns(pool):
    item = pool()
    first = item.acquire("session:crash|agent:a")
    assert first is not None
    try:
        first.spawned.proc.kill()
        first.spawned.proc.wait(timeout=10)
        failed = first.execute(_request("result = {'n': 1}"))
        assert failed.status == "failed"
        assert failed.code == kernel_mod.KERNEL_CRASHED
        second = item.acquire("session:crash|agent:a")
        assert second is not None and second is not first
        assert second.execute(_request("result = {'n': 2}")).status == "ok"
    finally:
        item.close_all()


def test_pool_evicts_the_oldest_kernel_at_capacity(pool):
    item = pool(max_kernels=1)
    first = item.acquire("session:one|agent:a")
    assert first is not None
    second = item.acquire("session:two|agent:a")
    assert second is not None
    try:
        assert not first.spawned.alive()
        assert second.spawned.alive()
    finally:
        item.close_all()


def test_pool_sweeps_idle_kernels(pool):
    item = pool(max_kernels=4, idle_s=1.0)
    first = item.acquire("session:idle|agent:a")
    assert first is not None
    try:
        time.sleep(1.2)
        second = item.acquire("session:other|agent:a")
        assert second is not None
        assert not first.spawned.alive()
        assert second.spawned.alive()
    finally:
        item.close_all()


def test_spawn_failure_degrades_to_one_shot(monkeypatch, pool):
    item = pool()

    def refuse(spec, **kwargs):
        raise sandbox_mod.SandboxUnavailable("no kernel for this test")

    monkeypatch.setattr(sandbox_mod, "spawn", refuse)
    assert item.acquire("session:fallback|agent:a") is None
    result = run_analysis(
        _request("result = {'ok': True}"), kernel=None,
    )
    assert result.status == "ok"


def test_spawn_refuses_network(monkeypatch):
    spec = sandbox_mod.RunSpec(
        argv=["python", "-c", "pass"], cwd=Path("."),
        env={}, timeout_s=1, output_cap_bytes=1, network=True,
    )
    with pytest.raises(sandbox_mod.SandboxUnavailable):
        sandbox_mod.spawn(spec)


def test_kernel_key_separates_delegated_runs():
    class Ctx:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    chat = Ctx(run_id="r1", session_id="s1", agent_id="a", delegation_depth=0)
    child = Ctx(run_id="r2", session_id="s1", agent_id="a", delegation_depth=1)
    other_chat = Ctx(run_id="r2", session_id="s2", agent_id="a", delegation_depth=0)
    assert kernel_key(chat) == kernel_key(Ctx(run_id="r9", session_id="s1", agent_id="a", delegation_depth=0))
    assert kernel_key(child) != kernel_key(chat)
    assert kernel_key(other_chat) != kernel_key(chat)
    assert kernel_key(child) == kernel_key(Ctx(run_id="r2", session_id="s1", agent_id="a", delegation_depth=2))


def test_env_flag_disables_the_pool(monkeypatch):
    monkeypatch.setenv("ECLIPSE_ANALYSIS_KERNEL", "0")
    kernel_mod.reset_kernel_pool()
    try:
        assert kernel_mod.get_pool() is None
    finally:
        monkeypatch.delenv("ECLIPSE_ANALYSIS_KERNEL", raising=False)
        kernel_mod.reset_kernel_pool()
