"""W3.3: BM25 search, tags/domain weighting, tiers and the disclosure decision."""

from __future__ import annotations

import json

import pytest

from harness.tool_bm25 import rank_tools, tokenize
from harness.tool_disclosure import (
    CORE_TOOLS,
    build_catalogue,
    disclosure_mode,
    resolve_disclosure,
)
from harness.tool_surface import register_tool_surface_tools
from harness.tools import ToolContext, ToolDefinition, ToolRegistry


def _tool(name, description, *, permission="read", domain="", tags=(), effect=None):
    async def _handler(_args, _ctx):
        return name

    return ToolDefinition(
        name=name, description=description,
        input_schema={"type": "object", "properties": {}},
        handler=_handler, permission=permission, domain=domain, tags=tuple(tags),
        effect=effect,
    )


def _registry(count: int = 40) -> ToolRegistry:
    reg = ToolRegistry()
    for index in range(count):
        reg.register(_tool(
            f"market_read_{index}",
            f"Read market series number {index} for prices and volume.",
            domain="market", tags=("quote", "price", "series"),
        ))
    reg.register(_tool(
        "market_get_quote", "Read the latest quote and last price for a symbol.",
        domain="market", tags=("quote", "price", "ticker"),
    ))
    reg.register(_tool(
        "options_implied_volatility", "Compute an option's implied volatility.",
        domain="quant", tags=("option", "iv", "vol"),
    ))
    reg.register(_tool(
        "portfolio_write", "Write a portfolio position.",
        permission="write", domain="portfolio", effect="write",
    ))
    reg.register(_tool(
        "ask_user", "Ask the user a clarifying question.",
        domain="chat",
    ))
    reg.get("ask_user").interactive = True  # type: ignore[union-attr]
    register_tool_surface_tools(reg)
    return reg


@pytest.mark.parametrize("raw,expected", [
    ("on", "on"), ("off", "off"), ("auto", "auto"),
])
def test_disclosure_mode_uses_the_registry(monkeypatch, raw, expected):
    monkeypatch.setenv("HARNESS_TOOL_DISCLOSURE", raw)
    assert disclosure_mode() == expected


def test_lazy_alias_is_honoured_only_when_the_registry_flag_is_absent(monkeypatch):
    monkeypatch.delenv("HARNESS_TOOL_DISCLOSURE", raising=False)
    monkeypatch.setenv("HARNESS_LAZY_TOOLS", "1")
    assert disclosure_mode() == "on"

    monkeypatch.setenv("HARNESS_TOOL_DISCLOSURE", "off")
    assert disclosure_mode() == "off"


def test_off_mode_never_narrows(monkeypatch):
    monkeypatch.setenv("HARNESS_TOOL_DISCLOSURE", "off")
    reg = _registry()
    allowed = set(reg.names())
    plan = resolve_disclosure(allowed, reg, window=200_000)
    assert not plan.enabled
    assert plan.allowed == allowed
    assert plan.saved_tokens == 0


def test_auto_stays_eager_when_the_window_is_unknown(monkeypatch):
    monkeypatch.setenv("HARNESS_TOOL_DISCLOSURE", "auto")
    reg = _registry()
    plan = resolve_disclosure(set(reg.names()), reg, window=None)
    assert not plan.enabled
    assert plan.reason == "window unknown"


def test_auto_stays_eager_below_the_threshold(monkeypatch):
    monkeypatch.setenv("HARNESS_TOOL_DISCLOSURE", "auto")
    reg = _registry()
    plan = resolve_disclosure(set(reg.names()), reg, window=10_000_000)
    assert not plan.enabled
    assert plan.reason == "below threshold"


def test_enabled_disclosure_keeps_effectful_and_interactive_and_saves_tokens(monkeypatch):
    monkeypatch.setenv("HARNESS_TOOL_DISCLOSURE", "on")
    reg = _registry()
    allowed = set(reg.names())
    plan = resolve_disclosure(allowed, reg, window=128_000)

    assert plan.enabled
    assert "portfolio_write" in plan.allowed  # effectful is never hidden
    assert "ask_user" in plan.allowed  # interactive is never hidden
    assert CORE_TOOLS & allowed <= plan.allowed
    assert "market_read_1" in plan.hidden
    assert plan.saved_tokens > 0
    assert plan.tier in (1, 2, 3)
    assert "tool_search" in plan.catalogue_block


def test_discovery_pair_is_required_before_narrowing(monkeypatch):
    monkeypatch.setenv("HARNESS_TOOL_DISCLOSURE", "on")
    reg = _registry()
    allowed = {"market_read_1", "tool_search"}  # invoke missing
    plan = resolve_disclosure(allowed, reg, window=128_000)
    assert not plan.enabled
    assert plan.reason == "discovery pair not bound"


def test_tier_degrades_when_the_catalogue_is_too_large():
    tools = [
        _tool(f"tool_{index}", "A very long description " * 12)
        for index in range(400)
    ]
    tier, block = build_catalogue(tools)
    assert tier in (2, 3)
    assert len(block) < 60_000


def test_bm25_ranks_an_exact_name_first_and_tags_matter():
    reg = _registry()
    tools = [reg.get(name) for name in reg.names()]
    ranked = rank_tools("market_get_quote", tools, 5)
    assert ranked[0].name == "market_get_quote"

    ranked = rank_tools("implied volatility option", tools, 3)
    assert ranked[0].name == "options_implied_volatility"


def test_tokenizer_splits_snake_and_camel_case():
    assert tokenize("market_getQuote") == ["market", "get", "quote"]


def test_labeled_query_set_recall_at_five():
    reg = _registry()
    tools = [reg.get(name) for name in reg.names()]
    cases = [
        ("market_get_quote", lambda name: name == "market_get_quote"),
        ("latest quote", lambda name: name == "market_get_quote"),
        ("implied volatility", lambda name: name == "options_implied_volatility"),
        ("option iv", lambda name: name == "options_implied_volatility"),
        ("price series", lambda name: name.startswith("market_read_")),
        ("market_read_7", lambda name: name == "market_read_7"),
        ("market series 23", lambda name: name.startswith("market_read_")),
        ("volume prices", lambda name: name.startswith("market_read_")),
        ("latest ticker price", lambda name: name == "market_get_quote"),
    ]
    hits = 0
    for query, matches in cases:
        top = [tool.name for tool in rank_tools(query, tools, 5)]
        hits += int(any(matches(name) for name in top))
    assert hits / len(cases) >= 0.90


@pytest.mark.asyncio
async def test_search_returns_available_sources_on_no_match(monkeypatch):
    monkeypatch.setenv("HARNESS_TOOL_DISCLOSURE", "on")
    reg = _registry()
    ctx = ToolContext(run_id="r1", log=lambda *_: None, tool_registry=reg)
    result = await reg.execute("tool_search", "c1", {"query": "zzzzz"}, ctx)
    payload = json.loads(result.text)
    assert payload["tools"] == []
    assert payload["availableSources"]
    assert any(item["domain"] == "market" for item in payload["availableSources"])


@pytest.mark.asyncio
async def test_search_includes_tags_and_domain():
    reg = _registry()
    ctx = ToolContext(run_id="r1", log=lambda *_: None, tool_registry=reg)
    result = await reg.execute("tool_search", "c1", {"query": "implied vol"}, ctx)
    payload = json.loads(result.text)
    match = next(row for row in payload["tools"] if row["name"] == "options_implied_volatility")
    assert match["domain"] == "quant"
    assert "option" in match["tags"]
