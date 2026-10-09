"""Agent-tool tests for the search layer."""

from __future__ import annotations

import pytest

from harness.search.tools import register_search_tools, _TOOL_NAMES
from harness.tools import ToolContext, ToolRegistry

from search_helpers import FakeEmbeddingProvider, instrument, make_service


def test_registration_is_idempotent_and_readonly():
    registry = ToolRegistry()
    added = register_search_tools(registry)
    assert set(added) == set(_TOOL_NAMES)
    assert register_search_tools(registry) == []
    for name in _TOOL_NAMES:
        assert registry.get(name).permission == "read"


@pytest.mark.asyncio
async def test_tools_search_and_scope():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    await service.ingest_text(
        "NVIDIA data center revenue grew on AI demand.",
        title="NVDA", source_type="filing", source_id="nvda", namespace="filing",
    )
    registry = ToolRegistry()
    register_search_tools(registry)
    ctx = ToolContext(run_id="r1", log=lambda *a, **k: None, search=service, user_id=None)

    result = await registry.execute("hybrid_search", "c1", {"query": "nvidia revenue"}, ctx)
    assert result.ok
    assert result.data["hits"]
    assert "citation" in result.data["hits"][0]
    assert "NVDA" in result.text


@pytest.mark.asyncio
async def test_tool_without_service_reports_unavailable():
    ctx = ToolContext(run_id="r1", log=lambda *a, **k: None, search=None)
    registry = ToolRegistry()
    register_search_tools(registry)
    result = await registry.execute("semantic_search", "c1", {"query": "x"}, ctx)
    assert result.data.get("available") is False


@pytest.mark.asyncio
async def test_search_admin_tool():
    service, _ = make_service(rerank_enabled=False)
    ctx = ToolContext(run_id="r1", log=lambda *a, **k: None, search=service)
    registry = ToolRegistry()
    register_search_tools(registry)
    result = await registry.execute("search_admin", "c1", {}, ctx)
    assert result.ok
    assert "embedding" in result.data


@pytest.mark.asyncio
async def test_search_context_tool_returns_budgeted_block():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    await service.ingest_text(
        "NVIDIA data center revenue grew on AI demand.",
        title="NVDA", source_type="filing", source_id="nvda", namespace="filing",
    )
    registry = ToolRegistry()
    register_search_tools(registry)
    ctx = ToolContext(run_id="r1", log=lambda *a, **k: None, search=service, user_id=None)
    result = await registry.execute("search_context", "c1", {"query": "nvidia revenue"}, ctx)
    assert result.ok
    # The assembled block is budgeted and delimited as untrusted data.
    assert "<<<UNTRUSTED_SEARCH_CONTENT>>>" in result.text
    assert "tokensEstimate" in result.data
    assert result.data["usedChunkIds"]
