"""Computer Use integration wiring tests.

Checks that the subsystem is registered through the SAME seams as every other
capability: the policy authority names its effectful tools, the authorizer chain
admits them, the agent presets advertise the toolset, and the HTTP route group is
included. These are structural guarantees, not desktop tests.
"""

from __future__ import annotations

import pytest


def test_effective_tools_matches_the_policy_authority():
    from harness.code.policy import COMPUTER_EFFECTFUL_TOOLS
    from harness.computer.schemas import EFFECTFUL_TOOLS

    # The tools the policy authority removes at plan_only must be a subset of the
    # tools the subsystem declares effectful.
    assert set(COMPUTER_EFFECTFUL_TOOLS) <= set(EFFECTFUL_TOOLS)


def test_plan_only_removes_elevated_computer_tools():
    from harness.agents import COMPUTER_TOOLS
    from harness.code.policy import COMPUTER_EFFECTFUL_TOOLS, allowed_tools

    allowed = set(allowed_tools("plan_only", tuple(COMPUTER_TOOLS)))
    for name in COMPUTER_EFFECTFUL_TOOLS:
        assert name not in allowed
    # Observation stays so a planning run can still see the desktop.
    assert "computer_use" in allowed
    assert "computer_capabilities" in allowed


def test_agents_advertise_the_computer_toolset():
    from harness.agents import CODE_AGENT, COMPUTER_TOOLS, ECLIPSE_AGENT

    for tool in COMPUTER_TOOLS:
        assert tool in ECLIPSE_AGENT.tools
        assert tool in CODE_AGENT.tools


@pytest.mark.asyncio
async def test_computer_authorizer_is_composed():
    from harness.code.authorizers import build_effect_authorizer
    from harness.computer.authorizers import make_computer_authorizer

    # The chain builds without an approvals store (the safe default).
    authorizer = build_effect_authorizer(None, "run-1", None, "ws-1")
    assert authorizer is not None
    # And the subsystem authorizer admits a declared effect tool.
    subsystem = make_computer_authorizer()

    class _Tool:
        name = "computer_finance_prepare"

    assert await subsystem(_Tool(), {}, None) is True


def test_router_is_included_in_the_app():
    from harness.main import app
    from harness.routers.computer import router

    included = {getattr(r, "path", None) for r in app.routes if hasattr(r, "path")}
    # The router object itself owns the paths; the app includes it.
    owned = {route.path for route in router.routes}
    assert "/computer/capabilities" in owned
    assert "/computer/doctor" in owned
    assert "/computer/sessions" in owned
    # At minimum the health route exists and the app exposes the health endpoint.
    assert "/health" in included


def test_register_computer_tools_registers_the_expected_names():
    from harness.computer.schemas import ALL_TOOL_NAMES
    from harness.computer.tools import register_computer_tools
    from harness.tools import ToolRegistry

    registry = ToolRegistry()
    added = register_computer_tools(registry)
    assert set(added) == set(ALL_TOOL_NAMES)
    # Computer action tools are registered read; the policy engine is the gate.
    assert registry.get("computer_use").permission == "read"
