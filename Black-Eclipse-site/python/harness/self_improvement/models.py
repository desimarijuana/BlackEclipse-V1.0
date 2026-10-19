"""Data contracts for RSL.

`HarnessSnapshot` is the only candidate surface RSL may vary: a system prompt, a
tool subset, step/call ceilings, an optional model identity and inert skill-draft
ids. It is deliberately data-only — it cannot carry permissions, risk classes,
approval state or identity fields.

`Observation` is the durable, bounded record of *why* a candidate exists. It is
evidence, never an instruction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

MAX_PROMPT_CHARS = 16_000
MAX_STEPS = 32
MAX_TOOL_CALLS = 200
MAX_TEMPERATURE = 2.0

OBSERVATION_KINDS: tuple[str, ...] = (
    "mistake_recurrence",
    "mined_failure",
    "operator",
)


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


@dataclass(frozen=True)
class HarnessSnapshot:
    """A validated, reproducible candidate harness configuration."""

    systemPrompt: str
    toolNames: tuple[str, ...] = ()
    maxSteps: int = 8
    maxToolCalls: int = MAX_TOOL_CALLS
    modelProvider: Optional[str] = None
    modelName: Optional[str] = None
    temperature: Optional[float] = None
    skillDraftIds: tuple[str, ...] = ()
    sourceDigest: str = ""

    def __post_init__(self) -> None:
        prompt = str(self.systemPrompt or "")
        if not prompt.strip():
            raise ValueError("systemPrompt is required")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise ValueError(f"systemPrompt exceeds {MAX_PROMPT_CHARS} characters")
        if not 1 <= int(self.maxSteps) <= MAX_STEPS:
            raise ValueError(f"maxSteps must be between 1 and {MAX_STEPS}")
        if not 0 <= int(self.maxToolCalls) <= MAX_TOOL_CALLS:
            raise ValueError(f"maxToolCalls must be between 0 and {MAX_TOOL_CALLS}")
        if self.temperature is not None:
            temperature = float(self.temperature)
            if not 0.0 <= temperature <= MAX_TEMPERATURE:
                raise ValueError(f"temperature must be between 0 and {MAX_TEMPERATURE}")

        tools = tuple(str(name).strip() for name in (self.toolNames or ()) if str(name).strip())
        if len(set(tools)) != len(tools):
            raise ValueError("toolNames must be unique")
        skill_ids = tuple(
            str(skill_id).strip()
            for skill_id in (self.skillDraftIds or ())
            if str(skill_id).strip()
        )
        if len(set(skill_ids)) != len(skill_ids):
            raise ValueError("skillDraftIds must be unique")

        object.__setattr__(self, "toolNames", tools)
        object.__setattr__(self, "skillDraftIds", skill_ids)
        digest = self.compute_digest()
        if self.sourceDigest and self.sourceDigest != digest:
            raise ValueError("sourceDigest does not match the snapshot contents")
        object.__setattr__(self, "sourceDigest", digest)

    def _identity(self) -> dict[str, Any]:
        return {
            "systemPrompt": self.systemPrompt,
            "toolNames": list(self.toolNames),
            "maxSteps": int(self.maxSteps),
            "maxToolCalls": int(self.maxToolCalls),
            "modelProvider": self.modelProvider,
            "modelName": self.modelName,
            "temperature": self.temperature,
            "skillDraftIds": list(self.skillDraftIds),
        }

    def compute_digest(self) -> str:
        """The sha256 of the canonical JSON identity (excluding the digest)."""
        return hashlib.sha256(_canonical(self._identity()).encode("utf-8")).hexdigest()

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload = self._identity()
        if include_digest:
            payload["sourceDigest"] = self.sourceDigest
        return payload

    def to_agent_config(self) -> Any:
        """Build the validated runtime agent config for a candidate trial."""
        from ..schemas import AgentConfig  # noqa: PLC0415 - keep the model module light

        return AgentConfig(
            id="rsl-candidate",
            name="RSL Candidate",
            systemPrompt=self.systemPrompt,
            tools=list(self.toolNames),
            maxSteps=int(self.maxSteps),
            maxToolCalls=int(self.maxToolCalls),
        )


@dataclass(frozen=True)
class Observation:
    """A bounded, reproducible reason a candidate exists."""

    kind: str
    signature: str
    runId: Optional[str] = None
    category: str = ""
    observedCount: int = 1
    targetHint: Optional[str] = None
    evidenceRunIds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in OBSERVATION_KINDS:
            raise ValueError(f"unknown observation kind {self.kind!r}")
        if not str(self.signature or "").strip():
            raise ValueError("signature is required")
        object.__setattr__(self, "observedCount", max(0, int(self.observedCount)))
        object.__setattr__(
            self,
            "evidenceRunIds",
            tuple(str(run_id) for run_id in (self.evidenceRunIds or ()) if str(run_id)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "signature": self.signature,
            "runId": self.runId,
            "category": self.category,
            "observedCount": int(self.observedCount),
            "targetHint": self.targetHint,
            "evidenceRunIds": list(self.evidenceRunIds),
        }


__all__ = [
    "HarnessSnapshot",
    "MAX_PROMPT_CHARS",
    "MAX_STEPS",
    "MAX_TOOL_CALLS",
    "OBSERVATION_KINDS",
    "Observation",
]
