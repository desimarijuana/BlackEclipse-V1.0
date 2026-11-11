"""Round 5 / C3: confined code over the READ-ONLY tool catalog."""

from __future__ import annotations

import pytest

from harness.code import sandbox
from harness.code_mode import MAX_TOOL_CALLS, run_code_mode
from harness.tools import ToolContext, ToolDefinition, ToolRegistry


def _registry() -> ToolRegistry:
    reg = ToolRegistry()

    async def echo(args, _ctx):
        return f"ok:{args.get('n')}", {"n": args.get("n")}

    async def writer(_args, _ctx):
        return "wrote"

    reg.register(ToolDefinition(
        name="echo", description="echo", input_schema={
            "type": "object", "properties": {"n": {"type": "integer"}},
        }, handler=echo, permission="read",
    ))
    reg.register(ToolDefinition(
        name="writer", description="write", input_schema={"type": "object", "properties": {}},
        handler=writer, permission="write",
    ))
    return reg


def _ctx(reg: ToolRegistry) -> ToolContext:
    return ToolContext(run_id="run_cm", log=lambda *_: None, tool_registry=reg)


@pytest.mark.asyncio
async def test_code_mode_is_disabled_without_the_operator_flag(monkeypatch):
    monkeypatch.delenv("HARNESS_CODE_MODE", raising=False)
    result = await run_code_mode("result = 1", ctx=_ctx(_registry()))
    assert result.ok is False
    assert "disabled" in result.error.lower()


@pytest.mark.asyncio
async def test_code_mode_runs_a_read_tool_and_returns_the_result(monkeypatch):
    if not sandbox.isolation_satisfied():
        pytest.skip("no process-isolation primitive on this host")
    monkeypatch.setenv("HARNESS_CODE_MODE", "1")
    result = await run_code_mode(
        "x = tools.call('echo', n=2)\nresult = x['n'] * 3\n",
        ctx=_ctx(_registry()),
    )
    assert result.ok is True, result.error
    assert "6" in result.output
    assert result.tool_calls == 1


@pytest.mark.asyncio
async def test_code_mode_refuses_an_effectful_tool(monkeypatch):
    if not sandbox.isolation_satisfied():
        pytest.skip("no process-isolation primitive on this host")
    monkeypatch.setenv("HARNESS_CODE_MODE", "1")
    result = await run_code_mode(
        "tools.call('writer')\nresult = 1\n",
        ctx=_ctx(_registry()),
    )
    assert result.ok is False
    assert "effectful" in result.error.lower()


def test_the_tool_call_budget_is_bounded():
    assert MAX_TOOL_CALLS == 20
