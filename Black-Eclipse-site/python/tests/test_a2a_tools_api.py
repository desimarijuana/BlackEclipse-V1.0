"""The A2A tools and the operator-gated /a2a routes."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-a2a-api-"), "agent-memory.db"),
)
os.environ.setdefault("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")

from harness.a2a.tools import A2A_TOOLS, register_a2a_tools
from harness.tools import ToolRegistry

from a2a_helpers import make_service, tool_context


def test_a2a_tools_declared_on_the_default_agent():
    from harness.agents import ECLIPSE_AGENT

    assert set(A2A_TOOLS) <= set(ECLIPSE_AGENT.tools)


def test_register_and_invoke_list_agents(tmp_path):
    service, store, host = make_service(tmp_path)
    registry = ToolRegistry()
    added = register_a2a_tools(registry)
    assert "delegate_task" in added
    ctx = tool_context(store, registry=registry, bus=host.bus)

    async def run():
        return await registry.execute("list_agents", "c1", {}, ctx)

    result = asyncio.run(run())
    assert result.ok
    assert result.data["agents"]


def test_delegate_tool_creates_task(tmp_path):
    service, store, host = make_service(tmp_path)
    registry = ToolRegistry()
    register_a2a_tools(registry)
    ctx = tool_context(store, registry=registry, bus=host.bus, agent_id="eclipse-agent")

    async def run():
        return await registry.execute(
            "delegate_task", "c2", {"objective": "Summarize news", "agentId": "news-agent"}, ctx,
        )

    result = asyncio.run(run())
    assert result.ok
    assert result.data["delegation"]["childAgentId"] == "news-agent"


def test_send_and_receive_tools(tmp_path):
    service, store, host = make_service(tmp_path)
    registry = ToolRegistry()
    register_a2a_tools(registry)
    sender = tool_context(store, registry=registry, bus=host.bus, agent_id="eclipse-agent")
    receiver = tool_context(store, registry=registry, bus=host.bus, agent_id="research-agent")

    async def run():
        await registry.execute("send_message", "c3", {
            "type": "QUESTION", "recipientAgentId": "research-agent",
            "payload": {"question": "why?"},
        }, sender)
        return await registry.execute("receive_message", "c4", {}, receiver)

    result = asyncio.run(run())
    assert result.ok
    assert result.data["messages"]


def test_merge_results_tool(tmp_path):
    service, store, host = make_service(tmp_path)
    registry = ToolRegistry()
    register_a2a_tools(registry)
    ctx = tool_context(store, registry=registry, bus=host.bus)

    async def run():
        return await registry.execute("merge_results", "c5", {"results": [
            {"agentId": "a", "status": "COMPLETED",
             "findings": [{"claim": "x is 1", "confidence": 0.8, "evidenceRefs": ["e1"]}]},
        ]}, ctx)

    result = asyncio.run(run())
    assert result.ok
    assert result.data["merged"]["coverage"] == 1.0


# ── HTTP routes ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module
    from fastapi.testclient import TestClient

    with TestClient(main_module.app) as test_client:
        yield test_client


def test_a2a_status_and_agents(client):
    status = client.get("/a2a/status")
    assert status.status_code == 200
    assert status.json()["status"]["agents"] >= 10
    agents = client.get("/a2a/agents").json()["agents"]
    assert any(a["id"] == "valuation-agent" for a in agents)
    caps = client.get("/a2a/capabilities").json()["capabilities"]
    assert "valuation-agent" in caps["dcf"]


def test_a2a_delegate_over_http(client):
    res = client.post("/a2a/delegate", json={"objective": "Summarize news", "agentId": "news-agent"})
    assert res.status_code == 200
    assert res.json()["delegation"]["childAgentId"] == "news-agent"
    delegations = client.get("/a2a/delegations", params={"runId": "api"}).json()["delegations"]
    assert delegations


def test_a2a_merge_over_http(client):
    res = client.post("/a2a/merge", json={"results": [
        {"agentId": "a", "status": "COMPLETED",
         "findings": [{"claim": "x is 1", "confidence": 0.8, "evidenceRefs": ["e1"]}]},
    ]})
    assert res.status_code == 200
    assert "merged" in res.json()


def test_a2a_non_operator_refused(monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    from starlette.testclient import TestClient as TC

    import harness.main as main_module
    with TC(main_module.app, client=("203.0.113.9", 5555)) as remote:
        assert remote.get("/a2a/status").status_code == 403
        assert remote.get("/a2a/agents").status_code == 403


def test_a2a_missing_agent_404(client):
    assert client.get("/a2a/agents/agent_nope").status_code == 404
