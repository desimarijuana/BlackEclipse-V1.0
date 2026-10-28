"""Channel provider adapters.

Each module implements one external messaging surface behind the
`transport.InboundTransport` / `transport.OutboundTransport` contracts. Providers
contain NO agent logic — they normalize inbound traffic and send replies.

* `telegram`    — long-poll `getUpdates` + `sendMessage`
* `discord`     — Gateway WebSocket (inbound) + REST (outbound)
* `email`       — IMAP inbound + SMTP outbound
* `slack`       — Socket Mode inbound (no public URL) + Web API outbound
* `teams`       — Bot Framework webhook inbound + connector outbound
* `google_chat` — Chat app webhook inbound + Chat API outbound
* `lark`        — Lark event webhook inbound + IM API outbound
* `webhooks`    — WhatsApp / generic: outbound HTTP + pure payload parsers
  (inbound arrives at the public `/channels/webhook/{kind}` route)
"""

from __future__ import annotations

from .discord import DiscordProvider
from .email import EmailProvider
from .google_chat import GoogleChatProvider
from .lark import LarkProvider
from .slack import SlackProvider
from .teams import TeamsProvider
from .telegram import TelegramProvider
from .webhooks import WebhookProvider, WhatsappProvider

__all__ = [
    "DiscordProvider",
    "EmailProvider",
    "GoogleChatProvider",
    "LarkProvider",
    "SlackProvider",
    "TeamsProvider",
    "TelegramProvider",
    "WebhookProvider",
    "WhatsappProvider",
]
