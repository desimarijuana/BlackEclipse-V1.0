"""C6: effect tokens bind an approval to the exact effectful call."""

from __future__ import annotations

import asyncio

import pytest

from harness.security import effect_tokens
from harness.security.effect_tokens import (
    EffectTokenBroker,
    attach_token,
    enforce_call,
    reset_broker,
    token_mode,
)
from harness.tools import ToolContext, ToolDefinition, ToolRegistry


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("HARNESS_EFFECT_TOKENS", raising=False)
    reset_broker(EffectTokenBroker(secret="test-secret-that-is-long-enough"))
    yield
    reset_broker(None)


def _broker() -> EffectTokenBroker:
    return EffectTokenBroker(secret="test-secret-that-is-long-enough")


def test_a_token_roundtrips_only_for_its_exact_call():
    broker = _broker()
    token = broker.issue(run_id="run_1", tool="shell", args={"cmd": "ls"}, tenant_id="t1")
    assert broker.verify(
        token, run_id="run_1", tool="shell", args={"cmd": "ls"}, tenant_id="t1",
    ).ok
    assert not broker.verify(
        token, run_id="run_2", tool="shell", args={"cmd": "ls"}, tenant_id="t1",
    ).ok
    assert not broker.verify(
        token, run_id="run_1", tool="shell", args={"cmd": "rm -rf /"}, tenant_id="t1",
    ).ok
    assert not broker.verify(
        token, run_id="run_1", tool="git", args={"cmd": "ls"}, tenant_id="t1",
    ).ok
    assert not broker.verify(
        token, run_id="run_1", tool="shell", args={"cmd": "ls"}, tenant_id="t2",
    ).ok


def test_argument_order_does_not_change_the_binding():
    broker = _broker()
    token = broker.issue(run_id="r", tool="t", args={"a": 1, "b": 2})
    assert broker.verify(token, run_id="r", tool="t", args={"b": 2, "a": 1}).ok


def test_a_tampered_or_expired_token_is_refused(monkeypatch):
    broker = _broker()
    token = broker.issue(run_id="r", tool="t", args={})
    body, _, signature = token.partition(".")
    assert not broker.verify(body + "." + ("A" * len(signature)), run_id="r", tool="t", args={}).ok
    assert not broker.verify("not-a-token", run_id="r", tool="t", args={}).ok

    now = effect_tokens.time.time
    monkeypatch.setattr(effect_tokens.time, "time", lambda: now() + 10_000)
    assert "expired" in broker.verify(token, run_id="r", tool="t", args={}).reason


def test_mode_defaults_to_shadow_and_parses_explicit_values(monkeypatch):
    assert token_mode() == "shadow"
    monkeypatch.setenv("HARNESS_EFFECT_TOKENS", "enforce")
    assert token_mode() == "enforce"
    monkeypatch.setenv("HARNESS_EFFECT_TOKENS", "off")
    assert token_mode() == "off"


def test_shadow_mode_records_a_missing_token_but_does_not_block():
    ctx = ToolContext(run_id="r1", log=lambda *_: None)
    verdict = enforce_call(ctx, "shell", {"cmd": "ls"})
    assert verdict.ok and verdict.shadow
    assert ctx.effect_token_reason == "no effect token"


def test_enforce_mode_refuses_a_call_without_a_token(monkeypatch):
    monkeypatch.setenv("HARNESS_EFFECT_TOKENS", "enforce")
    ctx = ToolContext(run_id="r1", log=lambda *_: None)
    verdict = enforce_call(ctx, "shell", {"cmd": "ls"})
    assert not verdict.ok
    assert "no effect token" in verdict.reason


def test_enforce_mode_accepts_the_bound_token_exactly_once(monkeypatch):
    monkeypatch.setenv("HARNESS_EFFECT_TOKENS", "enforce")
    ctx = ToolContext(run_id="r1", log=lambda *_: None)
    attach_token(ctx, run_id="r1", tool="shell", args={"cmd": "ls"})
    assert enforce_call(ctx, "shell", {"cmd": "ls"}).ok
    replay = enforce_call(ctx, "shell", {"cmd": "ls"})
    assert not replay.ok
    assert "already used" in replay.reason


def _effectful_registry() -> tuple[ToolRegistry, list[str]]:
    calls: list[str] = []

    async def handler(args, ctx):
        calls.append(args.get("cmd", ""))
        return "ran"

    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="effectful_shell",
        description="writes",
        input_schema={
            "type": "object",
            "properties": {"cmd": {"type": "string"}},
            "required": ["cmd"],
        },
        handler=handler,
        permission="write",
        risk="high",
    ))
    return registry, calls


@pytest.mark.asyncio
async def test_the_tool_executor_refuses_an_unbound_effectful_call(monkeypatch):
    monkeypatch.setenv("HARNESS_EFFECT_TOKENS", "enforce")
    registry, calls = _effectful_registry()

    async def authorizer(tool, args, ctx):
        return True  # approved, but no token bound to this call

    ctx = ToolContext(run_id="r1", log=lambda *_: None, authorize_effect=authorizer)
    result = await registry.execute("effectful_shell", "c1", {"cmd": "touch x"}, ctx)
    assert not result.ok
    assert result.error.code == "TOOL_FORBIDDEN"
    assert "effect token" in result.error.message
    assert calls == []


@pytest.mark.asyncio
async def test_the_tool_executor_runs_when_the_authorizer_binds_a_token(monkeypatch):
    monkeypatch.setenv("HARNESS_EFFECT_TOKENS", "enforce")
    registry, calls = _effectful_registry()

    async def authorizer(tool, args, ctx):
        attach_token(ctx, run_id=ctx.run_id, tool=tool.name, args=args)
        return True

    ctx = ToolContext(run_id="r1", log=lambda *_: None, authorize_effect=authorizer)
    result = await registry.execute("effectful_shell", "c1", {"cmd": "touch x"}, ctx)
    assert result.ok, result
    assert calls == ["touch x"]


@pytest.mark.asyncio
async def test_widening_the_arguments_after_approval_is_refused(monkeypatch):
    monkeypatch.setenv("HARNESS_EFFECT_TOKENS", "enforce")
    registry, calls = _effectful_registry()

    async def authorizer(tool, args, ctx):
        # Authorize a benign command, not the one the executor runs.
        attach_token(ctx, run_id=ctx.run_id, tool=tool.name, args={"cmd": "ls"})
        return True

    ctx = ToolContext(run_id="r1", log=lambda *_: None, authorize_effect=authorizer)
    result = await registry.execute("effectful_shell", "c1", {"cmd": "rm -rf /"}, ctx)
    assert not result.ok
    assert result.error.code == "TOOL_FORBIDDEN"
    assert "effect token" in result.error.message
    assert calls == []


def test_the_security_authorizer_mints_the_bound_token(tmp_path):
    """The migration seam attaches a token for the exact authorized call."""
    import os
    import tempfile
    from types import SimpleNamespace

    from harness.persistence import AgentMemoryStore
    from harness.security.gateway import SecurityGateway
    from harness.security.integration import make_security_authorizer
    from harness.security.models import PolicyProfile

    store = AgentMemoryStore(os.path.join(tempfile.mkdtemp(), "am.db"))
    gateway = SecurityGateway(store=store, profile=PolicyProfile.DEVELOPER)

    async def inner(tool, args, ctx=None):
        return True

    authorizer = make_security_authorizer(
        inner, run_id="run_c6", workspace_id="ws", gateway=gateway,
    )
    ctx = SimpleNamespace(
        run_id="run_c6", agent_id="a", tenant_id=None, session_id="s",
        workspace="ws", tenant=None,
    )
    tool = SimpleNamespace(name="write_file")
    allowed = asyncio.run(authorizer(tool, {"path": "src/app.py"}, ctx))
    assert allowed is True
    assert ctx.effect_token
    verdict = effect_tokens.get_broker().verify(
        ctx.effect_token, run_id="run_c6", tool="write_file",
        args={"path": "src/app.py"},
    )
    assert verdict.ok, verdict.reason
    # The same token does not authorize a different path.
    assert not effect_tokens.get_broker().verify(
        ctx.effect_token, run_id="run_c6", tool="write_file",
        args={"path": "src/other.py"},
    ).ok

