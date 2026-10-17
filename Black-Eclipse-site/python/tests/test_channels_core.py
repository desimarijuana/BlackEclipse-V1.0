"""Channel Gateway core tests: store, identity linking, command parsing, dispatch
scope gating, the operator `/do` tool bridge and its confirmation gate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from harness.channels import commands
from harness.channels.dispatch import ChannelDispatcher
from harness.channels.identity import claim_link_code, create_link_code
from harness.channels.model import InboundMessage, scope_allows
from harness.channels.service import ChannelService
from harness.channels.store import ChannelStore
from harness.persistence import AgentMemoryStore
from harness.tools import ToolContext, ToolDefinition, ToolRegistry


class _FakeResult:
    def __init__(self, output: str | None, status: str = "completed") -> None:
        self.output = output
        self.status = status
        self.error = None


class _DummyGateway:
    """Enough of a SecurityGateway for `make_security_authorizer` to allow an
    UNCLASSIFIED native tool (classification is None ⇒ inner/True)."""

    secrets = None
    audit = None


class FakeService:
    def __init__(self, store: AgentMemoryStore) -> None:
        self.store = store
        self.security = _DummyGateway()
        self.registry = ToolRegistry()
        self.ran: list = []

        async def read_tool(args, ctx):  # noqa: ANN001
            return f"quote {args.get('symbol')}"

        async def write_tool(args, ctx):  # noqa: ANN001
            return "wrote it"

        self.registry.register(
            ToolDefinition(
                name="read_tool", description="read", handler=read_tool,
                input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
                permission="read",
            )
        )
        self.registry.register(
            ToolDefinition(
                name="write_tool", description="write", handler=write_tool,
                input_schema={"type": "object", "properties": {}}, permission="write",
            )
        )

    async def run(self, request):  # noqa: ANN001
        self.ran.append(request)
        return _FakeResult(f"echo: {request.input.query}")


@pytest.fixture()
def env(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    fake = FakeService(store)
    service = ChannelService(fake)
    yield store, fake, service
    store.close()


def _bind(store: ChannelStore, *, scope="operator", external_id="42", kind="telegram"):
    return store.upsert_binding(
        kind=kind, external_id=external_id, external_chat="100",
        display_name="Tester", user_id="u1", tenant_id=None, scope=scope,
    )


# ── scope ─────────────────────────────────────────────────────────────────────
def test_scope_ordering():
    assert scope_allows("operator", "viewer")
    assert scope_allows("assistant", "viewer")
    assert not scope_allows("viewer", "assistant")
    assert not scope_allows("bogus", "viewer")


# ── store ─────────────────────────────────────────────────────────────────────
def test_binding_upsert_and_revoke(env):
    _, _, service = env
    b = _bind(service.store, scope="viewer")
    assert b.scope == "viewer"
    again = service.store.upsert_binding(
        kind="telegram", external_id="42", external_chat="100", display_name="T",
        user_id="u1", tenant_id=None, scope="operator",
    )
    assert again.id == b.id and again.scope == "operator"  # upsert, not duplicate
    assert service.store.revoke_binding(b.id)
    assert service.store.find_binding("telegram", "42").status == "revoked"


def test_seen_idempotency(env):
    _, _, service = env
    assert service.store.mark_seen("telegram", "m1") is True
    assert service.store.mark_seen("telegram", "m1") is False
    assert service.store.mark_seen("telegram", "m2") is True


def test_confirmation_single_use(env):
    _, _, service = env
    from harness.persistence import now_iso

    c = service.store.create_confirmation(
        token="ABC123", binding_id="b1", command_text="/do x", action="do:x",
        resource="x", expires_at=now_iso(),
    )
    assert service.store.claim_confirmation(c.token) is not None
    assert service.store.claim_confirmation(c.token) is None  # already claimed


# ── identity ──────────────────────────────────────────────────────────────────
def test_link_code_roundtrip(env):
    _, _, service = env
    code = create_link_code(service.store, kind="telegram", user_id="u1", tenant_id=None, scope="operator")
    binding, reason = claim_link_code(
        service.store, kind="telegram", code=code.code, external_id="99",
        external_chat="99", display_name="T",
    )
    assert reason == "" and binding is not None and binding.scope == "operator"
    # single-use
    binding2, reason2 = claim_link_code(
        service.store, kind="telegram", code=code.code, external_id="99", external_chat="99",
    )
    assert binding2 is None and "used" in reason2.lower()


def test_link_code_wrong_kind(env):
    _, _, service = env
    code = create_link_code(service.store, kind="telegram", user_id="u1", tenant_id=None, scope="viewer")
    binding, reason = claim_link_code(
        service.store, kind="slack", code=code.code, external_id="1", external_chat="1",
    )
    assert binding is None and "different channel" in reason


def test_link_code_expired(env):
    _, _, service = env
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    service.store.create_link_code(
        code="OLDCODE1", kind="telegram", user_id="u1", tenant_id=None, scope="viewer", expires_at=past,
    )
    binding, reason = claim_link_code(
        service.store, kind="telegram", code="OLDCODE1", external_id="1", external_chat="1",
    )
    assert binding is None and "expired" in reason


# ── commands ──────────────────────────────────────────────────────────────────
def test_parse_commands():
    assert commands.parse("hello").verb == ""
    parsed = commands.parse("/run do the thing")
    assert parsed.verb == "run" and parsed.args == ["do the thing"]
    assert commands.parse("/help").verb == "help"
    assert commands.parse("/link ABC").args == ["ABC"]


# ── dispatch ──────────────────────────────────────────────────────────────────
async def test_help_and_whoami(env):
    _, _, service = env
    b = _bind(service.store, scope="viewer")
    r = await service._dispatcher.dispatch(b, "/help")  # noqa: SLF001
    assert r.status == "ok" and "/confirm" in r.reply
    r2 = await service._dispatcher.dispatch(b, "/whoami")  # noqa: SLF001
    assert "viewer" in r2.reply


async def test_viewer_cannot_run_agent(env):
    _, fake, service = env
    b = _bind(service.store, scope="viewer")
    r = await service._dispatcher.dispatch(b, "what is AAPL trading at?")  # noqa: SLF001
    assert r.status == "denied" and not fake.ran


async def test_assistant_runs_agent(env):
    _, fake, service = env
    b = _bind(service.store, scope="assistant")
    r = await service._dispatcher.dispatch(b, "hello agent")  # noqa: SLF001
    assert r.status == "ok" and r.reply == "echo: hello agent"
    assert fake.ran and fake.ran[0].conversationId == f"channel-{b.id}"


async def test_do_read_tool(env):
    _, _, service = env
    b = _bind(service.store, scope="viewer")
    r = await service._dispatcher.dispatch(b, '/do read_tool {"symbol": "AAPL"}')  # noqa: SLF001
    assert r.status == "ok" and "AAPL" in r.reply


async def test_do_write_requires_operator(env):
    _, _, service = env
    b = _bind(service.store, scope="assistant")
    r = await service._dispatcher.dispatch(b, "/do write_tool {}")  # noqa: SLF001
    assert r.status == "denied" and "operator" in r.reply


async def test_do_write_confirmation_flow(env):
    _, _, service = env
    service.store.set_config("telegram", enabled=True, config={"operatorTools": ["write_tool"]})
    b = _bind(service.store, scope="operator")
    r = await service._dispatcher.dispatch(b, "/do write_tool {}")  # noqa: SLF001
    assert r.status == "confirmation_required"
    token = r.details["confirmationToken"]
    r2 = await service._dispatcher.dispatch(b, f"/confirm {token}")  # noqa: SLF001
    assert r2.status == "ok" and "wrote it" in r2.reply
    # token is single-use
    r3 = await service._dispatcher.dispatch(b, f"/confirm {token}")  # noqa: SLF001
    assert r3.status == "error"


async def test_do_write_not_allowlisted(env):
    _, _, service = env
    b = _bind(service.store, scope="operator")
    r = await service._dispatcher.dispatch(b, "/do write_tool {}")  # noqa: SLF001
    assert r.status == "denied" and "allowlist" in r.reply


# ── explicit mutation verbs ───────────────────────────────────────────────────
async def test_trade_requires_confirmation_then_runs(env):
    _, fake, service = env
    b = _bind(service.store, scope="operator")
    r = await service._dispatcher.dispatch(b, "/trade AAPL buy 10 @ 190")  # noqa: SLF001
    assert r.status == "confirmation_required" and not fake.ran
    r2 = await service._dispatcher.dispatch(b, f"/confirm {r.details['confirmationToken']}")  # noqa: SLF001
    assert r2.status == "ok" and fake.ran
    assert "Record this trade" in fake.ran[0].input.query
    # token is single-use
    r3 = await service._dispatcher.dispatch(b, f"/confirm {r.details['confirmationToken']}")  # noqa: SLF001
    assert r3.status == "error"


async def test_backtest_verb_maps_to_directive(env):
    _, fake, service = env
    b = _bind(service.store, scope="operator")
    r = await service._dispatcher.dispatch(b, "/backtest SMA cross AAPL")  # noqa: SLF001
    await service._dispatcher.dispatch(b, f"/confirm {r.details['confirmationToken']}")  # noqa: SLF001
    assert "Run this backtest" in fake.ran[0].input.query


async def test_mutation_verb_denied_for_assistant(env):
    _, fake, service = env
    b = _bind(service.store, scope="assistant")
    r = await service._dispatcher.dispatch(b, "/trade AAPL")  # noqa: SLF001
    assert r.status == "denied" and not fake.ran


# ── one-sender primitive ──────────────────────────────────────────────────────
async def test_send_outbound_unconfigured(env):
    _, _, service = env
    assert (await service.send_outbound("telegram", "123", "hi"))["ok"] is False


async def test_send_outbound_unknown_kind(env):
    _, _, service = env
    with pytest.raises(ValueError):
        await service.send_outbound("nope", "1", "hi")


# ── service inbound ───────────────────────────────────────────────────────────
async def test_inbound_unlinked_then_link(env):
    _, _, service = env
    code = create_link_code(service.store, kind="telegram", user_id="u1", tenant_id=None, scope="assistant")
    unlinked = await service.handle_inbound(
        InboundMessage(kind="telegram", external_id="7", external_chat="7", text="hi",
                       platform_message_id="u1")
    )
    assert unlinked.status == "unlinked"
    linked = await service.handle_inbound(
        InboundMessage(kind="telegram", external_id="7", external_chat="7",
                       text=f"/link {code.code}", platform_message_id="u2")
    )
    assert linked.status == "linked"
    assert service.store.find_binding("telegram", "7") is not None


async def test_inbound_duplicate_ignored(env):
    _, _, service = env
    _bind(service.store, external_id="5")
    msg = InboundMessage(kind="telegram", external_id="5", external_chat="100",
                         text="/help", platform_message_id="dup")
    first = await service.handle_inbound(msg)
    second = await service.handle_inbound(msg)
    assert first is not None and second is None


def test_config_redaction(env):
    _, _, service = env
    service.configure("telegram", enabled=True, config={"botToken": "secret-value", "agentId": "x"})
    described = service.describe_config("telegram")
    assert described["config"]["botToken"] == "***"
    assert described["config"]["agentId"] == "x"
    assert described["configured"] is True
