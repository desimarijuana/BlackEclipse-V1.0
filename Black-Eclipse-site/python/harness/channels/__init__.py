"""Channel Gateway — remote control of Eclipse over external messaging surfaces.

This package lets a user connect an external account (Telegram, Discord, Email,
Slack, WhatsApp, a generic webhook) to Eclipse so they can query and drive the
application from where they already are.

Design in one paragraph: a provider adapter normalizes an inbound message; the
`ChannelService` resolves the sender to a verified `ChannelBinding`, applies
idempotency + rate limits, and hands the message to the `ChannelDispatcher`. The
dispatcher gates by control scope (`viewer` < `assistant` < `operator`), routes
control commands, agent turns and the operator `/do` tool bridge, and requires an
in-channel `/confirm` for mutations. Nothing here is a second agent loop, tool
registry or effect authorizer: agent turns go through `service.run`, tool calls
through the ONE `ToolRegistry`, and effects through the Security Gateway.
"""

from __future__ import annotations

from .bootstrap import (
    channel_service,
    install_channel_layer,
    start_channels,
    stop_channels,
)
from .model import ChannelBinding, DispatchResult, InboundMessage
from .service import ChannelService
from .store import ChannelStore

__all__ = [
    "ChannelBinding",
    "ChannelService",
    "ChannelStore",
    "DispatchResult",
    "InboundMessage",
    "channel_service",
    "install_channel_layer",
    "start_channels",
    "stop_channels",
]
