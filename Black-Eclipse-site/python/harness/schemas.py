"""Wire contracts for the harness runtime.

These are pydantic mirrors of `src/lib/harness/types/contracts.ts`. The TS side
is authoritative for the shape; this module must stay in lockstep with it. Keep
field names identical so the JSON crossing the bridge is self-describing.

Every model validates external input — the runtime never trusts the caller.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

RunStatus = Literal["created", "running", "completed", "failed", "cancelled"]
HarnessErrorCode = Literal[
    "INVALID_INPUT",
    "PROVIDER_NOT_CONFIGURED",
    "PROVIDER_ERROR",
    "PROVIDER_TIMEOUT",
    "TOOL_NOT_FOUND",
    "TOOL_VALIDATION_FAILED",
    "TOOL_FORBIDDEN",
    "TOOL_TIMEOUT",
    "TOOL_ERROR",
    "MAX_STEPS_EXCEEDED",
    "CANCELLED",
    "PERSISTENCE_ERROR",
    "INTERNAL_ERROR",
]


class HarnessError(BaseModel):
    code: HarnessErrorCode
    message: str
    detail: Optional[str] = None


class ConversationTurn(BaseModel):
    """One prior turn, so a chat follow-up has context."""

    role: Literal["user", "assistant"]
    content: str = Field(max_length=20_000)


class RunDocument(BaseModel):
    """Extracted text of a document the user attached to the conversation.

    The front door performs extraction (the runtime has no filesystem access);
    this is the already-readable text, injected into the user turn.
    """

    name: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=20_000)


class RunInput(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    ticker: Optional[str] = None
    market: Optional[str] = None
    context: Optional[dict[str, Any]] = None
    # Prior conversation turns (oldest first). Bounded so a long chat cannot
    # blow the context window; the runtime keeps the most recent MAX_HISTORY.
    history: Optional[list[ConversationTurn]] = None
    # Attached documents, already extracted to text by the front door.
    documents: Optional[list[RunDocument]] = None

    @field_validator("query")
    @classmethod
    def _strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        return stripped


class ModelSettings(BaseModel):
    """Provider + credentials + model, resolved by the TS side from the vault.

    Credentials arrive here because the Python service cannot read the JDdS
    settings vault. They are never persisted or logged by this service.
    """

    provider: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: str
    temperature: Optional[float] = None


class AgentConfig(BaseModel):
    id: str
    name: str
    systemPrompt: str = Field(min_length=1)  # noqa: N815 - mirror TS field name
    tools: Optional[list[str]] = None
    maxSteps: Optional[int] = Field(default=8, ge=1, le=32)  # noqa: N815
    toolTimeoutMs: Optional[int] = Field(default=20_000, ge=100, le=120_000)  # noqa: N815
    runTimeoutMs: Optional[int] = Field(default=120_000, ge=1000, le=600_000)  # noqa: N815

    model_config = {"populate_by_name": True}


class RunRequest(BaseModel):
    runId: str  # noqa: N815
    input: RunInput
    # Python is authoritative for agents: the front door sends an id and the
    # runtime resolves the AgentConfig (including its system prompt) from its own
    # presets. `agent` is an optional explicit override for callers that need a
    # bespoke configuration; when both are absent the default agent is used.
    agentId: Optional[str] = None  # noqa: N815
    agent: Optional[AgentConfig] = None
    modelSettings: ModelSettings  # noqa: N815
    userId: Optional[str] = None  # noqa: N815
    # Base URL of the TS front door, used ONLY as the read-only JDdS data bridge.
    callbackBaseUrl: str  # noqa: N815
    # Shared secret for the data bridge (matches CRON_SECRET on the TS side).
    callbackToken: Optional[str] = None  # noqa: N815


class RunResult(BaseModel):
    runId: str  # noqa: N815
    status: RunStatus
    output: Optional[str] = None
    error: Optional[HarnessError] = None
    modelSteps: int = 0  # noqa: N815
    toolCalls: int = 0  # noqa: N815
    toolErrors: int = 0  # noqa: N815
    promptTokens: int = 0  # noqa: N815
    completionTokens: int = 0  # noqa: N815
    totalTokens: int = 0  # noqa: N815


EventLiteral = Literal[
    "run.created",
    "run.started",
    "model.requested",
    "model.completed",
    "tool.requested",
    "tool.completed",
    "tool.failed",
    "run.completed",
    "run.failed",
    "run.cancelled",
]


class HarnessEvent(BaseModel):
    runId: str  # noqa: N815
    type: EventLiteral
    data: Optional[dict[str, Any]] = None


class ToolExecutionRequest(BaseModel):
    callId: str  # noqa: N815
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResponse(BaseModel):
    toolCallId: str  # noqa: N815
    name: str
    ok: bool
    text: str
    error: Optional[HarnessError] = None
    durationMs: int = 0  # noqa: N815
