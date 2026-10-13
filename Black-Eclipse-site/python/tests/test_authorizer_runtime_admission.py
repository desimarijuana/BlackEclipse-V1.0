"""R3-02 — the runtime authorizer admits the execution + local application-runtime
families.

Measured before the fix: `execute_python` / `execute_code` / `build_project` /
`start_service` / `package_install` all returned False — the composed chain fell
through to the MCP authorizer, which refuses any tool without an MCP server id —
while those tools were still advertised to `edit_verify` profiles. They are now
admitted at the seam exactly like `command_run`; the HANDLER enforces the
workspace binding and the `code.execute` grant, and the security gateway still
classifies every call. Cluster/infra/remote actions stay unadmitted.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.code.authorizers import _admit_runtime_tools, build_effect_authorizer
from harness.tools import ToolDefinition


def _tool(name: str, effect: str = "external_action") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="",
        input_schema={"type": "object", "properties": {}},
        handler=lambda args, ctx: ("ok", None),
        permission="write",
        risk="high",
        effect=effect,
    )


def _authorize(name: str, effect: str = "external_action") -> bool:
    async def inner(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        return False

    return asyncio.run(_admit_runtime_tools(inner)(_tool(name, effect), {}, None))


@pytest.mark.parametrize("name", [
    # the execution layer
    "execute_code", "execute_python", "execute_javascript", "execute_typescript",
    "execute_sql", "execute_shell", "build_project", "test_project",
    "run_verification", "start_service", "stop_service", "restart_service",
    "cancel_execution",
    # the LOCAL application-runtime layer
    "runtime_start", "runtime_stop", "package_install", "package_add",
    "container_run", "compose_up", "environment_set",
])
def test_execution_and_local_runtime_tools_are_admitted(name: str) -> None:
    assert _authorize(name) is True


@pytest.mark.parametrize("name", [
    # cluster / infra / deploy stay on their own approval path (R3-07)
    "k8s_apply", "helm_install", "terraform_apply", "deploy_run",
    # remote / external actions are unchanged
    "code_push", "code_deploy", "git_push",
    # a non-runtime tool must still reach the real chain
    "plugin_invoke", "unknown_tool",
])
def test_infra_remote_and_unknown_tools_still_fall_through(name: str) -> None:
    assert _authorize(name) is False


def test_the_composed_authorizer_admits_execute_python_without_a_gateway(
    monkeypatch: Any,
) -> None:
    # The COMPOSITION (not only the helper) admits it when no security gateway is
    # installed; with a gateway the classification still runs first.
    from harness.security import bootstrap as sec_bootstrap

    monkeypatch.setattr(sec_bootstrap, "get_gateway", lambda: None)

    async def run() -> bool:
        auth = build_effect_authorizer(
            approvals=object(), run_id="r", emitter=None, workspace_id=None,
        )
        return bool(await auth(_tool("execute_python"), {}, None))

    assert asyncio.run(run()) is True


def test_the_admission_set_is_exactly_the_write_families() -> None:
    # The branch claims the execution write family and the local app-runtime
    # writes — and never a read tool (those never reach an authorizer).
    from harness.code import policy

    assert set(policy.EXECUTION_READ_TOOLS).isdisjoint(policy.EXECUTION_WRITE_TOOLS)
    assert set(policy.EXECUTION_READ_TOOLS).isdisjoint(policy.APP_RUNTIME_WRITE_TOOLS)
    assert "execute_python" in policy.EXECUTION_WRITE_TOOLS
    assert "package_install" in policy.APP_RUNTIME_WRITE_TOOLS
