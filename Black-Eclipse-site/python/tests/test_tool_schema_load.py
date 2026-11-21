"""Schema-on-demand: exact parameters, bounded, and never outside the allowlist."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from harness import tool_schema_load as T
from harness.tools import ToolDefinition, ToolRegistry


def _tool(name: str, *, params=None, description="A tool.") -> ToolDefinition:
    async def handler(args, ctx):  # pragma: no cover - never called here
        return "ok"

    return ToolDefinition(
        name=name,
        description=description,
        input_schema=params or {"type": "object", "properties": {}, "required": []},
        handler=handler,
        permission="read",
        risk="low",
    )


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_tool("market_quote", params={
        "type": "object",
        "properties": {"symbol": {"type": "string"}},
        "required": ["symbol"],
    }))
    registry.register(_tool("quant_backtest"))
    return registry


def _call(payload, *, registry=None, allowed=None):
    tool = T.build_tool()
    ctx = SimpleNamespace(tool_registry=registry, allowed=allowed)
    return json.loads(asyncio.run(tool.handler(payload, ctx)))


def test_install_registers_once_and_is_read_only():
    registry = _registry()
    assert T.install_tool_schema_load(registry) is True
    assert T.install_tool_schema_load(registry) is False
    tool = registry.get(T.NAME)
    assert tool is not None
    assert tool.permission == "read"
    assert tool.risk == "none"


def test_returns_the_exact_schema():
    result = _call({"names": ["market_quote"]}, registry=_registry())
    assert result["refused"] == []
    loaded = result["loaded"][0]
    assert loaded["name"] == "market_quote"
    params = json.loads(loaded["parametersJson"])
    assert params["required"] == ["symbol"]


def test_refuses_a_tool_outside_the_allowlist():
    result = _call({"names": ["quant_backtest"]}, registry=_registry(), allowed={"market_quote"})
    assert result["loaded"] == []
    assert result["refused"][0]["reason"] == "outside_allowlist"


def test_refuses_an_unknown_name():
    result = _call({"names": ["does_not_exist"]}, registry=_registry(), allowed=None)
    assert result["refused"][0]["reason"] == "unknown_tool"


def test_unrestricted_allowlist_permits_any_registered_tool():
    result = _call({"names": ["quant_backtest"]}, registry=_registry(), allowed=None)
    assert result["loaded"][0]["name"] == "quant_backtest"


def test_caps_the_number_of_tools_per_call():
    result = _call({"names": ["a"] * (T.MAX_TOOLS_PER_CALL + 1)}, registry=_registry())
    assert "error" in result


def test_rejects_an_empty_or_malformed_request():
    assert "error" in _call({"names": []}, registry=_registry())
    assert "error" in _call({"names": "market_quote"}, registry=_registry())


def test_bounds_a_huge_schema_and_flags_truncation():
    huge = {"type": "object", "properties": {f"k{i}": {"type": "string", "description": "x" * 200}
                                             for i in range(200)}}
    registry = ToolRegistry()
    registry.register(_tool("huge", params=huge))
    result = _call({"names": ["huge"]}, registry=registry)
    loaded = result["loaded"][0]
    assert loaded["parametersTruncated"] is True
    assert len(loaded["parametersJson"]) <= T.MAX_PARAM_CHARS


def test_is_bound_when_progressive_disclosure_narrows():
    from harness.tool_disclosure import CORE_TOOLS

    assert T.NAME in CORE_TOOLS
