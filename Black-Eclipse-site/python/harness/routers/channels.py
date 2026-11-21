"""Channel Gateway route group — `/channels/*`.

Operator-gated (transport/token), matching the rest of the runtime. This is the
control surface behind Settings › Connections: channel config, link-code minting,
binding management, message history, plus an inbound injection endpoint used by
push providers and the UI/test surface. Config values are ALWAYS redacted — a
credential is never returned over the wire.
"""

from __future__ import annotations

from typing import Any, Optional

import hmac
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ..channels import verify as channel_verify
from ..channels.attachments import attachment_from_api
from ..channels.providers import google_chat as channel_google_chat
from ..channels.providers import lark as channel_lark
from ..channels.providers import teams as channel_teams
from ..channels.providers import webhooks as channel_webhooks

from ..channels.bootstrap import channel_service, install_channel_layer
from ..channels.model import CHANNEL_KINDS, CONTROL_SCOPES, InboundMessage
from ..channels.registry import PUSH_KINDS
from ..deps import identity_for, require_operator, service

router = APIRouter(tags=["channels"], prefix="/channels")


def _channels():
    return channel_service(service) or install_channel_layer(service)


class ChannelConfigRequest(BaseModel):
    enabled: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class LinkCodeRequest(BaseModel):
    kind: str
    scope: str = "viewer"
    ttlS: Optional[int] = None  # noqa: N815


class BindingScopeRequest(BaseModel):
    scope: str


class SendAttachmentRequest(BaseModel):
    name: str = ""
    mimeType: str = ""  # noqa: N815
    url: str = ""
    contentBase64: str = ""  # noqa: N815


class SendRequest(BaseModel):
    kind: str
    chat: str
    text: str = Field("", max_length=4000)
    attachments: list[SendAttachmentRequest] = Field(default_factory=list, max_length=10)


class InboundRequest(BaseModel):
    kind: str
    externalId: str  # noqa: N815
    externalChat: Optional[str] = None  # noqa: N815
    text: str = ""
    platformMessageId: Optional[str] = None  # noqa: N815
    displayName: str = ""  # noqa: N815


# ── static routes FIRST ───────────────────────────────────────────────────────
@router.get("/health")
def channels_health(_: bool = Depends(require_operator)) -> dict[str, Any]:
    svc = _channels()
    if svc is None:
        return {"success": True, "available": False, "reason": "channel gateway unavailable"}
    return {"success": True, "available": True, **svc.health()}


@router.get("")
def list_channels(_: bool = Depends(require_operator)) -> dict[str, Any]:
    svc = _channels()
    if svc is None:
        return {"success": True, "channels": []}
    return {"success": True, "channels": svc.describe_all()}


@router.post("/link-code")
def create_link_code(
    body: LinkCodeRequest, request: Request, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    svc = _channels()
    if svc is None:
        raise HTTPException(status_code=503, detail="channel gateway unavailable")
    if body.kind not in CHANNEL_KINDS:
        raise HTTPException(status_code=400, detail=f"unknown channel kind: {body.kind}")
    if body.scope not in CONTROL_SCOPES:
        raise HTTPException(status_code=400, detail=f"unknown scope: {body.scope}")
    identity = identity_for(request)
    user_id = getattr(identity, "user_id", None)
    tenant_id = getattr(identity, "tenant_id", None)
    return {"success": True, "linkCode": svc.create_link_code(
        kind=body.kind, scope=body.scope, user_id=user_id, tenant_id=tenant_id, ttl_s=body.ttlS,
    )}


@router.get("/bindings")
def list_bindings(kind: Optional[str] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    svc = _channels()
    if svc is None:
        return {"success": True, "bindings": []}
    return {"success": True, "bindings": svc.list_bindings(kind=kind)}


@router.get("/messages")
def list_messages(
    kind: Optional[str] = None,
    bindingId: Optional[str] = None,  # noqa: N803
    limit: int = Query(100, ge=1, le=1000),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    svc = _channels()
    if svc is None:
        return {"success": True, "messages": []}
    return {"success": True, "messages": svc.list_messages(kind=kind, binding_id=bindingId, limit=limit)}


@router.post("/inbound")
async def inbound(body: InboundRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Ingest one normalized inbound message (push providers, UI, tests)."""
    svc = _channels()
    if svc is None:
        raise HTTPException(status_code=503, detail="channel gateway unavailable")
    if body.kind not in CHANNEL_KINDS:
        raise HTTPException(status_code=400, detail=f"unknown channel kind: {body.kind}")
    message = InboundMessage(
        kind=body.kind,
        external_id=body.externalId,
        external_chat=body.externalChat or body.externalId,
        text=body.text,
        platform_message_id=body.platformMessageId or "",
        display_name=body.displayName,
    )
    result = await svc.handle_inbound(message)
    if result is None:
        return {"success": True, "duplicate": True}
    return {"success": True, "duplicate": False, "result": result.to_dict()}


@router.post("/send")
async def send_outbound(body: SendRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Send one outbound message through a configured channel (the ONE sender)."""
    svc = _channels()
    if svc is None:
        raise HTTPException(status_code=503, detail="channel gateway unavailable")
    if body.kind not in CHANNEL_KINDS:
        raise HTTPException(status_code=400, detail=f"unknown channel kind: {body.kind}")
    attachments = [
        attachment_from_api(
            name=item.name,
            mime_type=item.mimeType,
            url=item.url,
            content_base64=item.contentBase64,
        )
        for item in body.attachments
    ]
    for attachment in attachments:
        if attachment.data is None and not attachment.url.startswith("https://"):
            raise HTTPException(
                status_code=400,
                detail="each attachment needs valid contentBase64 or an https URL",
            )
    if not body.text.strip() and not attachments:
        raise HTTPException(status_code=400, detail="send requires text or an attachment")
    result = await svc.send_outbound(
        body.kind, body.chat, body.text, attachments=attachments or None
    )
    return {"success": True, **result}


# ── dynamic routes ────────────────────────────────────────────────────────────
@router.put("/{kind}")
def configure_channel(
    kind: str, body: ChannelConfigRequest, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    svc = _channels()
    if svc is None:
        raise HTTPException(status_code=503, detail="channel gateway unavailable")
    try:
        return {"success": True, "channel": svc.configure(kind, enabled=body.enabled, config=body.config)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{kind}")
def delete_channel(kind: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    svc = _channels()
    if svc is None:
        raise HTTPException(status_code=503, detail="channel gateway unavailable")
    return {"success": True, "deleted": svc.delete_config(kind)}


@router.post("/bindings/{binding_id}/scope")
def set_binding_scope(
    binding_id: str, body: BindingScopeRequest, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    svc = _channels()
    if svc is None:
        raise HTTPException(status_code=503, detail="channel gateway unavailable")
    if body.scope not in CONTROL_SCOPES:
        raise HTTPException(status_code=400, detail=f"unknown scope: {body.scope}")
    if not svc.set_binding_scope(binding_id, body.scope):
        raise HTTPException(status_code=404, detail="binding not found")
    return {"success": True, "bindingId": binding_id, "scope": body.scope}


@router.delete("/bindings/{binding_id}")
def revoke_binding(binding_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    svc = _channels()
    if svc is None:
        raise HTTPException(status_code=503, detail="channel gateway unavailable")
    return {"success": True, "revoked": svc.revoke_binding(binding_id)}


# ── public webhook receivers (signature-verified, NOT operator-gated) ─────────
# A push provider (Slack/WhatsApp/generic) is an EXTERNAL service; it cannot send
# the operator token. Authenticity is proven by an HMAC over the RAW body under a
# per-channel secret. A missing/mismatched signature is refused. The set is
# registry-derived so a new push provider cannot be silently unreachable.
_PUSH_KINDS = PUSH_KINDS


def _enqueue(svc: Any, message: InboundMessage, background: BackgroundTasks) -> bool:
    """Claim synchronously, process after the ACK.

    External providers retry when an ACK is slow, and an agent turn can take
    seconds. The claim is the idempotency gate; the turn runs after the 200.
    """
    accepted = svc.accept_inbound(message)
    if accepted:
        background.add_task(svc.process_inbound, message)
    return accepted


@router.get("/webhook/{kind}")
async def webhook_verify(kind: str, request: Request) -> PlainTextResponse:
    """Provider subscription handshake (WhatsApp/Meta `hub.challenge`)."""
    if kind != "whatsapp":
        raise HTTPException(status_code=404, detail="no verification handshake for this channel")
    svc = _channels()
    if svc is None:
        raise HTTPException(status_code=503, detail="channel gateway unavailable")
    params = request.query_params
    verify_token = svc.secret_value("whatsapp", "verifyToken")
    if (
        params.get("hub.mode") == "subscribe"
        and verify_token
        and params.get("hub.verify_token") == verify_token
        and params.get("hub.challenge")
    ):
        return PlainTextResponse(params.get("hub.challenge") or "")
    raise HTTPException(status_code=403, detail="verification failed")


@router.post("/webhook/{kind}")
async def webhook_inbound(
    kind: str, request: Request, background: BackgroundTasks
) -> dict[str, Any]:
    if kind not in _PUSH_KINDS:
        raise HTTPException(status_code=404, detail=f"unknown webhook channel: {kind}")
    svc = _channels()
    if svc is None:
        raise HTTPException(status_code=503, detail="channel gateway unavailable")

    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    if kind == "slack":
        secret = svc.secret_value("slack", "signingSecret")
        if not channel_verify.verify_slack(
            secret,
            timestamp=headers.get("x-slack-request-timestamp"),
            body=body,
            signature=headers.get("x-slack-signature"),
        ):
            raise HTTPException(status_code=403, detail="invalid slack signature")
        payload = _safe_json(body)
        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge", "")}
        message = channel_webhooks.parse_slack(payload)
        accepted = _enqueue(svc, message, background)
        return {"ok": True, "duplicate": message is not None and not accepted}

    if kind == "whatsapp":
        secret = svc.secret_value("whatsapp", "appSecret")
        if not channel_verify.verify_whatsapp(
            secret, body=body, signature=headers.get("x-hub-signature-256")
        ):
            raise HTTPException(status_code=403, detail="invalid whatsapp signature")
        messages = channel_webhooks.parse_whatsapp(_safe_json(body))
        accepted = 0
        for message in messages:
            if _enqueue(svc, message, background):
                accepted += 1
        return {"ok": True, "accepted": accepted, "duplicate": bool(messages) and accepted == 0}

    if kind == "teams":
        app_id = svc.secret_value("teams", "appId")
        token = _bearer(headers.get("authorization"))
        if not channel_verify.verify_teams(token, app_id=app_id):
            raise HTTPException(status_code=403, detail="invalid teams token")
        message = channel_teams.parse_activity(_safe_json(body))
        accepted = _enqueue(svc, message, background) if message is not None else False
        return {"ok": True, "duplicate": message is not None and not accepted}

    if kind == "google_chat":
        audience = svc.secret_value("google_chat", "projectNumber") or svc.secret_value(
            "google_chat", "pubsubAudience"
        )
        if not audience:
            raise HTTPException(status_code=503, detail="google chat inbound requires a project number / audience")
        token = _bearer(headers.get("authorization"))
        if not channel_verify.verify_google_chat(token, audience=audience):
            raise HTTPException(status_code=403, detail="invalid google chat token")
        message = channel_google_chat.parse_event(_safe_json(body))
        accepted = _enqueue(svc, message, background) if message is not None else False
        return {"ok": True, "duplicate": message is not None and not accepted}

    if kind == "lark":
        payload = _safe_json(body)
        encrypt_key = svc.secret_value("lark", "encryptKey")
        if payload.get("encrypt"):
            if not encrypt_key:
                raise HTTPException(status_code=403, detail="lark payload is encrypted but no encrypt key is configured")
            if not channel_verify.verify_lark(
                encrypt_key,
                timestamp=headers.get("x-lark-request-timestamp"),
                nonce=headers.get("x-lark-request-nonce"),
                body=body,
                signature=headers.get("x-lark-signature"),
            ):
                raise HTTPException(status_code=403, detail="invalid lark signature")
            decrypted = channel_verify.decrypt_lark(encrypt_key, str(payload.get("encrypt")))
            if decrypted is None:
                raise HTTPException(status_code=403, detail="invalid lark ciphertext")
            payload = decrypted
        else:
            expected = svc.secret_value("lark", "verificationToken")
            if not expected and not encrypt_key:
                raise HTTPException(
                    status_code=403,
                    detail="lark inbound requires a verification token or encrypt key",
                )
            provided = (payload.get("header") or {}).get("token") or payload.get("token") or ""
            if expected and not hmac.compare_digest(str(expected), str(provided)):
                raise HTTPException(status_code=403, detail="invalid lark verification token")

        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge", "")}
        message = channel_lark.parse_event(payload)
        accepted = _enqueue(svc, message, background) if message is not None else False
        return {"ok": True, "duplicate": message is not None and not accepted}

    # Viber signs the RAW BODY with a HEX HMAC (LINE's sibling, different digest).
    if kind == "viber":
        from ..channels.providers import viber as channel_viber  # noqa: PLC0415

        token = svc.secret_value("viber", "authToken")
        if not channel_viber.verify(token, body=body,
                                    signature=headers.get("x-viber-content-signature")):
            raise HTTPException(status_code=403, detail="invalid viber signature")
        message = channel_viber.parse_webhook(_safe_json(body))
        accepted = _enqueue(svc, message, background) if message is not None else False
        # Viber expects a bare 200 with no body; it treats anything else as a retry.
        return {"ok": True, "duplicate": message is not None and not accepted}

    # LINE signs the RAW BODY only (no timestamp, no URL): body HMAC, one check.
    if kind == "line":
        from ..channels.providers import line as channel_line  # noqa: PLC0415

        secret = svc.secret_value("line", "channelSecret")
        if not channel_line.verify(secret, body=body,
                                   signature=headers.get("x-line-signature")):
            raise HTTPException(status_code=403, detail="invalid line signature")
        messages = channel_line.parse_webhook(_safe_json(body))
        accepted = 0
        for message in messages:
            if _enqueue(svc, message, background):
                accepted += 1
        return {"ok": True, "accepted": accepted,
                "duplicate": bool(messages) and accepted == 0}

    # Twilio posts a FORM, not JSON, and signs the public URL + sorted params.
    if kind == "twilio":
        import urllib.parse  # noqa: PLC0415 - only this branch needs it

        from ..channels.providers import twilio as channel_twilio  # noqa: PLC0415

        token = svc.secret_value("twilio", "authToken")
        public_url = svc.secret_value("twilio", "publicUrl")
        if not public_url:
            raise HTTPException(
                status_code=503,
                detail="twilio inbound requires `publicUrl` (the exact URL Twilio signs)",
            )
        form = {
            key: values[0]
            for key, values in urllib.parse.parse_qs(
                body.decode("utf-8", errors="replace"), keep_blank_values=True
            ).items()
        }
        if not channel_twilio.verify(
            token, url=public_url, params=form,
            signature=headers.get("x-twilio-signature"),
        ):
            raise HTTPException(status_code=403, detail="invalid twilio signature")
        message = channel_twilio.parse_inbound(
            form, bot_number=svc.secret_value("twilio", "fromNumber"))
        accepted = _enqueue(svc, message, background) if message is not None else False
        return {"ok": True, "duplicate": message is not None and not accepted}

    # generic webhook
    secret = svc.secret_value("webhook", "webhookSecret")
    if not channel_verify.verify_generic(
        secret, body=body, signature=headers.get("x-eclipse-signature")
    ):
        raise HTTPException(status_code=403, detail="invalid webhook signature")
    message = channel_webhooks.parse_generic(_safe_json(body))
    if message is None:
        raise HTTPException(status_code=400, detail="webhook body must include externalId and text")
    accepted = _enqueue(svc, message, background)
    return {"ok": True, "duplicate": not accepted}


def _bearer(value: Optional[str]) -> str:
    raw = str(value or "").strip()
    return raw[7:].strip() if raw.lower().startswith("bearer ") else ""


def _safe_json(body: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


__all__ = ["router"]
