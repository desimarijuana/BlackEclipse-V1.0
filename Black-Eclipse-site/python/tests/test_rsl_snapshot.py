"""RSL R3 — snapshot validation and the frozen landing target guard."""

from __future__ import annotations

import pytest

from harness.evaluation.candidate_invoker import (
    SnapshotError,
    assert_landable_target,
    validate_snapshot,
)
from harness.self_improvement.models import HarnessSnapshot
from harness.self_improvement.security import (
    RSL_FROZEN_TARGET,
    RSL_TARGET_OUTSIDE_WORKSPACE,
    RSL_TARGET_REQUIRED,
    RSLTargetError,
)


def _base() -> HarnessSnapshot:
    return HarnessSnapshot(
        systemPrompt="You are Eclipse.",
        toolNames=("eval_fs_write", "eval_fs_read"),
        maxSteps=8,
        maxToolCalls=8,
        skillDraftIds=("skill.a",),
    )


def _candidate(**overrides) -> HarnessSnapshot:
    values = {
        "systemPrompt": "You are a candidate.",
        "toolNames": ("eval_fs_write",),
        "maxSteps": 6,
        "maxToolCalls": 4,
        "skillDraftIds": ("skill.a",),
    }
    values.update(overrides)
    return HarnessSnapshot(**values)


def test_candidate_may_only_narrow_the_base_allowlist_and_ceilings():
    base = _base()
    candidate = _candidate()
    assert validate_snapshot(base, candidate) is candidate


@pytest.mark.parametrize("kwargs, code", [
    ({"toolNames": ("eval_fs_write", "eval_external_publish")}, "SNAPSHOT_TOOL_NOT_IN_BASE"),
    ({"maxSteps": 9}, "SNAPSHOT_STEPS_EXCEED_BASE"),
    ({"maxToolCalls": 9}, "SNAPSHOT_TOOL_CALLS_EXCEED_BASE"),
    ({"skillDraftIds": ("skill.a", "skill.b")}, "SNAPSHOT_UNKNOWN_SKILL"),
])
def test_candidate_cannot_widen_authority(kwargs, code):
    with pytest.raises(SnapshotError) as exc:
        validate_snapshot(_base(), _candidate(**kwargs))
    assert exc.value.code == code


@pytest.mark.parametrize("target", [
    "python/tests/test_rsl_config.py",
    "python/harness/evaluation/runner.py",
    "python/harness/evaluation/datasets/benchmark_v1.json",
    "python/harness/security/tiers.py",
    "python/harness/code/policy.py",
    "python/harness/code/authorizers.py",
    "python/harness/code/promotion.py",
    "python/harness/code/selfhost.py",
    "python/harness/code/patch.py",
    "python/harness/code/workspace.py",
    "python/harness/code/evolution.py",
    "python/harness/mcp/approvals.py",
    "python/harness/skills/permissions.py",
    "python/harness/skills/versioning.py",
    "scripts/test-evals.js",
    "scripts/check-all.js",
    ".env",
    "jdds.db",
    "./python\\harness\\evaluation\\runner.py",
])
def test_frozen_targets_are_refused(target):
    with pytest.raises(RSLTargetError) as exc:
        assert_landable_target(target)
    assert exc.value.code == RSL_FROZEN_TARGET


@pytest.mark.parametrize("target", [
    "",
    "C:/Users/msi/project/file.py",
    "/etc/passwd",
    "../outside.py",
    "python/harness/../../outside.py",
])
def test_targets_outside_the_workspace_are_refused(target):
    with pytest.raises(RSLTargetError) as exc:
        assert_landable_target(target)
    assert exc.value.code in (RSL_TARGET_REQUIRED, RSL_TARGET_OUTSIDE_WORKSPACE)


def test_a_normal_workspace_target_is_returned_normalized():
    assert assert_landable_target("./python\\harness\\finance_tools.py") == (
        "python/harness/finance_tools.py"
    )

def test_tool_guidance_is_bounded_and_part_of_the_digest():
    plain = HarnessSnapshot(systemPrompt="You are Eclipse.")
    guided = HarnessSnapshot(
        systemPrompt="You are Eclipse.",
        toolGuidance="Prefer the narrow tool; cite the result.",
    )
    assert plain.effective_prompt() == "You are Eclipse."
    assert "Prefer the narrow tool" in guided.effective_prompt()
    assert guided.sourceDigest != plain.sourceDigest
    assert guided.to_agent_config().systemPrompt == guided.effective_prompt()

    with pytest.raises(ValueError):
        HarnessSnapshot(
            systemPrompt="You are Eclipse.",
            toolGuidance="x" * 4_001,
        )

def test_context_policies_are_closed_sets_and_reach_the_agent_config():
    from harness.schemas import AgentConfig

    guided = HarnessSnapshot(
        systemPrompt="You are Eclipse.",
        skillManifest="top3",
        memoryPolicy="profile_only",
    )
    config = guided.to_agent_config()
    assert config.skillManifest == "top3"
    assert config.memoryPolicy == "profile_only"
    assert config.tools == []

    with pytest.raises(ValueError):
        HarnessSnapshot(systemPrompt="You are Eclipse.", skillManifest="everything")
    with pytest.raises(ValueError):
        HarnessSnapshot(systemPrompt="You are Eclipse.", memoryPolicy="everything")
    with pytest.raises(ValueError):
        AgentConfig(
            id="x", name="x", systemPrompt="p", skillManifest="everything",
        )


def test_a_context_policy_changes_the_snapshot_identity():
    plain = HarnessSnapshot(systemPrompt="You are Eclipse.")
    narrowed = HarnessSnapshot(
        systemPrompt="You are Eclipse.", skillManifest="none",
    )
    assert plain.sourceDigest != narrowed.sourceDigest
    assert "skillManifest" in narrowed.to_dict()
    assert "skillManifest" not in plain.to_dict()

def test_the_subagent_prompt_is_bounded_and_reaches_the_agent_config():
    snapshot = HarnessSnapshot(
        systemPrompt="You are Eclipse.",
        subagentPrompt="Report the numbers and the source of each one.",
    )
    assert snapshot.to_agent_config().subagentPrompt == (
        "Report the numbers and the source of each one."
    )
    assert snapshot.sourceDigest != HarnessSnapshot(
        systemPrompt="You are Eclipse."
    ).sourceDigest

    with pytest.raises(ValueError):
        HarnessSnapshot(
            systemPrompt="You are Eclipse.", subagentPrompt="x" * 4_001,
        )
