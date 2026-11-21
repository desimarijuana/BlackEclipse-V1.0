"""OpenBB Workspace bridge: a custom agent that speaks the Workspace protocol."""

from __future__ import annotations

from .adapter import (
    BridgeError,
    build_run_request,
    history_payload,
    parse_query,
    prepare,
)
from .event_mapper import map_event, map_events, sse_lines
from .models import ChatMessage, ContextItem, PreparedQuery, QueryRequest
from .stream import openbb_frames

__all__ = [
    "BridgeError",
    "ChatMessage",
    "ContextItem",
    "PreparedQuery",
    "QueryRequest",
    "build_run_request",
    "history_payload",
    "map_event",
    "map_events",
    "openbb_frames",
    "parse_query",
    "prepare",
    "sse_lines",
]
