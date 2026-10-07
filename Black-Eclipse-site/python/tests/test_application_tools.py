"""Application Runtime layer — agent-tool registration, gating and reachability.

Asserts the REAL tool surface: registration names, the autonomy boundary (the
write tools are removed at `plan_only`, the read-only surface stays), and that the
chat coding turn binds the runtime tools through the SAME resolver the graph uses.
"""

from __future__ import annotations

import pytest

from harness.execution.application.tools import (
    ALL_TOOL_NAMES,
    APP_RUNTIME_READ_TOOLS,
    APP_RUNTIME_WRITE_TOOLS,
    register_application_tools,
)
from harness.tools import ToolRegistry


def test_register_application_tools():
    registry = ToolRegistry()
    names = register_application_tools(registry)
    assert "runtime_start" in names
    assert "runtime_inspect" in names
    assert "container_list" in names
    assert "compose_up" in names
    assert "environment_inspect" in names
    assert "port_check" in names
    assert "health_check" in names
    assert registry.get("runtime_start").permission == "write"
    assert registry.get("runtime_inspect").permission == "read"
    assert registry.get("compose_up").effect == "external_action"
    assert registry.get("runtime_inspect").effect is None


def test_tool_surface_is_stable():
    registry = ToolRegistry()
    registered = set(register_application_tools(registry))
    assert registered == set(ALL_TOOL_NAMES)
    # Every declared tool has a handler and a schema, and the name sets are disjoint.
    from harness.execution.application.k8s_infra_tools import k8s_infra_schemas
    from harness.execution.application.tools import _HANDLERS, application_schemas

    schemas = {**application_schemas(), **k8s_infra_schemas()}
    for name in ALL_TOOL_NAMES:
        assert name in _HANDLERS, name
        assert name in schemas, name
    assert not (set(APP_RUNTIME_WRITE_TOOLS) & set(APP_RUNTIME_READ_TOOLS))


def test_new_capability_tools_are_registered():
    registry = ToolRegistry()
    names = set(register_application_tools(registry))
    for name in ("runtime_metrics_history", "workspace_graph", "workspace_start",
                 "workspace_stop", "k8s_port_forward", "k8s_logs_follow", "deploy_promote"):
        assert name in names, name
    assert registry.get("workspace_graph").permission == "read"
    assert registry.get("workspace_start").permission == "write"
    assert registry.get("deploy_promote").permission == "write"


def test_autonomy_boundary_structural():
    """The write tools are ABSENT at plan_only; the read tools stay."""
    from harness.agents import ECLIPSE_AGENT
    from harness.code import policy
    from harness.execution.application.tools import register_application_tools as reg
    from harness.tools import ToolRegistry

    registry = ToolRegistry()
    reg(registry)

    declared = tuple(ALL_TOOL_NAMES)
    edit = policy.allowed_tools("edit_verify", declared)
    plan = policy.allowed_tools("plan_only", declared)
    assert "runtime_start" in edit
    assert "runtime_start" not in plan
    assert "runtime_inspect" in plan
    assert "port_check" in plan
    # Cluster/infra/cloud mutations are removed at edit_verify AND plan_only.
    assert "k8s_apply" not in edit
    assert "terraform_apply" not in edit
    assert "deploy_run" not in edit
    assert "k8s_apply" not in plan
    # Read-only orchestration stays at plan_only.
    assert "k8s_get" in plan and "terraform_plan" in plan and "deploy_status" in plan
    # approve_external keeps the mutations.
    approve = policy.allowed_tools("approve_external", declared)
    assert "k8s_apply" in approve and "terraform_destroy" in approve and "deploy_run" in approve


def test_reachable_from_a_chat_coding_turn():
    from harness.agents import ECLIPSE_AGENT
    from harness.code.tools import register_code_tools
    from harness.execution.application.tools import register_application_tools
    from harness.graph import resolve_surface
    from harness.tools import ToolRegistry

    registry = ToolRegistry()
    register_code_tools(registry)
    register_application_tools(registry)

    def _bound(autonomy):
        allowed, _prompt = resolve_surface(ECLIPSE_AGENT, registry, {}, autonomy)
        return {s["name"] for s in registry.schemas(allowed)}

    change = _bound("edit_verify")
    assert {"runtime_inspect", "runtime_start", "runtime_stop", "package_install",
            "compose_up", "port_check", "health_check",
            "k8s_get", "k8s_logs", "terraform_plan", "deploy_status"} <= change
    # The cluster/infra/cloud MUTATIONS are absent at edit_verify.
    assert not ({"k8s_apply", "k8s_delete", "terraform_apply", "terraform_destroy", "deploy_run"} & change)
    question = _bound("plan_only")
    assert not ({"runtime_start", "package_install", "compose_up"} & question)
    assert {"runtime_inspect", "runtime_status", "port_check", "health_check",
            "k8s_get", "terraform_plan"} <= question


@pytest.mark.asyncio
async def test_handlers_refuse_without_runtime(monkeypatch):
    """With no application runtime installed, every handler refuses structurally."""
    from harness.execution.application import runtime as runtime_mod
    from harness.execution.application import tools
    from harness.tools import ToolContext

    monkeypatch.setattr(runtime_mod, "get_application_runtime", lambda: None)
    ctx = ToolContext(run_id="r", log=lambda *_: None, autonomy="edit_verify")
    for name in ("runtime_inspect", "runtime_start", "package_detect", "container_list",
                 "compose_up", "environment_inspect", "port_check", "health_check",
                 "k8s_get", "k8s_apply", "terraform_plan", "deploy_status", "cloud_providers"):
        handler = tools._HANDLERS[name]  # noqa: SLF001
        text, data = await handler({}, ctx)
        assert data.get("status") == "refused"


@pytest.mark.asyncio
async def test_start_refuses_without_execute_grant(tmp_path):
    from harness.execution.application import runtime as runtime_mod
    from harness.execution.application import tools
    from harness.execution.application.manager import ApplicationRuntimeManager, build_runtime_registry
    from harness.execution.application.store import ApplicationRuntimeStore
    from harness.persistence import AgentMemoryStore
    from harness.tools import ToolContext

    store = AgentMemoryStore(str(tmp_path / "m.db"))
    manager = ApplicationRuntimeManager(registry=build_runtime_registry(), store=ApplicationRuntimeStore(store))
    original = runtime_mod.get_application_runtime
    runtime_mod.set_application_runtime(manager)
    try:
        ctx = ToolContext(run_id="r", log=lambda *_: None, autonomy="plan_only")
        text, data = await tools._HANDLERS["runtime_start"]({}, ctx)
        assert data.get("status") == "refused"
        assert data.get("code") == "PROFILE_DENIED"
    finally:
        runtime_mod.set_application_runtime(original)


@pytest.mark.asyncio
async def test_runtime_detect_and_capabilities(tmp_path):
    from harness.execution.application import runtime as runtime_mod
    from harness.execution.application import tools
    from harness.execution.application.manager import ApplicationRuntimeManager, build_runtime_registry
    from harness.execution.application.store import ApplicationRuntimeStore
    from harness.persistence import AgentMemoryStore
    from harness.tools import ToolContext

    store = AgentMemoryStore(str(tmp_path / "m.db"))
    manager = ApplicationRuntimeManager(registry=build_runtime_registry(), store=ApplicationRuntimeStore(store))
    original = runtime_mod.get_application_runtime
    runtime_mod.set_application_runtime(manager)
    try:
        ctx = ToolContext(run_id="r", log=lambda *_: None, autonomy="edit_verify")
        text, data = await tools._HANDLERS["runtime_detect"]({}, ctx)
        assert data.get("status") == "ok"
        assert "tools" in data
        text2, data2 = await tools._HANDLERS["runtime_capabilities"]({}, ctx)
        assert "capabilities" in data2
        text3, data3 = await tools._HANDLERS["port_find_free"]({}, ctx)
        assert data3.get("status") == "ok"
    finally:
        runtime_mod.set_application_runtime(original)
