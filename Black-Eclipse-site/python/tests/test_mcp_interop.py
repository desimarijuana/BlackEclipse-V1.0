"""Continuation Milestone 7 — interop details: sampling allowlist, name clamp.

Pure, offline. The sampling allowlist and the name clamp are both edge-case
safety: a server asking for an arbitrary model, and an over-long tool name
failing at the wire instead of at registration.
"""

from __future__ import annotations

import pytest

from harness.mcp.interactions import InteractionCounters, SamplingPolicy, build_sampling_callback
from harness.mcp.naming import (
    MAX_ECLIPSE_TOOL_NAME,
    name_was_clamped,
    namespace_tool,
)


# ── sampling allowlist ──────────────────────────────────────────────────────


def test_no_allowlist_is_unchanged_behaviour():
    # Absent list: the configured model is used, and the requested model is never
    # honoured (the runtime serves sampling on its own adapter).
    policy = SamplingPolicy(model="eclipse-default")
    assert policy.resolve_model("gpt-4o") == ("eclipse-default", False)
    assert policy.resolve_model(None) == ("eclipse-default", False)


def test_allowlist_honours_a_listed_model():
    policy = SamplingPolicy(model="eclipse-default", allowed_models=["gpt-4o", "claude"])
    assert policy.resolve_model("gpt-4o") == ("gpt-4o", False)
    assert policy.resolve_model("claude") == ("claude", False)


def test_allowlist_falls_back_for_an_unlisted_model():
    policy = SamplingPolicy(model="eclipse-default", allowed_models=["gpt-4o"])
    assert policy.resolve_model("evil-model") == ("eclipse-default", True)
    assert policy.resolve_model(None) == ("eclipse-default", True)


def test_policy_public_includes_allowed_models():
    policy = SamplingPolicy(allowed_models=["a", "b"])
    assert policy.public()["allowedModels"] == ["a", "b"]


@pytest.mark.asyncio
async def test_sampling_callback_records_a_model_fallback():
    policy = SamplingPolicy(enabled=True, model="eclipse-default", allowed_models=["gpt-4o"])
    counters = InteractionCounters()

    async def run_model(prompt: str) -> str:
        return "ok"

    callback = build_sampling_callback(policy=policy, server_id="s", counters=counters, run_model=run_model)

    class _Hint:
        name = "evil-model"

    class _Prefs:
        hints = [_Hint()]

    class _Params:
        model_preferences = _Prefs()
        messages = []
        max_tokens = 10

    await callback(None, _Params())
    assert counters.sampling_model_fallbacks == 1


@pytest.mark.asyncio
async def test_sampling_callback_no_fallback_without_an_allowlist():
    policy = SamplingPolicy(enabled=True, model="eclipse-default")
    counters = InteractionCounters()

    async def run_model(prompt: str) -> str:
        return "ok"

    callback = build_sampling_callback(policy=policy, server_id="s", counters=counters, run_model=run_model)

    class _Params:
        model_preferences = None
        messages = []
        max_tokens = 10

    await callback(None, _Params())
    assert counters.sampling_model_fallbacks == 0


# ── name clamp ──────────────────────────────────────────────────────────────


def test_a_short_name_is_byte_identical_to_today():
    # The convention is unchanged for a normal identity.
    name = namespace_tool("notion", "API-get-self")
    assert name == "mcp__notion__API_get_self"
    assert name_was_clamped("notion", "API-get-self") is False


def test_an_overlong_name_is_clamped_to_the_limit():
    long_tool = "a" * 200
    name = namespace_tool("server", long_tool)
    assert len(name) <= MAX_ECLIPSE_TOOL_NAME
    assert name.startswith("mcp__server__")
    assert name_was_clamped("server", long_tool) is True


def test_two_distinct_overlong_identities_do_not_collide():
    # The appended digest keeps two long, similarly-named tools distinct.
    a = namespace_tool("srv", "x" * 200 + "alpha")
    b = namespace_tool("srv", "x" * 200 + "beta")
    assert a != b
    assert len(a) <= MAX_ECLIPSE_TOOL_NAME and len(b) <= MAX_ECLIPSE_TOOL_NAME


def test_clamp_preserves_the_double_underscore_form():
    name = namespace_tool("a-very-long-server-id-name", "y" * 200)
    assert name.startswith("mcp__a_very_long_server_id_name__")
    assert len(name) <= MAX_ECLIPSE_TOOL_NAME
