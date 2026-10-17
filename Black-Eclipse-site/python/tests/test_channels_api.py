"""Channel Gateway API tests — the `/channels/*` operator-gated route group."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.channels.service import ChannelService
from harness.persistence import AgentMemoryStore
from harness.tools import ToolRegistry


class _DummyGateway:
    secrets = None
    audit = None


class StubService:
    def __init__(self, store: AgentMemoryStore) -> None:
        self.store = store
        self.security = _DummyGateway()
        self.registry = ToolRegistry()
        self.channels = ChannelService(self)

    async def run(self, request):  # noqa: ANN001
        class _R:
            output = "ok"
            status = "completed"
            error = None

        return _R()


@pytest.fixture
def client(tmp_workspace, monkeypatch):
    from harness.routers import channels as channels_router

    memory = AgentMemoryStore(str(Path(tmp_workspace) / "agent-memory.db"))
    stub = StubService(memory)
    monkeypatch.setattr(channels_router, "service", stub)

    app = FastAPI()
    app.include_router(channels_router.router)
    with TestClient(app) as test_client:
        yield test_client, stub
    memory.close()


def test_health_and_list(client):
    http, _ = client
    health = http.get("/channels/health").json()
    assert health["success"] and health["available"]
    listed = http.get("/channels").json()
    assert len(listed["channels"]) >= 1
    assert any(c["channel"] == "telegram" for c in listed["channels"])


def test_configure_and_redaction(client):
    http, _ = client
    res = http.put("/channels/telegram", json={"enabled": True, "config": {"botToken": "abc123", "agentId": "z"}})
    assert res.status_code == 200
    cfg = res.json()["channel"]
    assert cfg["enabled"] is True
    assert cfg["config"]["botToken"] == "***"
    assert cfg["config"]["agentId"] == "z"
    assert cfg["configured"] is True


def test_link_code_and_inbound_flow(client):
    http, _ = client
    code = http.post("/channels/link-code", json={"kind": "telegram", "scope": "assistant"}).json()["linkCode"]
    token = code["code"]
    unlinked = http.post("/channels/inbound", json={
        "kind": "telegram", "externalId": "55", "externalChat": "55", "text": "hi",
        "platformMessageId": "m1",
    }).json()
    assert unlinked["result"]["status"] == "unlinked"

    linked = http.post("/channels/inbound", json={
        "kind": "telegram", "externalId": "55", "externalChat": "55",
        "text": f"/link {token}", "platformMessageId": "m2",
    }).json()
    assert linked["result"]["status"] == "linked"

    bindings = http.get("/channels/bindings").json()["bindings"]
    assert any(b["externalId"] == "55" for b in bindings)

    duplicate = http.post("/channels/inbound", json={
        "kind": "telegram", "externalId": "55", "externalChat": "55", "text": "hi",
        "platformMessageId": "m2",
    }).json()
    assert duplicate["duplicate"] is True


def test_binding_scope_and_revoke(client):
    http, stub = client
    code = http.post("/channels/link-code", json={"kind": "telegram", "scope": "viewer"}).json()["linkCode"]
    http.post("/channels/inbound", json={
        "kind": "telegram", "externalId": "77", "externalChat": "77",
        "text": f"/link {code['code']}", "platformMessageId": "x1",
    })
    binding = next(b for b in http.get("/channels/bindings").json()["bindings"] if b["externalId"] == "77")
    assert http.post(f"/channels/bindings/{binding['id']}/scope", json={"scope": "operator"}).status_code == 200
    assert http.delete(f"/channels/bindings/{binding['id']}").json()["revoked"] is True


def test_unknown_kind_rejected(client):
    http, _ = client
    assert http.put("/channels/nope", json={"enabled": True, "config": {}}).status_code == 400
    assert http.post("/channels/link-code", json={"kind": "nope", "scope": "viewer"}).status_code == 400


# ── push providers (signature-verified webhooks) ──────────────────────────────
def _slack_sig(secret: str, ts: int, body: bytes) -> str:
    import hashlib
    import hmac

    base = f"v0:{ts}:".encode() + body
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


def test_slack_url_verification_and_signature(client):
    import time

    http, stub = client
    stub.channels.store.set_config("slack", enabled=True, config={"signingSecret": "s3cr3t", "botToken": "t"})
    body = b'{"type":"url_verification","challenge":"chal-1"}'
    ts = int(time.time())
    ok = http.post(
        "/channels/webhook/slack",
        content=body,
        headers={"X-Slack-Signature": _slack_sig("s3cr3t", ts, body), "X-Slack-Request-Timestamp": str(ts)},
    )
    assert ok.status_code == 200 and ok.json()["challenge"] == "chal-1"

    bad = http.post("/channels/webhook/slack", content=body, headers={"X-Slack-Signature": "v0=nope"})
    assert bad.status_code == 403


def test_generic_webhook_link_flow(client):
    import hashlib
    import hmac

    http, stub = client
    stub.channels.store.set_config("webhook", enabled=True, config={"webhookSecret": "wh", "replyUrl": "http://x"})

    def post(payload: dict):
        import json as _json

        raw = _json.dumps(payload).encode()
        sig = "sha256=" + hmac.new(b"wh", raw, hashlib.sha256).hexdigest()
        return http.post("/channels/webhook/webhook", content=raw, headers={"X-Eclipse-Signature": sig})

    # unsigned / wrong secret refused
    assert http.post("/channels/webhook/webhook", content=b"{}").status_code == 403

    code = http.post("/channels/link-code", json={"kind": "webhook", "scope": "assistant"}).json()["linkCode"]["code"]
    linked = post({"externalId": "phone1", "externalChat": "phone1", "text": f"/link {code}", "messageId": "g1"})
    assert linked.status_code == 200 and linked.json()["ok"]

    bindings = http.get("/channels/bindings").json()["bindings"]
    assert any(b["externalId"] == "phone1" for b in bindings)

    # duplicate message id is reported, not reprocessed
    dup = post({"externalId": "phone1", "externalChat": "phone1", "text": "hi", "messageId": "g1"})
    assert dup.json()["duplicate"] is True


def test_send_endpoint(client):
    http, _ = client
    res = http.post("/channels/send", json={"kind": "telegram", "chat": "1", "text": "hi"})
    assert res.status_code == 200 and res.json()["ok"] is False  # not configured
    assert http.post("/channels/send", json={"kind": "nope", "chat": "1", "text": "hi"}).status_code == 400


def test_whatsapp_verification_handshake(client):
    http, stub = client
    stub.channels.store.set_config("whatsapp", enabled=True, config={"verifyToken": "vtok", "appSecret": "as"})
    ok = http.get(
        "/channels/webhook/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "vtok", "hub.challenge": "CH"},
    )
    assert ok.status_code == 200 and ok.text == "CH"
    bad = http.get(
        "/channels/webhook/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "CH"},
    )
    assert bad.status_code == 403
