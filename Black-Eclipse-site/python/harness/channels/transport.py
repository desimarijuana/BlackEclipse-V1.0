"""Transport contracts for channel providers.

A provider supplies an INBOUND half (receive messages) and an OUTBOUND half (send
a reply). A pull-based provider (Telegram long-poll, IMAP) implements `run()` as a
loop; a push-based provider (a webhook endpoint) implements `received()` and the
router calls it. Both halves are thin — no agent loop, no second registry.

`OutboundMessage.text` is already rendered/redacted by the dispatcher; a transport
never inspects or stores it beyond the platform's own history.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol, runtime_checkable

from .model import InboundMessage

MessageHandler = Callable[[InboundMessage], Awaitable[None]]


@dataclass
class OutboundMessage:
    kind: str
    external_chat: str
    text: str


@runtime_checkable
class OutboundTransport(Protocol):
    """Sends a reply to an external chat. Returns True on delivery."""

    kind: str

    async def send(self, message: OutboundMessage) -> bool:  # pragma: no cover - protocol
        ...


@runtime_checkable
class InboundTransport(Protocol):
    """A pull-based inbound source. `run` blocks until `stop` is called."""

    kind: str

    async def run(self, on_message: MessageHandler) -> None:  # pragma: no cover - protocol
        ...

    async def stop(self) -> None:  # pragma: no cover - protocol
        ...


__all__ = ["InboundTransport", "MessageHandler", "OutboundMessage", "OutboundTransport"]
