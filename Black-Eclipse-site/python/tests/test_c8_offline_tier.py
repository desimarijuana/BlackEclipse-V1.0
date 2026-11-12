"""C8.4: the offline tier drives the real agent graph, not a fake loop."""

from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace

import pytest

from harness import graph as graph_module
from harness.evaluation.runner import ScriptedAgentInvoker
from harness.evaluation.tasks import EvaluationTask
from harness.persistence import AgentMemoryStore


@pytest.mark.asyncio
async def test_the_offline_invoker_calls_the_real_graph(monkeypatch):
    store = AgentMemoryStore(os.path.join(tempfile.mkdtemp(), "agent-memory.db"))
    invoker = ScriptedAgentInvoker(store)
    seen: dict[str, object] = {}

    async def fake_execute_run(request, registry, bridge, trial_store, **kwargs):
        seen["runId"] = request.runId
        seen["registry"] = registry
        seen["bus"] = kwargs.get("bus")
        return SimpleNamespace(status="completed", output="done", error=None)

    monkeypatch.setattr(graph_module, "execute_run", fake_execute_run)
    task = EvaluationTask.from_dict({
        "id": "c84.real_graph.001",
        "name": "Real graph seam",
        "description": "assert the offline invoker uses execute_run",
        "category": "core",
        "difficulty": "easy",
        "input": {"prompt": "Say done."},
        "expected_output": {"contains": "done"},
        "graders": [{"name": "exact"}],
        "metadata": {"tier": 0, "agent_script": [{"type": "final", "content": "done"}]},
    })
    result = await invoker.invoke(task, "trial_c84", SimpleNamespace())
    assert seen.get("runId")
    assert seen.get("registry") is not None
    assert seen.get("bus") is not None
    assert result.status == "completed"
    assert result.output == "done"
    store.close()
