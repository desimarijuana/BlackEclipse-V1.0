"""The typed A2A message protocol.

Messages are NEVER arbitrary strings: every message is an `AgentEnvelope` with a
closed `MessageType` and a validated payload shape per type. This module owns the
pure protocol rules — payload validation, correlation, and the idempotency key
that makes delivery safe to retry.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional

from .model import (
    DEFAULT_ENVELOPE_TTL_S,
    AgentEnvelope,
    MessagePriority,
    MessageType,
)

#: The payload keys each message type REQUIRES. A message missing one is refused
#: before it is persisted, so a consumer never has to defend against a malformed
#: envelope it should never have received.
PAYLOAD_REQUIRED: dict[MessageType, tuple[str, ...]] = {
    MessageType.TASK_REQUEST: ("objective",),
    MessageType.TASK_RESPONSE: ("status",),
    MessageType.FINDING: ("claim",),
    MessageType.EVIDENCE: ("evidenceRefs",),
    MessageType.QUESTION: ("question",),
    MessageType.ANSWER: ("question", "answer"),
    MessageType.DELEGATION: ("childAgentId", "objective"),
    MessageType.STATUS: ("status",),
    MessageType.FAILURE: ("error",),
    MessageType.APPROVAL_REQUEST: ("subject",),
    MessageType.APPROVAL_RESPONSE: ("approvalId", "decision"),
    MessageType.REVIEW_REQUEST: ("subject",),
    MessageType.REVIEW_RESPONSE: ("verdict",),
    MessageType.CANCEL: ("targetId",),
}


class ProtocolError(ValueError):
    """A malformed envelope. ``code`` is stable and testable."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def canonical_key(envelope: AgentEnvelope) -> str:
    """A stable idempotency key. Two identical sends collapse to one delivery.

    An explicit `idempotencyKey` always wins (so a caller can control the unit of
    idempotency). Otherwise the key is a digest of the identity-bearing fields —
    NOT the timestamp, so a retry of the same logical message dedupes.
    """
    if envelope.idempotency_key:
        return envelope.idempotency_key
    # The auto-generated correlation id is deliberately EXCLUDED: it is random
    # per send, so including it would defeat idempotency. Identity is the message's
    # logical content (type/sender/recipient/run/task/payload).
    material = json.dumps(
        {
            "type": envelope.type.value,
            "sender": envelope.sender_agent_id,
            "recipient": envelope.recipient_agent_id,
            "runId": envelope.run_id,
            "taskId": envelope.task_id,
            "payload": envelope.payload,
        },
        sort_keys=True, default=str,
    )
    return "idem_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def validate_envelope(envelope: AgentEnvelope) -> None:
    """Refuse a structurally invalid envelope with a named reason."""
    if not envelope.sender_agent_id:
        raise ProtocolError("A2A_NO_SENDER", "an envelope must name a sender")
    # A missing recipient is a BROADCAST (fan-out to every active agent), not an
    # error — the bus expands it to one delivery per active agent.
    required = PAYLOAD_REQUIRED.get(envelope.type, ())
    missing = [key for key in required if not envelope.payload.get(key)]
    if missing:
        raise ProtocolError(
            "A2A_PAYLOAD_INVALID",
            f"{envelope.type.value} needs {', '.join(missing)}",
        )
    if len(json.dumps(envelope.payload, default=str)) > 100_000:
        raise ProtocolError("A2A_PAYLOAD_TOO_LARGE", "the message payload is too large")


def ensure_correlation(envelope: AgentEnvelope) -> AgentEnvelope:
    """Give the envelope a correlation id if it lacks one (in place + return)."""
    if not envelope.correlation_id:
        envelope.correlation_id = "cor_" + uuid.uuid4().hex[:16]
    if not envelope.idempotency_key:
        envelope.idempotency_key = canonical_key(envelope)
    return envelope


def make_envelope(
    message_type: MessageType | str,
    *,
    sender: str,
    recipient: Optional[str] = None,
    run_id: str = "",
    task_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    reply_to: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    evidence_refs: Optional[list[str]] = None,
    permissions: Optional[dict[str, Any]] = None,
    priority: MessagePriority | str = MessagePriority.NORMAL,
    ttl: int = DEFAULT_ENVELOPE_TTL_S,
) -> AgentEnvelope:
    """Build, validate and correlate an envelope in one call."""
    envelope = AgentEnvelope(
        type=MessageType(message_type) if not isinstance(message_type, MessageType) else message_type,
        run_id=run_id, task_id=task_id, sender_agent_id=sender,
        recipient_agent_id=recipient, correlation_id=correlation_id, reply_to=reply_to,
        priority=MessagePriority(priority) if not isinstance(priority, MessagePriority) else priority,
        payload=dict(payload or {}), evidence_refs=list(evidence_refs or []),
        permissions=dict(permissions or {}), ttl=ttl,
    )
    ensure_correlation(envelope)
    validate_envelope(envelope)
    return envelope


__all__ = [
    "PAYLOAD_REQUIRED",
    "ProtocolError",
    "canonical_key",
    "ensure_correlation",
    "make_envelope",
    "validate_envelope",
]
