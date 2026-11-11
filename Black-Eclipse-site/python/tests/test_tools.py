"""Tool registry: validation, permission, timeout, failure, lookup."""

from __future__ import annotations

import asyncio

import pytest

from harness.tools import DataBridge, ToolContext, ToolDefinition, ToolRegistry


def make_tool(name: str = "echo", **overrides) -> ToolDefinition:
    async def handler(args, ctx):
        return f"ok:{args.get('symbol')}"

    defaults = dict(
        name=name,
        description=f"{name} tool",
        input_schema={
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
        handler=overrides.pop("handler", handler),
        timeout_ms=overrides.pop("timeout_ms", 5000),
    )
    defaults.update(overrides)
    return ToolDefinition(**defaults)


def ctx() -> ToolContext:
    return ToolContext(run_id="r1", log=lambda *_: None, data_bridge=None)


@pytest.mark.asyncio
async def test_executes_valid_call():
    reg = ToolRegistry()
    reg.register(make_tool())
    result = await reg.execute("echo", "c1", {"symbol": "AAPL"}, ctx())
    assert result.ok
    assert result.text == "ok:AAPL"


@pytest.mark.asyncio
async def test_lookup_and_listing():
    reg = ToolRegistry()
    reg.register(make_tool("a"))
    reg.register(make_tool("b"))
    assert reg.get("a") is not None
    assert set(reg.names()) == {"a", "b"}
    assert {s["name"] for s in reg.schemas()} == {"a", "b"}


def test_rejects_duplicate_and_invalid_names():
    reg = ToolRegistry()
    reg.register(make_tool("ok_name"))
    with pytest.raises(ValueError):
        reg.register(make_tool("ok_name"))
    with pytest.raises(ValueError):
        reg.register(make_tool("bad name"))


@pytest.mark.asyncio
async def test_unknown_tool():
    reg = ToolRegistry()
    result = await reg.execute("nope", "c1", {}, ctx())
    assert not result.ok
    assert result.error.code == "TOOL_NOT_FOUND"


@pytest.mark.asyncio
async def test_validation_rejects_bad_input():
    reg = ToolRegistry()
    reg.register(make_tool())
    result = await reg.execute("echo", "c1", {}, ctx())
    assert not result.ok
    assert result.error.code == "TOOL_VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_allowlist_enforced():
    reg = ToolRegistry()
    reg.register(make_tool())
    result = await reg.execute("echo", "c1", {"symbol": "X"}, ctx(), allowed={"other"})
    assert not result.ok
    assert result.error.code == "TOOL_FORBIDDEN"


@pytest.mark.asyncio
async def test_non_read_tools_refused():
    reg = ToolRegistry()
    reg.register(make_tool(permission="write"))
    result = await reg.execute("echo", "c1", {"symbol": "X"}, ctx())
    assert not result.ok
    assert result.error.code == "TOOL_FORBIDDEN"


@pytest.mark.asyncio
async def test_timeout():
    async def slow(args, c):
        await asyncio.sleep(2)
        return "late"

    reg = ToolRegistry()
    reg.register(make_tool(handler=slow, timeout_ms=50))
    result = await reg.execute("echo", "c1", {"symbol": "X"}, ctx())
    assert not result.ok
    assert result.error.code == "TOOL_TIMEOUT"


@pytest.mark.asyncio
async def test_timeout_holds_even_when_the_handler_swallows_cancellation():
    # A pathological handler that ignores CancelledError could previously hang
    # `asyncio.wait_for` (and the whole run) forever; the hard deadline must
    # still return TOOL_TIMEOUT.
    release = asyncio.Event()

    async def stubborn(args, c):
        while not release.is_set():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                continue
        return "late"

    reg = ToolRegistry()
    reg.register(make_tool(handler=stubborn, timeout_ms=100))
    result = await reg.execute("echo", "c1", {"symbol": "X"}, ctx())
    assert not result.ok
    assert result.error.code == "TOOL_TIMEOUT"
    release.set()
    await asyncio.sleep(0.05)  # let the abandoned handler exit cleanly


@pytest.mark.asyncio
async def test_handler_failure_is_structured():
    async def boom(args, c):
        raise RuntimeError("kaboom")

    reg = ToolRegistry()
    reg.register(make_tool(handler=boom))
    result = await reg.execute("echo", "c1", {"symbol": "X"}, ctx())
    assert not result.ok
    assert result.error.code == "TOOL_ERROR"
    assert "kaboom" in result.text


@pytest.mark.asyncio
async def test_enum_constrained_schema_rejects_bad_value():
    async def handler(args, c):
        return "ok"

    reg = ToolRegistry()
    reg.register(
        ToolDefinition(
            name="mkt",
            description="market",
            input_schema={
                "type": "object",
                "properties": {"market": {"type": "string", "enum": ["US", "PK"]}},
                "required": ["market"],
            },
            handler=handler,
        )
    )
    ok = await reg.execute("mkt", "c1", {"market": "US"}, ctx())
    assert ok.ok
    bad = await reg.execute("mkt", "c2", {"market": "XX"}, ctx())
    assert not bad.ok
    assert bad.error.code == "TOOL_VALIDATION_FAILED"


class FakeBridge(DataBridge):
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def fetch(self, capability, params):
        self.calls.append((capability, params))
        return self.payload


@pytest.mark.asyncio
async def test_finance_tool_reports_unavailable_without_inventing_data():
    from harness.finance_tools import register_finance_tools

    reg = ToolRegistry()
    register_finance_tools(reg)
    bridge = FakeBridge({"status": "UNAVAILABLE"})
    c = ToolContext(run_id="r1", log=lambda *_: None, data_bridge=bridge)
    result = await reg.execute("get_market_snapshot", "c1", {"symbol": "ZZZZ"}, c)
    assert result.ok
    assert "UNAVAILABLE" in result.text
    assert bridge.calls[0][0] == "market_snapshot"


@pytest.mark.asyncio
async def test_finance_tool_returns_grounded_snapshot():
    from harness.finance_tools import register_finance_tools

    reg = ToolRegistry()
    register_finance_tools(reg)
    bridge = FakeBridge(
        {
            "status": "OK",
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "exchange": "NASDAQ",
            "country": "US",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "securityType": "Common Stock",
            "priceSource": "scraper",
            "updatedAt": "2026-09-20T12:00:00.000Z",
            "price": {"price": 237.42, "changePct": 1.23, "marketCap": None, "volume": None, "peRatio": None},
        }
    )
    c = ToolContext(run_id="r1", log=lambda *_: None, data_bridge=bridge)
    result = await reg.execute("get_market_snapshot", "c1", {"symbol": "aapl"}, c)
    assert result.ok
    assert "237.42" in result.text
    # Phase 13 follow-up: provenance is now PER FIELD. With a stale vault row and
    # no live provider, the snapshot is labelled a saved reading and names its
    # stored source rather than a blanket "Data source: JDDS (scraper)".
    assert "saved snapshot" in result.text.lower()
    assert "JDDS/scraper" in result.text


@pytest.mark.asyncio
async def test_active_context_is_isolated_between_concurrent_runs():
    """Two runs sharing the registry must not overwrite each other's context."""
    from harness import tools as tools_mod

    reg = ToolRegistry()

    async def worker(run_id: str) -> str:
        reg.set_active_context(ToolContext(run_id=run_id, log=lambda *_: None))
        await asyncio.sleep(0)
        current = tools_mod._ACTIVE_CTX.get()
        return current.run_id if current is not None else "missing"

    assert await asyncio.gather(worker("run_a"), worker("run_b")) == ["run_a", "run_b"]


@pytest.mark.asyncio
async def test_langchain_tool_view_is_bound():
    reg = ToolRegistry()
    reg.register(make_tool())
    tools = reg.langchain_tools({"echo"})
    assert [t.name for t in tools] == ["echo"]
    reg.set_active_context(ctx())
    out = await tools[0].ainvoke({"symbol": "MSFT"})
    assert out == "ok:MSFT"
