"""Phase 5 — the code-agent allowlist IS the autonomy boundary.

Structural, not prompt-based: a write/external tool the profile does not permit is
REMOVED before the model sees the schema, so the registry returns TOOL_FORBIDDEN.
"""

from __future__ import annotations

from harness.agents import CODE_AGENT, CODE_AGENT_TOOLS, ECLIPSE_AGENT, CODE_NAVIGATOR
from harness.code import policy
from harness.code.policy import EXTERNAL_ACTION_TOOLS, WRITE_TOOLS, allowed_tools
from harness.graph import effective_allowlist
from harness.tools import ToolRegistry
from harness.code.tools import register_code_tools

FINANCE_TOOL_PREFIXES = ("market_", "fundamentals_", "research_", "macro_", "get_")
CODE_TOOL_PREFIXES = ("workspace_", "patch_", "command_", "code_")


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_code_tools(reg)
    return reg


# ── the policy authority is the only narrowing seam ─────────────────────────


def test_plan_only_removes_write_and_external():
    declared = ("workspace_read", "workspace_patch_apply", "command_run", "code_commit")
    result = allowed_tools("plan_only", declared)
    assert "workspace_patch_apply" not in result
    assert "command_run" not in result
    assert "code_commit" not in result
    assert "workspace_read" in result


def test_edit_verify_has_write_but_not_external():
    declared = tuple(WRITE_TOOLS) + tuple(EXTERNAL_ACTION_TOOLS) + ("workspace_read",)
    result = allowed_tools("edit_verify", declared)
    assert set(WRITE_TOOLS) <= set(result)
    assert not (set(EXTERNAL_ACTION_TOOLS) & set(result))


def test_approve_external_has_everything():
    declared = tuple(WRITE_TOOLS) + tuple(EXTERNAL_ACTION_TOOLS)
    result = allowed_tools("approve_external", declared)
    assert set(declared) <= set(result)


def test_unknown_autonomy_is_read_only_subset():
    declared = tuple(WRITE_TOOLS) + tuple(EXTERNAL_ACTION_TOOLS) + ("workspace_read",)
    result = allowed_tools("nonsense", declared)
    assert not (set(WRITE_TOOLS) & set(result))
    assert not (set(EXTERNAL_ACTION_TOOLS) & set(result))
    assert "workspace_read" in result


# ── the code-agent preset ───────────────────────────────────────────────────


def test_code_agent_has_no_finance_tool():
    for name in CODE_AGENT.tools:
        assert not name.startswith(FINANCE_TOOL_PREFIXES), name
    # `delegate` (Phase 7) and `analysis_run` (Phase 8) are shared ORCHESTRATION /
    # COMPUTE capabilities, not finance tools: neither holds a data permission of
    # its own, and both are gated (delegation by narrowing, analysis by being off
    # per run). The Application Runtime tools (`runtime_*`/`package_*`/… and the
    # orchestration/infra/cloud tools) are also shared DevOps capabilities with no
    # finance data permission.
    from harness.execution.application.tools import ALL_TOOL_NAMES as APP_TOOLS
    from harness.agents import BROWSER_TOOLS, COMPUTER_TOOLS

    app_runtime = set(APP_TOOLS)
    # Browser and Computer Use tools are SHARED interactive capabilities (like
    # delegate/analysis), not finance tools: they carry no finance data permission
    # of their own and their effectful halves are narrowed by the run's autonomy
    # profile (browser policy engine / computer policy engine + finance firewall).
    assert not (set(CODE_AGENT.tools) & set(ECLIPSE_AGENT.tools) - {
        "memory", "skill_list", "skill_view", "session_search", "session_open",
        "delegate", "analysis_run", "scaffold_kit",
    } - app_runtime - set(BROWSER_TOOLS) - set(COMPUTER_TOOLS))


def test_code_agent_does_not_allow_mcp():
    assert getattr(CODE_AGENT, "allowMcpTools", False) is False


def test_finance_agent_unchanged_no_code_tool():
    for name in ECLIPSE_AGENT.tools:
        assert not name.startswith(CODE_TOOL_PREFIXES) or name.startswith(
            ("runtime_", "package_", "container_", "compose_", "environment_", "port_", "health_",
             "k8s_", "helm_", "kustomize_", "terraform_", "cloud_", "deploy_")), name
    # Phase 5: 24 tools, no code tool. Phase 7 adds `delegate`; Phase 8 adds
    # `analysis_run`; Phase 9 adds `scaffold_kit` — shared capabilities. The
    # Application Runtime adds a read-only DevOps surface (local + orchestration /
    # infra / cloud read-only) so the finance agent can answer "inspect this
    # project" / "what's deployed" without a coding turn.
    declared_app = [t for t in ECLIPSE_AGENT.tools if t.startswith(
        ("runtime_", "package_", "container_", "compose_", "environment_", "port_", "health_",
         "k8s_", "helm_", "kustomize_", "terraform_", "cloud_", "deploy_"))]
    # The Browser Automation Runtime adds a shared interactive capability set
    # (declared exactly once as `BROWSER_TOOLS`), so it is counted alongside the
    # base and the DevOps surface.
    from harness.agents import BROWSER_TOOLS, COMPUTER_TOOLS  # noqa: PLC0415

    assert len(ECLIPSE_AGENT.tools) == 27 + len(declared_app) + len(BROWSER_TOOLS) + len(COMPUTER_TOOLS)
    assert "runtime_inspect" in ECLIPSE_AGENT.tools
    assert "runtime_start" not in ECLIPSE_AGENT.tools
    assert "k8s_get" in ECLIPSE_AGENT.tools
    assert "k8s_apply" not in ECLIPSE_AGENT.tools
    assert "delegate" in ECLIPSE_AGENT.tools
    assert "analysis_run" in ECLIPSE_AGENT.tools
    assert "scaffold_kit" in ECLIPSE_AGENT.tools
    assert ECLIPSE_AGENT.allowMcpTools is True


def test_code_agent_registered_as_a_preset():
    from harness.agents import AGENT_PRESETS

    assert AGENT_PRESETS["code-agent"] is CODE_AGENT


# ── the allowlist is structural ─────────────────────────────────────────────


def test_plan_only_allowlist_has_no_write_tool():
    allowed = effective_allowlist(CODE_AGENT, _registry(), "plan_only")
    assert allowed is not None
    assert not (set(allowed) & set(WRITE_TOOLS))
    assert not (set(allowed) & set(EXTERNAL_ACTION_TOOLS))


def test_edit_verify_allowlist_has_write_no_external():
    allowed = effective_allowlist(CODE_AGENT, _registry(), "edit_verify")
    assert set(WRITE_TOOLS) <= set(allowed)
    assert not (set(allowed) & set(EXTERNAL_ACTION_TOOLS))


def test_approve_external_allowlist_has_external():
    allowed = effective_allowlist(CODE_AGENT, _registry(), "approve_external")
    assert set(EXTERNAL_ACTION_TOOLS) <= set(allowed)


def test_finance_agent_allowlist_is_not_narrowed_without_autonomy():
    allowed = effective_allowlist(ECLIPSE_AGENT, _registry(), None)
    assert set(ECLIPSE_AGENT.tools) <= set(allowed)


def test_registry_refuses_a_write_tool_absent_from_plan_only():
    import asyncio

    from harness.tools import ToolContext

    registry = _registry()
    allowed = effective_allowlist(CODE_AGENT, registry, "plan_only")
    ctx = ToolContext(run_id="r", log=lambda *_: None)
    result = asyncio.run(registry.execute(
        "workspace_patch_apply", "c1",
        {"operations": [{"op": "create", "path": "x.py", "reason": "x", "content": "y"}]},
        ctx, allowed=allowed,
    ))
    assert result.ok is False
    assert result.error is not None and result.error.code == "TOOL_FORBIDDEN"
