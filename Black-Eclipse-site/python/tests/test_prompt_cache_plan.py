"""W2.6: provider-gated prompt cache plan + marker application."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from harness.prompt_segments import (
    PromptCachePlan,
    apply_cache_markers,
    build_cache_plan,
    build_prompt_plan,
)


def _plan(provider: str = "anthropic"):
    return build_prompt_plan(
        system_prompt="You are Eclipse Agent.",
        agent_id="eclipse-agent",
        tool_names=["memory", "session_search"],
        user_message="hello",
        provider=provider,
    )


def test_anthropic_gets_one_ephemeral_marker():
    plan = _plan("anthropic")
    assert plan.cache_plan is not None
    assert plan.cache_plan.marker_kind == "anthropic_ephemeral"
    assert plan.cache_plan.marker_count == 1
    assert "system_policy" in plan.cache_plan.stable_segment_ids


def test_openai_compatible_gets_prefix_ordering_only():
    plan = _plan("openai")
    assert plan.cache_plan.marker_kind == "openai_prefix"
    assert plan.cache_plan.marker_count == 0


def test_unknown_provider_gets_no_marker():
    plan = _plan("some-new-provider")
    assert plan.cache_plan.marker_kind == "none"
    assert plan.cache_plan.marker_count == 0


def test_marker_is_applied_to_the_first_system_message_only():
    plan = _plan("anthropic")
    messages = [
        SystemMessage(content="stable policy"),
        HumanMessage(content="q"),
        AIMessage(content="a"),
    ]
    marked = apply_cache_markers(messages, plan.cache_plan)
    assert isinstance(marked[0].content, list)
    assert marked[0].content[0]["cache_control"] == {"type": "ephemeral"}
    assert marked[0].content[0]["text"] == "stable policy"
    # Other messages are untouched.
    assert marked[1].content == "q"
    # The input is not mutated.
    assert messages[0].content == "stable policy"


def test_marker_is_idempotent():
    plan = _plan("anthropic")
    messages = [SystemMessage(content="stable policy"), HumanMessage(content="q")]
    once = apply_cache_markers(messages, plan.cache_plan)
    twice = apply_cache_markers(once, plan.cache_plan)
    assert twice[0].content == once[0].content


def test_no_marker_for_non_anthropic_providers():
    for provider in ("openai", "google", "ollama", "unknown"):
        plan = _plan(provider)
        messages = [SystemMessage(content="policy"), HumanMessage(content="q")]
        marked = apply_cache_markers(messages, plan.cache_plan)
        assert marked[0].content == "policy"


def test_direct_provider_shorthand_is_capability_gated():
    messages = [SystemMessage(content="policy"), HumanMessage(content="q")]
    assert apply_cache_markers(messages, provider="anthropic")[0].content != "policy"
    assert apply_cache_markers(messages, provider="google")[0].content == "policy"


def test_cache_plan_is_serialised_without_content():
    payload = build_cache_plan("anthropic", _plan("anthropic")).to_dict()
    assert payload["markerKind"] == "anthropic_ephemeral"
    assert payload["markerCount"] == 1
    assert "You are Eclipse Agent" not in str(payload)


def test_plan_without_provider_has_no_cache_plan():
    plan = build_prompt_plan(system_prompt="s", agent_id="a", user_message="u")
    assert plan.cache_plan is None
    assert PromptCachePlan(provider="x").marker_kind == "none"
