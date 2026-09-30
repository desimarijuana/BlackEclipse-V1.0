"""Continuation Milestone 5 — circuit breaker for a server that always fails.

`maxCallsPerRun` bounds call volume; `RetryBudget` covers connect/reconnect.
Neither stops a server that connects and then fails every call. The breaker trips
into OPEN after a threshold, refuses immediately and honestly, and re-probes once
after a cooldown (HALF_OPEN). Deterministic and offline.
"""

from __future__ import annotations

import os
import sys

import pytest

from harness.mcp.circuit import (
    CLOSED,
    FAILURE_THRESHOLD,
    HALF_OPEN,
    OPEN,
    CircuitBreaker,
    breaker_state,
    should_probe,
)
from harness.mcp.config import MCPServerConfig
from harness.mcp.manager import MCPManager
from harness.tools import ToolContext, ToolRegistry

FIXTURES = os.path.join(os.path.dirname(__file__), "mcp_fixtures")
RAW = os.path.join(FIXTURES, "raw_fixture.py")


class FakeClock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


# ── pure state machine ──────────────────────────────────────────────────────


def test_breaker_closed_below_threshold_open_at_threshold():
    assert breaker_state(failures=0, opened_at=None, now=0) == CLOSED
    assert breaker_state(failures=FAILURE_THRESHOLD - 1, opened_at=None, now=0) == CLOSED
    assert breaker_state(failures=FAILURE_THRESHOLD, opened_at=0, now=0) == OPEN


def test_breaker_half_open_after_cooldown():
    # Cooldown 60s: before it, OPEN; after it, HALF_OPEN.
    assert breaker_state(failures=FAILURE_THRESHOLD, opened_at=0, now=30) == OPEN
    assert breaker_state(failures=FAILURE_THRESHOLD, opened_at=0, now=60) == HALF_OPEN
    assert should_probe(failures=FAILURE_THRESHOLD, opened_at=0, now=60, probe_in_flight=False) is True
    assert should_probe(failures=FAILURE_THRESHOLD, opened_at=0, now=60, probe_in_flight=True) is False


def test_breaker_machine_allow_and_reset():
    clock = FakeClock()
    b = CircuitBreaker(_clock=clock)
    assert b.state() == CLOSED
    for _ in range(FAILURE_THRESHOLD):
        assert b.allow() is True
        b.record_failure("mcp_timeout")
    assert b.state() == OPEN
    # OPEN: immediate refusal, and it does not claim the probe slot.
    assert b.allow() is False
    # After the cooldown: exactly one probe.
    clock.advance(61)
    assert b.allow() is True
    assert b.probe_in_flight is True
    # A second concurrent call while the probe is in flight is refused.
    assert b.allow() is False
    # Probe succeeds: back to CLOSED.
    b.record_success()
    assert b.state() == CLOSED
    assert b.allow() is True


def test_breaker_probe_failure_rearms_the_cooldown():
    clock = FakeClock()
    b = CircuitBreaker(_clock=clock)
    for _ in range(FAILURE_THRESHOLD):
        b.record_failure("mcp_call_failed")
    clock.advance(61)
    assert b.allow() is True
    b.record_probe_failure("mcp_call_failed")
    assert b.state() == OPEN
    assert b.allow() is False
    # The cooldown is re-armed from the probe-failure time.
    clock.advance(30)
    assert b.allow() is False
    clock.advance(31)
    assert b.allow() is True


def test_operator_reset_clears_the_breaker():
    clock = FakeClock()
    b = CircuitBreaker(_clock=clock)
    for _ in range(FAILURE_THRESHOLD):
        b.record_failure("mcp_timeout")
    assert b.state() == OPEN
    b.reset()
    assert b.state() == CLOSED
    assert b.failures == 0
    assert b.allow() is True


# ── manager integration ─────────────────────────────────────────────────────


def _cfg(mode: str, **overrides) -> MCPServerConfig:
    data = dict(
        id="raw",
        command=sys.executable,
        args=[RAW, mode],
        enabled=True,
        selected_tools=["echo"],
        tool_effects={"echo": "read"},
        startup_timeout_ms=8_000,
        catalog_timeout_ms=8_000,
        call_timeout_ms=8_000,
    )
    data.update(overrides)
    return MCPServerConfig(**data)


async def _execute(manager, registry, name, ctx, args=None):
    return await registry.execute(name, "c1", args or {"text": "hi"}, ctx, allowed={name})


@pytest.mark.asyncio
async def test_breaker_trips_after_repeated_transport_failures_and_refuses_honestly():
    manager = MCPManager([_cfg("fail_calls")])
    registry = ToolRegistry()
    await manager.start()
    try:
        [name] = manager.register_selected_tools(registry)
        rt = manager._runtimes["raw"]
        # Drive failures to the threshold.
        for _ in range(FAILURE_THRESHOLD):
            result = await _execute(manager, registry, name, ToolContext(run_id="r1", log=lambda *_: None))
            assert not result.ok
        assert rt.circuit.state() == OPEN
        # The next call refuses IMMEDIATELY with the distinct code and does no
        # transport work (no new call counted).
        calls_before = rt.calls
        result = await _execute(manager, registry, name, ToolContext(run_id="r1", log=lambda *_: None))
        assert not result.ok
        assert "circuit" in result.text.lower() or "failing every call" in result.text.lower()
        assert rt.calls == calls_before
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_a_denied_approval_does_not_trip_the_breaker():
    # A write tool with no authorizer is refused by the REGISTRY before the MCP
    # transport is ever reached — that must not count toward the breaker.
    body = _cfg("normal", selected_tools=["write_thing"], tool_effects={"write_thing": "write"},
                enabled_effects=["read", "write"])
    manager = MCPManager([body])
    registry = ToolRegistry()
    await manager.start()
    try:
        [name] = manager.register_selected_tools(registry)
        rt = manager._runtimes["raw"]
        for _ in range(FAILURE_THRESHOLD + 2):
            result = await _execute(manager, registry, name, ToolContext(run_id="r1", log=lambda *_: None))
            assert not result.ok
        assert rt.circuit.failures == 0
        assert rt.circuit.state() == CLOSED
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_operator_reset_clears_a_tripped_breaker():
    manager = MCPManager([_cfg("fail_calls")])
    registry = ToolRegistry()
    await manager.start()
    try:
        [name] = manager.register_selected_tools(registry)
        rt = manager._runtimes["raw"]
        for _ in range(FAILURE_THRESHOLD):
            await _execute(manager, registry, name, ToolContext(run_id="r1", log=lambda *_: None))
        assert rt.circuit.state() == OPEN
        # (The call above is `_execute(manager, registry, name, ctx)`.)
        out = manager.reset_circuit("raw")
        assert out["success"] is True
        assert rt.circuit.state() == CLOSED
    finally:
        await manager.close()
