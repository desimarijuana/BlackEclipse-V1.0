"""End-to-end: the REAL chat run graph drives the portfolio construction tools.

Unlike the registry-level tests, these drive `graph.execute_run` with a scripted
model, so a natural-language turn must route to a registered portfolio tool,
execute it, and finish — the integration the chatbot actually uses.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.finance_tools import register_finance_tools
from harness.persistence import AgentMemoryStore
from harness.portfolio.tools import register_portfolio_tools
from harness.schemas import ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolRegistry
from portfolio_helpers import make_service


class ScriptedModel:
    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)

    def bind_tools(self, tools: Any) -> "ScriptedModel":
        return self

    async def ainvoke(self, messages: Any) -> AIMessage:
        return self._responses.pop(0) if self._responses else AIMessage(content="(exhausted)")

    async def astream(self, messages: Any):
        yield await self.ainvoke(messages)


class _Bridge(DataBridge):
    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "UNAVAILABLE"}


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-portfolio-chat-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_finance_tools(reg)
    register_portfolio_tools(reg)
    return reg


def _request(run_id: str, query: str, **kw: Any) -> RunRequest:
    return RunRequest(
        runId=run_id, input=RunInput(query=query), agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000", **kw,
    )


@pytest.mark.asyncio
async def test_chat_drives_portfolio_comparison_through_the_graph(store, monkeypatch):
    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{"id": "c1", "name": "portfolio_compare_allocations",
                                           "args": {"symbols": ["A", "B"],
                                                    "covariance": [[0.04, 0.0], [0.0, 0.09]],
                                                    "expected_returns": [0.08, 0.05],
                                                    "methods": ["equal_weight", "min_variance"]}}]),
        AIMessage(content="Min-variance had lower volatility."),
    ])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    result = await graph_module.execute_run(
        _request("run_pf_compare", "compare equal weight and minimum variance"),
        _registry(), _Bridge(), store)
    assert result.status == "completed"
    assert result.toolCalls >= 1
    assert result.toolErrors == 0


@pytest.mark.asyncio
async def test_chat_drives_portfolio_estimation_through_the_graph(store, monkeypatch):
    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{"id": "c1", "name": "portfolio_estimate_inputs",
                                           "args": {"returns": {"A": [0.01, -0.01, 0.02],
                                                                "B": [0.0, 0.01, -0.01]}}}]),
        AIMessage(content="Estimated."),
    ])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    result = await graph_module.execute_run(
        _request("run_pf_estimate", "estimate expected returns and covariance from these returns"),
        _registry(), _Bridge(), store)
    assert result.status == "completed" and result.toolErrors == 0
