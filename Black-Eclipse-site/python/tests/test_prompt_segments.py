"""Milestone 9 — prompt segments, stable cache keys, selective skill manifest.

These tests assert the properties that matter: reusable segments do not change
when only the user message changes; a profile/skill change invalidates ONLY that
segment; the cache key is deterministic; and skill injection stays bounded.
"""

from __future__ import annotations

from harness.prompt_segments import (
    MAX_SKILLS_IN_MANIFEST,
    STATIC_SEGMENTS,
    PromptSegment,
    build_prompt_plan,
    build_skill_manifest,
    compare_plans,
    prompt_cache_key,
    runtime_context_block,
)


def _plan(**overrides):
    base = dict(
        system_prompt="You are Eclipse Agent.",
        agent_id="eclipse-agent",
        tool_names=["memory", "session_search"],
        profile_block="Persistent context\n```\n[USER PROFILE]\n- Prefers concise answers.\n```",
        profile_snapshot_id="snap_1",
        skill_manifest="Skill manifest:\n- research.planning",
        skill_manifest_version="mf_1",
        user_message="hello",
    )
    base.update(overrides)
    return build_prompt_plan(**base)


def test_cache_key_is_deterministic():
    assert _plan().cache_key == _plan().cache_key


def test_user_message_does_not_change_cache_key():
    a = _plan(user_message="hello")
    b = _plan(user_message="a completely different question")
    assert a.cache_key == b.cache_key
    # …but the user_message segment hash differs.
    assert a.by_id("user_message").content_hash != b.by_id("user_message").content_hash


def test_run_instructions_segment_is_removed():
    """Gap 2: the never-populated `run_instructions` segment is gone."""
    assert _plan().by_id("run_instructions") is None


def test_profile_change_invalidates_only_profile_segment():
    a = _plan(profile_snapshot_id="snap_1", profile_block="P1")
    b = _plan(profile_snapshot_id="snap_2", profile_block="P2")
    assert a.cache_key != b.cache_key
    changes = compare_plans(a, b)
    assert [c["segment"] for c in changes] == ["profile_snapshot"]


def test_skill_manifest_change_invalidates_only_manifest_segment():
    a = _plan(skill_manifest_version="mf_1", skill_manifest="M1")
    b = _plan(skill_manifest_version="mf_2", skill_manifest="M2")
    assert a.cache_key != b.cache_key
    changes = compare_plans(a, b)
    assert [c["segment"] for c in changes] == ["skill_manifest"]


def test_tool_schema_change_invalidates_cache_key():
    a = _plan(tool_names=["a", "b"])
    b = _plan(tool_names=["a", "b", "c"])
    assert a.cache_key != b.cache_key
    assert [c["segment"] for c in compare_plans(a, b)] == ["tool_schemas"]


def test_segment_records_identity():
    plan = _plan()
    segment = plan.by_id("system_policy")
    assert isinstance(segment, PromptSegment)
    assert segment.source == "prompts.py"
    assert segment.content_hash
    assert segment.token_estimate > 0
    assert segment.cache_key == plan.cache_key


def test_prompt_content_edit_changes_cache_key():
    """TASK 4: a system-policy CONTENT change must change the cache key.

    The key was previously derived from hand-bumped versions only, so editing the
    prompt left it unchanged.
    """
    a = _plan(system_prompt="You are Eclipse Agent. Rule A.")
    b = _plan(system_prompt="You are Eclipse Agent. Rule B.")
    assert a.cache_key != b.cache_key
    assert [c["segment"] for c in compare_plans(a, b)] == ["system_policy"]


def test_runtime_context_does_not_change_cache_key():
    """The run date lives in a run-frozen segment, never the reusable key."""
    a = _plan(runtime_context="Date: 2026-10-01")
    b = _plan(runtime_context="Date: 2026-10-02")
    assert a.cache_key == b.cache_key
    assert a.by_id("runtime_context").content_hash != b.by_id("runtime_context").content_hash


def test_reusable_token_accounting_excludes_run_frozen_segments():
    plan = _plan(runtime_context="Date: 2026-10-01")
    reusable = plan.reusable_total_tokens()
    assert reusable == sum(
        s.token_estimate for s in plan.segments if s.id in STATIC_SEGMENTS
    )
    # Run-frozen and turn-specific segments are NOT part of the reuse accounting.
    for segment_id in ("runtime_context", "user_message",
                       "profile_snapshot", "skill_manifest"):
        assert segment_id not in STATIC_SEGMENTS
    assert reusable < sum(s.token_estimate for s in plan.segments)


def test_session_summary_is_not_a_declared_segment():
    """M6: the never-populated `session_summary` was removed from the plan."""
    assert _plan().by_id("session_summary") is None


def test_runtime_context_block_carries_run_date_and_id():
    from datetime import datetime, timezone

    now = datetime(2026, 10, 1, 14, 30, 0, tzinfo=timezone.utc)
    block = runtime_context_block("run_abc", now=now)
    assert "2026-10-01" in block
    assert "14:30:00" in block
    assert "run_abc" in block


# ── skill manifest ──────────────────────────────────────────────────────────


class _FakeRegistry:
    def __init__(self, matches):
        self._matches = matches

    def discover(self, query="", include_non_executable=True, **kwargs):
        return self._matches


def test_skill_manifest_is_bounded():
    matches = [
        {"id": f"skill.{i}", "version": "1", "description": "d" * 200}
        for i in range(50)
    ]
    registry = _FakeRegistry(matches)
    content, version = build_skill_manifest(registry, "anything")
    assert content
    assert version
    assert content.count("- skill.") <= MAX_SKILLS_IN_MANIFEST


def test_skill_manifest_empty_when_no_matches():
    assert build_skill_manifest(_FakeRegistry([]), "q") == ("", None)


def test_skill_manifest_survives_registry_error():
    class Boom:
        def discover(self, **kwargs):
            raise RuntimeError("boom")

    assert build_skill_manifest(Boom(), "q") == ("", None)


def test_no_previous_plan_reports_no_previous():
    changes = compare_plans(None, _plan())
    assert changes == [{"segment": "all", "reason": "no previous plan"}]
