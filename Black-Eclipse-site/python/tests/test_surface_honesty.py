"""Milestone 4 — surface honesty when a store is disabled.

The tool surface and the prompt guidance must derive from policy, resolved PER
RUN. A disabled store drops its tool from the bound schema and its guidance from
the prompt; the prompt stays byte-stable within a run.
"""

from __future__ import annotations

from harness.agents import ECLIPSE_AGENT
from harness.graph import resolve_surface, surface_disabled_tools
from harness.prompts import ECLIPSE_AGENT_SYSTEM_PROMPT, filter_system_prompt
from harness.tools import ToolRegistry


def _registry():
    from harness.memory_tools import register_memory_tools

    registry = ToolRegistry()
    register_memory_tools(registry)
    return registry


def _settings(**overrides):
    base = {
        "memory_enabled": True,
        "session_history_enabled": True,
        "external_memory_search_enabled": False,
    }
    base.update(overrides)
    return base


def test_disabled_store_drops_tool_from_allowlist():
    registry = _registry()
    allowed, prompt = resolve_surface(ECLIPSE_AGENT, registry, _settings(memory_enabled=False))
    assert "memory" not in allowed
    assert "memory_search_native" not in allowed
    # The prompt carries no memory guidance.
    assert "Eclipse-Memory is available through the `memory` tool." not in prompt
    assert "## Memory & self-improvement" not in prompt
    assert "## Prior sessions (historical recall)" not in prompt


def test_enabled_store_keeps_tool_and_guidance():
    registry = _registry()
    allowed, prompt = resolve_surface(ECLIPSE_AGENT, registry, _settings())
    assert "memory" in allowed
    assert "memory" in prompt
    assert prompt == ECLIPSE_AGENT_SYSTEM_PROMPT


def test_session_history_off_drops_session_tools_only():
    registry = _registry()
    allowed, prompt = resolve_surface(
        ECLIPSE_AGENT, registry, _settings(session_history_enabled=False)
    )
    assert "session_search" not in allowed
    assert "session_open" not in allowed
    assert "memory" in allowed
    assert "## Prior sessions (historical recall)" not in prompt
    assert "Eclipse-Memory is available through the `memory` tool." in prompt


def test_external_search_off_drops_external_tool():
    registry = _registry()
    allowed, _ = resolve_surface(ECLIPSE_AGENT, registry, _settings())
    assert "memory_search_external" not in allowed  # external off by default
    allowed_on, _ = resolve_surface(
        ECLIPSE_AGENT, registry, _settings(external_memory_search_enabled=True)
    )
    assert "memory_search_external" in allowed_on


def test_partial_enablement_advertises_only_working_surface():
    registry = _registry()
    allowed, _ = resolve_surface(
        ECLIPSE_AGENT, registry, _settings(external_memory_search_enabled=False)
    )
    assert "memory_search_native" in allowed
    assert "memory_search_external" not in allowed


def test_prompt_is_byte_stable_for_fixed_settings():
    registry = _registry()
    _, prompt_a = resolve_surface(ECLIPSE_AGENT, registry, _settings(memory_enabled=False))
    _, prompt_b = resolve_surface(ECLIPSE_AGENT, registry, _settings(memory_enabled=False))
    assert prompt_a == prompt_b


def test_filter_is_pure_and_leaves_base_prompt_untouched():
    assert filter_system_prompt(ECLIPSE_AGENT_SYSTEM_PROMPT) == ECLIPSE_AGENT_SYSTEM_PROMPT
    assert "Eclipse-Memory is available" in ECLIPSE_AGENT_SYSTEM_PROMPT


def test_surface_disabled_tools_defaults_safe():
    disabled = surface_disabled_tools({})
    # Defaults: memory on, sessions on, external off.
    assert "memory_search_external" in disabled
    assert "memory" not in disabled
    assert "session_search" not in disabled


def test_policy_flip_takes_effect_next_run_not_mid_run():
    registry = _registry()
    on_allowed, _ = resolve_surface(ECLIPSE_AGENT, registry, _settings())
    off_allowed, _ = resolve_surface(ECLIPSE_AGENT, registry, _settings(memory_enabled=False))
    assert "memory" in on_allowed
    assert "memory" not in off_allowed
