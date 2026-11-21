"""OpenBB Workspace protocol models (the subset a custom agent receives).

OpenBB Workspace calls a custom agent with one stateless `POST /v1/query` whose
body carries the whole conversation plus workspace context. There is **no thread
id**: `QueryRequest` fields are `messages`, `context`, `widgets`, `urls`,
`api_keys`, `force_web_search`, `timezone`, `workspace_state`,
`workspace_options`, `tools`.

These models are deliberately tolerant (`extra="allow"`): OpenBB adds fields
between releases, and rejecting a request because a new key appeared would break
the integration for a cosmetic reason. Unknown keys are preserved, never trusted.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["user", "assistant", "system", "tool"]

MAX_MESSAGES = 200
MAX_MESSAGE_CHARS = 24_000
MAX_CONTEXT_ITEMS = 40
MAX_INJECTED_CHARS = 6_000


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Role = "user"
    content: str = ""

    def clipped(self, limit: int = MAX_MESSAGE_CHARS) -> str:
        text = str(self.content or "")
        return text if len(text) <= limit else text[: limit - 1] + "…"


class ContextItem(BaseModel):
    """One workspace context item (a widget, a dashboard, a selected row)."""

    model_config = ConfigDict(extra="allow")

    type: str = "text"
    name: str = ""
    description: str = ""
    data: Any = None

    def render(self) -> str:
        """A bounded, plain-text projection — never the raw payload."""
        parts = [f"[{self.type}] {self.name}".strip()]
        if self.description:
            parts.append(str(self.description)[:500])
        if self.data is not None:
            parts.append(str(self.data)[:1_000])
        return "\n".join(parts)


class QueryRequest(BaseModel):
    """The body of one `POST /v1/query`."""

    model_config = ConfigDict(extra="allow")

    messages: list[ChatMessage] = Field(default_factory=list)
    context: list[ContextItem] = Field(default_factory=list)
    widgets: list[Any] = Field(default_factory=list)
    urls: list[Any] = Field(default_factory=list)
    #: Provider keys OpenBB forwards for the agent. They are NEVER echoed or logged.
    api_keys: dict[str, Any] = Field(default_factory=dict)
    force_web_search: bool = False
    timezone: str = ""
    workspace_state: dict[str, Any] = Field(default_factory=dict)
    workspace_options: dict[str, Any] = Field(default_factory=dict)
    tools: list[Any] = Field(default_factory=list)


class PreparedQuery(BaseModel):
    """What the bridge hands to the harness: history plus one composed user turn."""

    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage]
    user_message: str
    context_items: int = 0
    api_key_names: list[str] = Field(default_factory=list)


__all__ = [
    "ChatMessage",
    "ContextItem",
    "MAX_CONTEXT_ITEMS",
    "MAX_INJECTED_CHARS",
    "MAX_MESSAGES",
    "MAX_MESSAGE_CHARS",
    "PreparedQuery",
    "QueryRequest",
    "Role",
]
