"""Wire contracts for the harness runtime.

These are pydantic mirrors of `src/lib/harness/types/contracts.ts`. The TS side
is authoritative for the shape; this module must stay in lockstep with it. Keep
field names identical so the JSON crossing the bridge is self-describing.

Every model validates external input — the runtime never trusts the caller.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

RunStatus = Literal["created", "running", "completed", "failed", "cancelled"]
HarnessErrorCode = Literal[
    "INVALID_INPUT",
    "PROVIDER_NOT_CONFIGURED",
    "PROVIDER_ERROR",
    "PROVIDER_TIMEOUT",
    "CONTEXT_OVERFLOW",
    "TOOL_NOT_FOUND",
    "TOOL_VALIDATION_FAILED",
    "TOOL_FORBIDDEN",
    "TOOL_TIMEOUT",
    "TOOL_ERROR",
    "MAX_STEPS_EXCEEDED",
    "TOOL_BUDGET_EXCEEDED",
    "CHECKPOINT_NOT_FOUND",
    "RESUME_CONFLICT",
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

    The TS front door sends camelCase (`baseUrl`/`apiKey`), so aliases are
    generated with `to_camel` AND `populate_by_name` keeps the snake_case
    constructor used by tests/internal callers working. Without this the
    camelCase fields were silently dropped by pydantic and the runtime fell back
    to the catalog default base URL with no key.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    provider: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: str
    temperature: Optional[float] = None
    # Optional operator-declared context window (tokens) for this run. Used ONLY
    # when the catalog cannot resolve one (a local server, a router, a custom
    # endpoint). Never fabricated: absent/None leaves the window unknown and the
    # conservative ceiling applies. Additive, so old callers are unaffected.
    context_window: Optional[int] = Field(default=None, ge=1, le=10_000_000)


class AgentConfig(BaseModel):
    id: str
    name: str
    systemPrompt: str = Field(min_length=1)  # noqa: N815 - mirror TS field name
    tools: Optional[list[str]] = None
    maxSteps: Optional[int] = Field(default=8, ge=1, le=32)  # noqa: N815
    toolTimeoutMs: Optional[int] = Field(default=20_000, ge=100, le=120_000)  # noqa: N815
    runTimeoutMs: Optional[int] = Field(default=120_000, ge=1000, le=600_000)  # noqa: N815
    # The maximum number of tool calls this run may execute in total. A skill
    # manifest declares `limits.maxToolCalls`; the runtime carries it here so it
    # is ENFORCED in the graph, not merely advertised in metadata/prompts. None
    # means unbounded (ordinary chat agents). Enforced per call in `tools_node`.
    maxToolCalls: Optional[int] = Field(default=None, ge=0, le=200)  # noqa: N815
    # Narrow opt-in: when True, the run's effective allowlist is expanded to also
    # include the MCP tools CURRENTLY registered, selected and namespaced in the
    # registry (`mcp_*`). Default False, so a custom/skill agent keeps its exact
    # restricted allowlist and can never call an MCP tool it did not name. It is
    # an expansion over registration state, not permission to call arbitrary
    # tools: registration itself already enforces enabled + selected + read-only.
    allowMcpTools: bool = False  # noqa: N815

    model_config = {"populate_by_name": True}


class RunWorkspace(BaseModel):
    """An optional narrowing/confirmation of the server-resolved workspace root.

    Phase 1 binds only the SERVER-RESOLVED root; a caller-supplied `root` can
    only CONFIRM it. A mismatch means the run gets no workspace at all.
    """

    root: str = Field(min_length=1, max_length=1024)
    baseRevision: Optional[str] = Field(default=None, max_length=128)  # noqa: N815


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
    # M3/M4: the request-scoped isolation identity. A run belongs to one session,
    # profile and project. All are optional for backward compatibility; when
    # absent the runtime uses the default profile and derives a session id.
    sessionId: Optional[str] = None  # noqa: N815
    profileId: Optional[str] = None  # noqa: N815
    projectId: Optional[str] = None  # noqa: N815
    # Phase 3: an optional skill bundle to expand into the run's skill manifest.
    # The bundle is a reference only — a member that is missing/disabled is
    # reported and skipped, never enabled.
    bundleId: Optional[str] = None  # noqa: N815
    # ── Run lineage + resume (Phase 1) ─────────────────────────────────────
    # The run that spawned this one (e.g. a skill invocation, a workflow step).
    # None for a top-level run. Recorded so lineage survives a restart.
    parentRunId: Optional[str] = None  # noqa: N815
    # The workflow this run belongs to, when the composable workflow path is used.
    workflowId: Optional[str] = None  # noqa: N815
    # A checkpoint id to resume from. When set, the runtime re-enters the graph
    # at the recorded node instead of starting a fresh run; a missing checkpoint
    # fails with CHECKPOINT_NOT_FOUND and a terminal run with RESUME_CONFLICT.
    resumeFrom: Optional[str] = None  # noqa: N815
    # Phase 1 (additive, optional): bind this run to a read-only workspace. Absent
    # ⇒ the run has no code capability at all (the default-actor rule, Phase 0).
    workspace: Optional[RunWorkspace] = None
    # Phase 2 (additive, optional): the run's autonomy profile. Only a workspace-
    # bound run with a known profile may hold code verbs (Phase 0). "edit_verify"
    # is what grants code.write; absent/unknown grants nothing (fail-closed).
    autonomy: Optional[str] = None
    # Base URL of the TS front door, used ONLY as the read-only JDdS data bridge.
    callbackBaseUrl: str  # noqa: N815
    # Shared secret for the data bridge (matches CRON_SECRET on the TS side).
    callbackToken: Optional[str] = None  # noqa: N815


class RunResult(BaseModel):
    runId: str  # noqa: N815
    status: RunStatus
    output: Optional[str] = None
    error: Optional[HarnessError] = None
    # ── Run lineage (Phase 1, additive) ─────────────────────────────────────
    parentRunId: Optional[str] = None  # noqa: N815
    childRunIds: list[str] = Field(default_factory=list)  # noqa: N815
    modelSteps: int = 0  # noqa: N815
    toolCalls: int = 0  # noqa: N815
    toolErrors: int = 0  # noqa: N815
    promptTokens: int = 0  # noqa: N815
    completionTokens: int = 0  # noqa: N815
    totalTokens: int = 0  # noqa: N815
    # Phase 4 (additive, optional): evidence-grounded research metadata for a
    # gated run. Absent/None for ordinary chat and for older persisted rows, so
    # existing clients remain compatible.
    research: Optional[dict[str, Any]] = None  # noqa: N815
    # Phase 3-M Reliability (additive, optional): the deterministic outcome of
    # explicit user memory intent for this turn (saved/forgotten/corrected/
    # refused/needs_confirmation) and whether the run is eligible to become a
    # learning candidate. Absent for skill runs and older rows.
    memory: Optional[dict[str, Any]] = None  # noqa: N815
    # Context budgeting (additive, optional): how the resolved model's window
    # bounded this run's history. Absent for older persisted rows and for runs
    # that did not trim, so existing clients remain compatible.
    context: Optional[dict[str, Any]] = None


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
