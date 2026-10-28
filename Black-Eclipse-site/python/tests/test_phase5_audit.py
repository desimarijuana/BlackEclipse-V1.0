"""Roadmap Phase 5 audit: the autonomy boundary is the allowlist."""

from __future__ import annotations

import inspect

from harness.agents import get_agent
from harness.code import actions
from harness.code.policy import (
    EXTERNAL_ACTION_TOOLS,
    allowed_tools,
)
from harness.evaluation.runner import _build_registry
from harness.mcp import approvals


def test_code_agent_has_no_finance_tools_and_no_mcp():
    code = get_agent("code-agent")
    tools = set(code.tools or ())
    assert not tools & {
        "market_get_quote", "market_get_ohlcv",
        "fundamentals_get_financials", "research_search",
    }
    assert code.allowMcpTools is False


def test_finance_agent_does_not_gain_external_code_actions():
    finance = get_agent("eclipse-agent")
    tools = set(finance.tools or ())
    assert not tools & set(EXTERNAL_ACTION_TOOLS)


def test_plan_only_removes_every_write_or_effectful_declared_tool():
    registry = _build_registry()
    declared = tuple(get_agent("code-agent").tools or ())
    allowed = allowed_tools("plan_only", declared)
    leaked = []
    for name in allowed:
        tool = registry.get(name)
        if tool is None:
            continue
        if tool.permission != "read" or (
            tool.effect and str(tool.effect) != "read"
        ):
            leaked.append((name, tool.permission, tool.effect))
    assert leaked == [], f"plan_only leaked write tools: {leaked}"


def test_unknown_autonomy_is_the_read_only_subset():
    declared = tuple(get_agent("code-agent").tools or ())
    assert set(allowed_tools("nonsense", declared)) == set(
        allowed_tools("plan_only", declared)
    )


def test_edit_verify_removes_external_actions():
    declared = tuple(get_agent("code-agent").tools or ())
    allowed = set(allowed_tools("edit_verify", declared))
    assert not (allowed & set(EXTERNAL_ACTION_TOOLS))


def test_single_use_claim_is_shared_not_reimplemented():
    source = inspect.getsource(actions)
    assert "consume_kind" in source
    assert "claim_guarded" in inspect.getsource(approvals)


def test_code_task_lifecycle_reuses_run_lineage():
    from harness.code import tasks

    source = inspect.getsource(tasks)
    assert "RunLineage" in source
    assert "latest_checkpoint" in source
    assert "save_checkpoint" in source
