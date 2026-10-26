"""OPT-IN real-provider end-to-end checks for the graph agent plane.

Skipped unless explicitly enabled, because it spends real tokens and needs
credentials:

    HARNESS_E2E_PROVIDER=openai
    HARNESS_E2E_MODEL=gpt-4o-mini
    HARNESS_E2E_API_KEY=...
    (optional) HARNESS_E2E_BASE_URL=...
    HARNESS_E2E=1 pytest python/tests/test_graph_agent_e2e.py

This is the only place a real provider is exercised; the routine suites use
deterministic fakes.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.model import ExecutionMode, WorkflowIR
from harness.graph_runtime.planner import plan_graph

_ENABLED = os.getenv("HARNESS_E2E", "").strip().lower() in ("1", "true", "yes", "on")
_PROVIDER = os.getenv("HARNESS_E2E_PROVIDER", "").strip()
_MODEL = os.getenv("HARNESS_E2E_MODEL", "").strip()
_API_KEY = os.getenv("HARNESS_E2E_API_KEY", "").strip()
_BASE_URL = os.getenv("HARNESS_E2E_BASE_URL", "").strip() or None
# Local runtimes (Ollama/LM Studio/vLLM) accept requests without an API key.
_KEYLESS = {"ollama", "lmstudio", "local", "vllm"}

pytestmark = pytest.mark.skipif(
    not (
        _ENABLED
        and _PROVIDER
        and _MODEL
        and (_API_KEY or _PROVIDER.lower() in _KEYLESS)
    ),
    reason="set HARNESS_E2E=1 plus HARNESS_E2E_PROVIDER/MODEL (and API_KEY unless local)",
)


def _settings() -> dict:
    return {
        "provider": _PROVIDER,
        "model": _MODEL,
        "apiKey": _API_KEY,
        "baseUrl": _BASE_URL,
    }


def test_chat_to_graph_and_step_planning_with_a_real_provider():
    """Both model paths share ONE event loop (provider clients are loop-bound)."""
    from harness.graph_runtime.agent_plan import generate_step_plan

    async def run():
        planned = await plan_graph(
            "Fetch Apple daily bars, compute an EMA crossover signal and report the result.",
            model_settings=_settings(),
            registry=build_default_registry(),
        )
        steps = await generate_step_plan(
            "Check one recent AAPL filing for revenue growth.",
            model_settings=_settings(),
        )
        return planned, steps

    result, plan = asyncio.run(run())
    assert result["ok"] is True, result.get("errors")
    ir = WorkflowIR.model_validate(result["ir"])
    assert ir.nodes
    assert any(node.type == "output.result" for node in ir.nodes)
    assert result["model"]["provider"]

    assert plan["steps"]
    assert all(step["objective"] for step in plan["steps"])
    assert plan["model"]["provider"]


def _ir() -> WorkflowIR:
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_e2e", "name": "E2E",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            {"id": "trig", "type": "trigger.manual", "version": "1.0.0", "config": {}, "layout": {"x": 0, "y": 0}},
            {"id": "agent", "type": "agent.research", "version": "1.0.0",
             "config": {"agent": "eclipse-agent", "maxSteps": 2}, "layout": {"x": 0, "y": 0}},
            {"id": "out", "type": "output.result", "version": "1.0.0", "config": {}, "layout": {"x": 0, "y": 0}},
        ],
        "edges": [
            {"id": "e1", "source": "trig", "sourceHandle": "start", "target": "agent", "targetHandle": "query"},
            {"id": "e2", "source": "agent", "sourceHandle": "finding", "target": "out", "targetHandle": "value"},
        ],
        "settings": {"executionMode": ExecutionMode.RESEARCH.value, "failFast": False,
                     "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": ["agent.run"],
    })


def test_agent_node_reaches_a_real_provider(tmp_path):
    from harness.graph_runtime.bootstrap import install_graph_layer
    from harness.graph_runtime.compiler import RunGrants
    from harness.persistence import AgentMemoryStore
    from harness.service import AgenticService

    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    service = AgenticService(memory)
    try:
        assert install_graph_layer(service) is True
        run = service.graphs.run_sync(
            _ir(),
            grants=RunGrants(
                test_run=False,
                granted_capabilities=frozenset({"agent.run"}),
                allow_network=True,
            ),
            model_settings=_settings(),
            callback_base_url=os.getenv("HARNESS_CALLBACK_URL", ""),
        )
        assert run.status.value in ("succeeded", "failed")
        record = service.graphs.get_run(run.id)
        assert record is not None
        assert record["nodeRuns"]
    finally:
        service.close()
