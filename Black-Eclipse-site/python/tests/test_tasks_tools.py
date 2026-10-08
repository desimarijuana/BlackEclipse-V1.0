"""The LLM-facing task tools execute through the shared ToolRegistry."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.tasks.tools import TASK_TOOLS, register_task_tools
from harness.tools import ToolContext, ToolRegistry


@pytest.fixture()
def ctx(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    return ToolContext(run_id="run-1", log=lambda *a, **k: None, memory_store=store)


@pytest.fixture()
def registry():
    reg = ToolRegistry()
    names = register_task_tools(reg)
    assert set(names) == set(TASK_TOOLS)
    return reg


async def _call(registry, ctx, name, args):
    return await registry.execute(name, "c1", args, ctx)


@pytest.mark.asyncio
async def test_create_plan_task_and_complete(registry, ctx):
    res = await _call(registry, ctx, "create_plan", {"name": "Compare"})
    assert res.ok
    plan_id = res.data["plan"]["id"]

    res = await _call(registry, ctx, "create_task", {
        "title": "Research NVDA", "planId": plan_id,
        "acceptanceCriteria": [{"text": "10-K obtained"}],
    })
    assert res.ok
    task_id = res.data["task"]["id"]

    # Completion is refused until the criterion passes.
    res = await _call(registry, ctx, "complete_task", {"taskId": task_id})
    assert not res.data["ok"]
    assert res.data["code"] == "COMPLETION_REJECTED"

    view = (await _call(registry, ctx, "read_task", {"taskId": task_id})).data["task"]
    crit_id = view["criteria"][0]["id"]
    await _call(registry, ctx, "set_task_criterion",
                {"criterionId": crit_id, "state": "PASSED"})

    res = await _call(registry, ctx, "complete_task", {"taskId": task_id})
    assert res.data["ok"]
    assert res.data["task"]["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_dependency_and_tree_tools(registry, ctx):
    plan_id = (await _call(registry, ctx, "create_plan", {"name": "P"})).data["plan"]["id"]
    a = (await _call(registry, ctx, "create_task", {"title": "A", "planId": plan_id})).data["task"]["id"]
    b = (await _call(registry, ctx, "create_task", {"title": "B", "planId": plan_id})).data["task"]["id"]
    res = await _call(registry, ctx, "add_dependency", {"taskId": b, "dependsOnTaskId": a})
    assert res.data["ok"]
    # Cycle is rejected through the tool surface too.
    res = await _call(registry, ctx, "add_dependency", {"taskId": a, "dependsOnTaskId": b})
    assert not res.data["ok"]
    assert res.data["code"] == "DEPENDENCY_CYCLE"
    res = await _call(registry, ctx, "read_plan", {"planId": plan_id})
    assert res.data["ok"]
    assert res.data["plan"]["stats"]["total"] == 2


@pytest.mark.asyncio
async def test_tools_are_registered_as_read_permission(registry):
    for name in TASK_TOOLS:
        tool = registry.get(name)
        assert tool is not None
        assert tool.permission == "read"
