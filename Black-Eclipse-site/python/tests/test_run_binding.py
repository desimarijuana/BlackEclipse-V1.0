"""Per-run bindings must never leak across concurrent runs (multi-session).

The market gateway and MCP manager are process-wide singletons. Before this,
each run rewrote their bridge/model, so two concurrent chat sessions used each
other's transport and model. `run_binding` carries those values in a ContextVar
instead: every run task inherits its own copy.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from harness.mcp.manager import MCPManager
from harness.run_binding import (
    bind_run,
    current_bridge,
    current_sampling_factory,
)


class _Bridge:
    def __init__(self, name: str) -> None:
        self.name = name


@pytest.mark.asyncio
async def test_concurrent_tasks_keep_their_own_bridge_and_factory():
    async def worker(name: str) -> tuple[str, str]:
        async def factory(_policy: object, prompt: str) -> str:
            return f"{name}:{prompt}"

        with bind_run(bridge=_Bridge(name), sampling_factory=factory):
            await asyncio.sleep(0)  # force the tasks to interleave
            bridge = current_bridge()
            model = current_sampling_factory()
            assert bridge is not None and model is not None
            return bridge.name, await model(None, "hello")

    a, b = await asyncio.gather(worker("run_a"), worker("run_b"))
    assert a == ("run_a", "run_a:hello")
    assert b == ("run_b", "run_b:hello")


@pytest.mark.asyncio
async def test_current_binding_falls_back_outside_a_run():
    assert current_bridge("default") == "default"
    assert current_sampling_factory("default") == "default"


@pytest.mark.asyncio
async def test_mcp_sampling_uses_the_run_binding_not_the_process_default():
    manager = MCPManager.__new__(MCPManager)
    manager._sampling_model_factory = None  # no process-wide default
    run_model = manager._make_sampling_callable(SimpleNamespace(sampling="policy"))

    async def factory(policy: object, prompt: str) -> str:
        assert policy == "policy"
        return f"answered:{prompt}"

    with bind_run(sampling_factory=factory):
        assert await run_model("ping") == "answered:ping"

    with pytest.raises(Exception):
        await run_model("outside")
