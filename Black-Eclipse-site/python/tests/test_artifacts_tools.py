"""Agent-tool integration for the Artifact Center."""

from __future__ import annotations

import asyncio

import pytest

from harness.artifacts import ArtifactService, ArtifactStore, LocalArtifactStorage
from harness.artifacts.tools import register_artifact_tools
from harness.persistence import AgentMemoryStore
from harness.tools import ToolContext, ToolRegistry


@pytest.fixture()
def ctx(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    registry = ToolRegistry()
    register_artifact_tools(registry)
    service = ArtifactService(ArtifactStore(store), LocalArtifactStorage(tmp_path / "files"))
    context = ToolContext(
        run_id="run_test", log=lambda *a, **k: None, memory_store=store,
        artifact_service=service, agent_id="eclipse-agent",
    )
    yield registry, context
    store.close()


def _run(registry, context, name, args):
    tool = registry.get(name)
    assert tool is not None
    return asyncio.run(tool.handler(args, context))


def test_tools_registered(ctx):
    registry, _ = ctx
    for name in (
        "artifact_register", "artifact_list", "artifact_get",
        "artifact_add_version", "artifact_tag", "artifact_create_collection",
    ):
        assert registry.get(name) is not None


def test_register_list_get_via_tools(ctx):
    registry, context = ctx
    text, data = _run(registry, context, "artifact_register", {
        "name": "out.csv", "contentBase64": "YSxiCjEsMgo=", "tags": ["x"],
    })
    assert "Registered artifact" in text
    artifact_id = data["artifact"]["id"]

    text, data = _run(registry, context, "artifact_list", {"mine": True})
    assert data["total"] == 1

    text, data = _run(registry, context, "artifact_get", {"artifactId": artifact_id})
    assert data["artifact"]["name"] == "out.csv"

    text, data = _run(registry, context, "artifact_add_version", {
        "artifactId": artifact_id, "contentBase64": "bmV3Cg==",
    })
    assert data["artifact"]["versionNumber"] == 2


def test_tool_without_service_reports_unavailable(tmp_path, monkeypatch):
    from harness.artifacts import bootstrap

    # No service is available: neither a run-context service nor the boot global.
    # Pin the global accessor so the assertion cannot depend on a service another
    # test (or a boot/self-heal path) may have registered process-wide.
    monkeypatch.setattr(bootstrap, "get_artifact_service", lambda: None)
    store = AgentMemoryStore(str(tmp_path / "m.db"))
    registry = ToolRegistry()
    register_artifact_tools(registry)
    context = ToolContext(run_id="r", log=lambda *a, **k: None, memory_store=store)
    text, data = _run(registry, context, "artifact_get", {"artifactId": "x"})
    assert "ARTIFACT_UNAVAILABLE" in text
    store.close()
