"""Milestone 9 — prompt segments, stable cache keys, selective skill manifest.

These tests assert the properties that matter: reusable segments do not change
when only the user message changes; a profile/skill change invalidates ONLY that
segment; the cache key is deterministic; and skill injection stays bounded.
"""

from __future__ import annotations

from harness.prompt_segments import (
    MAX_SKILLS_IN_MANIFEST,
    PromptSegment,
    build_prompt_plan,
    build_skill_manifest,
    compare_plans,
    prompt_cache_key,
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


def test_run_instructions_do_not_change_cache_key():
    a = _plan(run_instructions="")
    b = _plan(run_instructions="Answer in JSON.")
    assert a.cache_key == b.cache_key


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


def test_reusable_token_accounting_excludes_user_message():
    plan = _plan()
    reusable = plan.reusable_total_tokens()
    assert reusable == sum(
        s.token_estimate for s in plan.segments
        if s.id in ("system_policy", "agent_identity", "tool_schemas",
                    "profile_snapshot", "session_summary", "skill_manifest")
    )
    assert reusable < sum(s.token_estimate for s in plan.segments)


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
