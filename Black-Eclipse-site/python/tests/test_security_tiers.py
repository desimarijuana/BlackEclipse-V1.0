"""Round 4 (W15): autonomy tiers mapped onto the existing policy.

The tier mapping is DERIVED from the policy groups the authorizer enforces —
these tests pin the classification order, the fail-safe direction, the audit,
and the consistency between the mapping and the policy itself.
"""

from __future__ import annotations

from types import SimpleNamespace

from harness.code import policy
from harness.security.tiers import (
    TIER_APPROVAL,
    TIER_AUTONOMOUS,
    TIER_GUARDED,
    classify_tool,
    tier_report,
    tier_requires_approval,
)


def test_effect_metadata_is_authoritative():
    assert classify_tool("anything", effect="external") == TIER_APPROVAL
    assert classify_tool("anything", effect="destructive") == TIER_APPROVAL
    assert classify_tool("anything", effect="write") == TIER_GUARDED
    assert classify_tool("anything", effect="execute") == TIER_GUARDED


def test_policy_groups_drive_the_tiers():
    approval_name = policy.EXTERNAL_ACTION_TOOLS[0]
    assert classify_tool(approval_name) == TIER_APPROVAL
    assert tier_requires_approval(classify_tool(approval_name)) is True

    write_name = policy.FS_WRITE_TOOLS[0]
    assert classify_tool(write_name) == TIER_GUARDED

    read_name = policy.FS_READ_TOOLS[0]
    assert classify_tool(read_name) == TIER_AUTONOMOUS


def test_the_mapping_is_consistent_with_the_policy_groups():
    approval = set(policy.EXTERNAL_ACTION_TOOLS) | set(policy.GIT_EXTERNAL_TOOLS)
    for name in approval:
        assert classify_tool(name) == TIER_APPROVAL, name
    guarded = (
        set(policy.WRITE_TOOLS) | set(policy.EXECUTION_WRITE_TOOLS)
        | set(policy.ACQUISITION_WRITE_TOOLS)
    )
    for name in guarded - approval:
        assert classify_tool(name) == TIER_GUARDED, name


def test_a_declared_write_permission_is_at_least_guarded():
    assert classify_tool("unknown_tool", permission="write") == TIER_GUARDED
    assert classify_tool("unknown_tool", permission="read") == TIER_AUTONOMOUS


def test_tier_report_audits_a_registry():
    tools = {
        "read_thing": SimpleNamespace(permission="read", effect=None),
        "write_thing": SimpleNamespace(permission="write", effect=None),
        "publish_thing": SimpleNamespace(permission="write", effect="external"),
    }

    class _Registry:
        def names(self):
            return list(tools)

        def get(self, name):
            return tools[name]

    report = tier_report(_Registry())
    assert report["counts"] == {"autonomous": 1, "guarded": 1, "approval": 1}
    assert report["approvalTierTools"] == ["publish_thing"]
    assert report["total"] == 3


def test_tier_report_on_a_real_registry_never_crashes():
    from harness.tasks.tools import register_task_tools
    from harness.tools import ToolRegistry

    registry = ToolRegistry()
    register_task_tools(registry)
    report = tier_report(registry)
    assert report["total"] >= 20
    # Task tools are agent-local read state: autonomous, never approval-gated.
    assert "create_goal" not in report["approvalTierTools"]
