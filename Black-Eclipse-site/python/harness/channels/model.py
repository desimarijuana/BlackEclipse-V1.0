"""Channel Gateway contracts — the vocabulary for remote control.

A *channel* is an external messaging surface (Telegram, Discord, Email, Slack,
WhatsApp, a generic webhook) that a user can connect to Eclipse so they can see
and drive the application from where they already are.

The trust model is the whole point of this module:

  * an inbound message is UNTRUSTED until a `ChannelBinding` resolves its sender
    to a verified Eclipse identity, and
  * every action is authorised by scope (`viewer` < `assistant` < `operator`) and
    by the Security Gateway; the channel never self-authorises.

Nothing here touches the DB or the network — these are pure contracts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

# The closed vocabulary of supported channel kinds. Adding a provider means
# adding its kind here and shipping a transport adapter under `providers/`.
CHANNEL_KINDS: tuple[str, ...] = (
    "telegram",
    "discord",
    "email",
    "slack",
    "whatsapp",
    "webhook",
)

# Control scopes, ordered least → most privileged. A binding carries exactly one.
CONTROL_SCOPES: tuple[str, ...] = ("viewer", "assistant", "operator")
_SCOPE_RANK = {"viewer": 0, "assistant": 1, "operator": 2}

BINDING_STATUSES: tuple[str, ...] = ("active", "revoked")
CONFIRMATION_STATUSES: tuple[str, ...] = ("pending", "confirmed", "cancelled", "expired")


def scope_rank(scope: str) -> int:
    """The numeric rank of a scope, or -1 for an unknown/forged value (fail closed)."""
    return _SCOPE_RANK.get(str(scope or "").lower(), -1)


def scope_allows(have: str, need: str) -> bool:
    """Whether a binding with `have` may perform an action requiring `need`.

    An unknown scope on either side is refused (rank -1 can never be >= need).
    """
    return scope_rank(have) >= scope_rank(need) >= 0


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


@dataclass
class ChannelBinding:
    """A verified link from an external account to an Eclipse identity."""

    id: str
    kind: str
    external_id: str
    external_chat: str
    display_name: str
    user_id: Optional[str]
    tenant_id: Optional[str]
    scope: str
    status: str
    created_at: str
    last_seen_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "externalId": self.external_id,
            "externalChat": self.external_chat,
            "displayName": self.display_name,
            "userId": self.user_id,
            "tenantId": self.tenant_id,
            "scope": self.scope,
            "status": self.status,
            "createdAt": self.created_at,
            "lastSeenAt": self.last_seen_at,
        }


@dataclass
class InboundMessage:
    """A normalized inbound message from a provider adapter."""

    kind: str
    external_id: str
    external_chat: str
    text: str
    platform_message_id: str
    display_name: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class LinkCode:
    """A short-lived, single-use linking code minted in the UI and claimed by a
    message from the external account (`/link <code>`)."""

    code: str
    kind: str
    user_id: Optional[str]
    tenant_id: Optional[str]
    scope: str
    created_at: str
    expires_at: str
    used_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "kind": self.kind,
            "userId": self.user_id,
            "tenantId": self.tenant_id,
            "scope": self.scope,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "usedAt": self.used_at,
        }


@dataclass
class Confirmation:
    """A pending in-channel confirmation for a mutating action.

    The token is bound to (binding, action, resource) and is single-use with a
    short TTL; a remote user replies `/confirm <token>` to execute.
    """

    token: str
    binding_id: str
    command_text: str
    action: str
    resource: str
    created_at: str
    expires_at: str
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "bindingId": self.binding_id,
            "commandText": self.command_text,
            "action": self.action,
            "resource": self.resource,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "status": self.status,
        }


@dataclass
class DispatchResult:
    """The outcome of dispatching one inbound message."""

    status: str
    reply: str
    run_id: Optional[str] = None
    audit_id: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reply": self.reply,
            "runId": self.run_id,
            "auditId": self.audit_id,
            "details": self.details,
        }


__all__ = [
    "BINDING_STATUSES",
    "CHANNEL_KINDS",
    "CONFIRMATION_STATUSES",
    "CONTROL_SCOPES",
    "ChannelBinding",
    "Confirmation",
    "DispatchResult",
    "InboundMessage",
    "LinkCode",
    "new_id",
    "scope_allows",
    "scope_rank",
]
