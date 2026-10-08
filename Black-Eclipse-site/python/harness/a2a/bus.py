"""The A2A message bus.

A durable, correlated, retryable, idempotent delivery layer over the ONE
agent-memory connection. It is NOT an in-memory event emitter: every message and
every per-recipient delivery is a row, so a crash between publish and consume
loses nothing. The process `EventBus` is used only to WAKE live consumers; the
durable row is the source of truth.

    publish(message)      → persist (idempotent) + fan out a delivery per recipient
    consume(queue)       → claim pending deliveries for one recipient
    acknowledge(message) → mark a delivery done
    reject(message)      → count a failed attempt; dead-letter past the limit
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .model import AgentEnvelope, DeliveryStatus
from .protocol import ProtocolError, validate_envelope
from .store import A2AStore

Listener = Callable[[str, dict[str, Any]], None]

DEFAULT_MAX_ATTEMPTS = 3


class MessageBus:
    """Durable publish/consume with acknowledgement, retry and dead-lettering."""

    def __init__(self, store: A2AStore, *, event_bus: Any = None,
                 max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> None:
        self._store = store
        self._event_bus = event_bus
        self._max_attempts = max(1, int(max_attempts))

    # ── publish ───────────────────────────────────────────────────────────────

    def publish(self, envelope: AgentEnvelope) -> tuple[AgentEnvelope, bool]:
        validate_envelope(envelope)
        stored, created = self._store.publish_message(envelope)
        if created:
            self._wake("message.sent", {
                "messageId": stored.id, "type": stored.type.value,
                "senderAgentId": stored.sender_agent_id,
                "recipientAgentId": stored.recipient_agent_id,
                "runId": stored.run_id, "taskId": stored.task_id,
                "correlationId": stored.correlation_id,
            })
        return stored, created

    # ── consume ───────────────────────────────────────────────────────────────

    def consume(self, recipient: str, *, limit: int = 50) -> list[AgentEnvelope]:
        """Claim PENDING deliveries for `recipient` and return their messages."""
        deliveries = self._store.pending_deliveries(recipient, limit=limit)
        messages: list[AgentEnvelope] = []
        for delivery in deliveries:
            message_id = delivery["messageId"]
            envelope = self._store.get_message(message_id)
            if envelope is None:
                self._store.dead_letter(message_id, recipient, "message row missing")
                continue
            if envelope.is_expired():
                self._store.dead_letter(message_id, recipient, "message TTL expired")
                continue
            self._store.mark_delivered(message_id, recipient)
            messages.append(envelope)
            self._wake("message.received", {
                "messageId": message_id, "recipientAgentId": recipient,
                "type": envelope.type.value, "senderAgentId": envelope.sender_agent_id,
            })
        return messages

    def peek(self, recipient: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return self._store.pending_deliveries(recipient, limit=limit)

    # ── ack / reject ──────────────────────────────────────────────────────────

    def acknowledge(self, message_id: str, recipient: str) -> None:
        self._store.acknowledge(message_id, recipient, status=DeliveryStatus.ACKNOWLEDGED)
        self._wake("message.acknowledged", {"messageId": message_id, "recipientAgentId": recipient})

    def reject(self, message_id: str, recipient: str, error: str) -> None:
        """A failed delivery. Retry until the attempt limit, then dead-letter."""
        deliveries = [d for d in self._store.list_deliveries(recipient=recipient, limit=1000)
                      if d["messageId"] == message_id]
        attempts = int(deliveries[0]["attempts"]) if deliveries else 0
        if attempts + 1 >= self._max_attempts:
            self._store.dead_letter(message_id, recipient, error)
            self._wake("message.dead_lettered", {"messageId": message_id, "recipientAgentId": recipient})
        else:
            self._store.reject(message_id, recipient, error)
            self._wake("message.rejected", {"messageId": message_id, "recipientAgentId": recipient})

    # ── queries ───────────────────────────────────────────────────────────────

    def inbox(self, recipient: str, *, limit: int = 100) -> list[AgentEnvelope]:
        return self._store.list_messages(recipient=recipient, limit=limit)

    def thread(self, run_id: str, *, limit: int = 200) -> list[AgentEnvelope]:
        return self._store.list_messages(run_id=run_id, limit=limit)

    def dead_letters(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._store.list_deliveries(status=DeliveryStatus.DEAD_LETTER.value, limit=limit)

    # ── live wakeup ───────────────────────────────────────────────────────────

    def _wake(self, event_type: str, data: dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            import time as _time

            self._event_bus.publish({"type": event_type, "at": _time.time(), "data": data})
        except Exception:  # noqa: BLE001 - a wakeup must never break delivery
            pass


__all__ = ["DEFAULT_MAX_ATTEMPTS", "Listener", "MessageBus", "ProtocolError"]
