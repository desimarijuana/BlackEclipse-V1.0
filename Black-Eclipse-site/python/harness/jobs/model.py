"""A job is a durable, reviewable intent to run something later.

It is DATA. A job never holds executable code, never holds a prompt body that
grants anything, and never widens authority: it references a skill (by id +
version) or an objective + agent id, and the run it produces is subject to exactly
the same permission, allowlist and policy checks as a user-initiated run.

The shape mirrors the wire contract in the phase file §6.1 and is persisted as a
JSON blob on a `HarnessJob` row (the queryable columns live beside it).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

# Accept BOTH snake_case (persistence / Python callers) and camelCase (the TS
# front door), exactly like `schemas.ModelSettings` and `mcp.config`.
_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

JobKind = Literal["cron", "interval", "file_watch", "webhook", "manual"]
OnMissed = Literal["skip", "run_once"]           # both recorded; never silent
JobTargetKind = Literal["skill", "objective"]

# The autonomy a code job may declare. Absent ⇒ a research/analysis job.
JobAutonomy = Literal["plan_only", "edit_verify", "approve_external"]

JobDeliveryAdapter = Literal["in_app", "artifact"]   # Phase 11 adds "messaging"
KNOWN_ADAPTERS: tuple[str, ...] = ("in_app", "artifact")

# Breaker states — reused from `mcp/circuit.py` (same names, same meaning).
CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"

# Run-row terminal statuses recorded on `HarnessJobRun.status`.
RUN_STATUSES: tuple[str, ...] = (
    "running", "ok", "failed", "skipped", "timed_out", "refused",
)

MIN_INTERVAL_S = 60
MAX_INTERVAL_S = 30 * 24 * 3600


class JobTarget(BaseModel):
    """What a job runs. A skill reference or a free-text objective + agent."""

    model_config = _CAMEL

    kind: JobTargetKind
    skill_id: Optional[str] = None
    skill_version: Optional[str] = None          # pinned; a job is reproducible
    objective: Optional[str] = Field(None, max_length=4000)
    agent_id: str = "eclipse-agent"
    # Code jobs only. Absent ⇒ a research/analysis job.
    workspace_root: Optional[str] = None
    autonomy: Optional[JobAutonomy] = None

    def is_code_job(self) -> bool:
        return self.workspace_root is not None or self.autonomy is not None


class JobDelivery(BaseModel):
    model_config = _CAMEL

    adapter: JobDeliveryAdapter = "in_app"
    title: Optional[str] = Field(None, max_length=200)


class JobDefinition(BaseModel):
    """One durable job definition. Persisted as JSON + queryable columns."""

    model_config = _CAMEL

    id: str                                       # uuid4 hex, server-assigned
    name: str = Field(..., max_length=120)
    kind: JobKind
    cron: Optional[str] = None                    # 5-field, validated by jobs/cron
    interval_seconds: Optional[int] = Field(None, ge=MIN_INTERVAL_S, le=MAX_INTERVAL_S)
    watch_path: Optional[str] = None              # file_watch; must be inside a workspace
    webhook_token_hash: Optional[str] = None      # webhook; SHA-256, never the token
    timezone: str = "local"                       # "local" or an IANA name
    on_missed: OnMissed = "skip"
    target: JobTarget
    delivery: JobDelivery = Field(default_factory=JobDelivery)
    enabled: bool = False                         # discovery is not activation
    max_runtime_s: int = Field(900, ge=30, le=7200)
    created_at: str
    updated_at: str
    last_run_at: Optional[str] = None
    consecutive_failures: int = 0
    breaker: Literal["closed", "open", "half_open"] = "closed"
    breaker_opened_at: Optional[str] = None
    breaker_reset_by: Optional[str] = None        # operator id, or None

    @model_validator(mode="after")
    def _kind_consistency(self) -> "JobDefinition":
        if self.kind == "cron" and not self.cron:
            raise ValueError("a cron job requires a cron expression")
        if self.kind == "interval" and self.interval_seconds is None:
            raise ValueError("an interval job requires interval_seconds")
        if self.kind == "file_watch" and not self.watch_path:
            raise ValueError("a file-watch job requires watch_path")
        return self

    def public(self) -> dict:
        """The secret-free view for the API/UI (never the token hash).

        camelCase (by alias) so the TS front door reads natural JSON.
        """
        data = self.model_dump(by_alias=True)
        data.pop("webhookTokenHash", None)
        data["webhook"] = self.webhook_token_hash is not None
        return data


__all__ = [
    "CLOSED",
    "HALF_OPEN",
    "JobAutonomy",
    "JobDefinition",
    "JobDelivery",
    "JobDeliveryAdapter",
    "JobKind",
    "JobTarget",
    "JobTargetKind",
    "KNOWN_ADAPTERS",
    "MAX_INTERVAL_S",
    "MIN_INTERVAL_S",
    "OPEN",
    "OnMissed",
    "RUN_STATUSES",
]
