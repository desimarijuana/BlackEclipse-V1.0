"""Provider registry and fast-ACK contracts.

The registry is the single source of truth for channel kinds, required config
and inbound mode. These tests keep the service, router and specs from drifting.
"""

from __future__ import annotations

from pathlib import Path

from starlette.background import BackgroundTasks

from harness.channels import registry
from harness.channels.model import CHANNEL_KINDS, InboundMessage
from harness.channels.provider import ProviderContext
from harness.channels.service import ChannelService
from harness.persistence import AgentMemoryStore
from harness.routers import channels as channels_router
from harness.tools import ToolRegistry


class _DummyGateway:
    secrets = None
    audit = None


class _StubService:
    def __init__(self, store: AgentMemoryStore) -> None:
        self.store = store
        self.security = _DummyGateway()
        self.registry = ToolRegistry()
        self.channels = ChannelService(self)


def _service(tmp_path) -> tuple[AgentMemoryStore, ChannelService]:
    store = AgentMemoryStore(str(Path(tmp_path) / "agent-memory.db"))
    return store, _StubService(store).channels


def test_kinds_are_derived_and_partitioned():
    assert CHANNEL_KINDS == registry.KINDS
    assert registry.PUSH_KINDS | registry.POLL_KINDS == frozenset(registry.KINDS)
    # A hybrid provider (Slack: Socket Mode + Events webhook) may appear in both.
    assert registry.PUSH_KINDS <= frozenset(registry.KINDS)
    assert registry.POLL_KINDS <= frozenset(registry.KINDS)
    for kind, spec in registry.PROVIDERS.items():
        assert spec.kind == kind
        assert spec.label
        assert spec.required_keys or spec.any_required, f"{kind} must declare required credentials"


def test_every_spec_builds_a_transport_with_credentials():
    for kind in registry.KINDS:
        provider = registry.build_provider(
            ProviderContext(kind=kind, config={}, secret=lambda _key: "x")
        )
        assert provider is not None, kind
        assert provider.kind == kind


def test_missing_required_credential_returns_none():
    provider = registry.build_provider(
        ProviderContext(
            kind="whatsapp",
            config={},
            secret=lambda key: "x" if key == "accessToken" else "",
        )
    )
    assert provider is None


def test_is_configured_uses_required_fields():
    present = {"accessToken", "phoneNumberId"}
    assert registry.is_configured("whatsapp", lambda key: key in present)
    assert not registry.is_configured("whatsapp", lambda key: key == "accessToken")
    assert registry.is_configured("email", lambda key: key == "imapHost")
    # Boolean-ish alternative credentials must be truthy, not merely present.
    assert registry.is_configured("google_chat", lambda key: "true" if key == "useAdc" else "")
    assert not registry.is_configured("google_chat", lambda key: "false" if key == "useAdc" else "")


def test_describe_config_exposes_metadata_without_secret_values(tmp_path):
    store, service = _service(tmp_path)
    try:
        service.configure("slack", enabled=True, config={"botToken": "xoxb-secret"})
        described = service.describe_config("slack")
        assert described["label"] == "Slack"
        assert described["inboundMode"] == "both"
        assert described["config"]["botToken"] == "***"
        fields = {field["key"]: field for field in described["fields"]}
        assert fields["botToken"]["required"] is True
        assert fields["botToken"]["secret"] is True
    finally:
        store.close()


def test_enqueue_claims_then_defers_processing():
    class _Svc:
        def __init__(self, accepted: bool) -> None:
            self.accepted = accepted
            self.calls: list[InboundMessage] = []

        def accept_inbound(self, message: InboundMessage) -> bool:
            return self.accepted

        async def process_inbound(self, message: InboundMessage):  # noqa: ANN201
            self.calls.append(message)

    message = InboundMessage(
        kind="webhook",
        external_id="u1",
        external_chat="u1",
        text="hi",
        platform_message_id="m1",
    )

    accepted = _Svc(True)
    background = BackgroundTasks()
    assert channels_router._enqueue(accepted, message, background) is True
    assert len(background.tasks) == 1
    assert accepted.calls == []  # not awaited on the ACK path

    duplicate = _Svc(False)
    background = BackgroundTasks()
    assert channels_router._enqueue(duplicate, message, background) is False
    assert background.tasks == []

def test_attachment_context_is_metadata_only():
    from harness.channels.dispatch import _attachment_context
    from harness.channels.model import Attachment

    note = _attachment_context([
        Attachment(id="f1", name="a.pdf", mime_type="application/pdf", size=12, url="https://x/a"),
    ])
    assert "a.pdf" in note
    assert "application/pdf" in note
    assert "12 bytes" in note
    assert "do not invent" in note.lower()
    assert _attachment_context([]) == ""
