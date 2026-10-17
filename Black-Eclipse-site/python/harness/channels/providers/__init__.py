"""Channel provider adapters.

Each module implements one external messaging surface behind the
`transport.InboundTransport` / `transport.OutboundTransport` contracts. Providers
contain NO agent logic — they normalize inbound traffic and send replies.

* `telegram` — long-poll `getUpdates` + `sendMessage`
* `discord`  — Gateway WebSocket (inbound) + REST (outbound)
* `email`    — IMAP inbound + SMTP outbound
* `webhooks` — Slack / WhatsApp / generic: outbound HTTP + pure payload parsers
  (inbound arrives at the public `/channels/webhook/{kind}` route)
"""

from __future__ import annotations

from .discord import DiscordProvider
from .email import EmailProvider
from .telegram import TelegramProvider
from .webhooks import SlackProvider, WebhookProvider, WhatsappProvider

__all__ = [
    "DiscordProvider",
    "EmailProvider",
    "SlackProvider",
    "TelegramProvider",
    "WebhookProvider",
    "WhatsappProvider",
]
