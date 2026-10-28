"""Read-only tool-contract shadow: classify, never grant."""

from __future__ import annotations

import asyncio

from harness.self_improvement.tool_shadow import shadow_report
from harness.tools import ToolDefinition, ToolRegistry


async def _handler(args, ctx):
    return "ok", {}


def _tool(name, *, permission="read", risk="low", effect=None):
    return ToolDefinition(
        name=name,
        description=f"{name} test tool",
        input_schema={"type": "object", "properties": {}},
        handler=_handler,
        permission=permission,
        risk=risk,
        effect=effect,
        timeout_ms=1000,
    )


def test_shadow_report_classifies_without_granting():
    registry = ToolRegistry()
    for tool in (
        _tool("market_read_test"),
        _tool("write_test", permission="write", effect="write"),
        _tool("place_order", permission="read"),
        _tool("capability_activate", permission="read"),
        _tool("blocked_read"),
        _tool("market_get_quote"),
    ):
        registry.register(tool)
    before = registry.names()

    report = shadow_report(
        registry,
        granted_tools={"market_get_quote"},
        blocked_tools={"blocked_read"},
    )
    rows = {row["name"]: row for row in report["rows"]}
    assert rows["market_read_test"]["status"] == "eligible_shadow"
    assert "not_read_permission" in rows["write_test"]["reasons"]
    assert "financial_action" in rows["place_order"]["reasons"]
    assert "mechanism" in rows["capability_activate"]["reasons"]
    assert "blocked_tool" in rows["blocked_read"]["reasons"]
    assert "market_get_quote" not in rows
    assert report["counts"]["eligible"] == 1
    assert registry.names() == before
