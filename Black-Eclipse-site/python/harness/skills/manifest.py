"""Skill manifest — the machine-readable contract for a skill.

A skill is a versioned procedure the existing agent runtime executes. The
manifest is the authoritative declaration of *what a skill is allowed to do*:
its inputs/outputs (validated in code), the tools it may call, the permissions
it requires, its dependencies, its risk level, and its lifecycle status.

Design rules (mirrored in docs/harness/phase-3-architecture.md):

  * Validation is pydantic — already a dependency via LangChain. There is no
    second schema library, and no hand-rolled validator.
  * Versioning is semver (a tiny comparator here; no dependency).
  * `instructions` names a file inside the skill folder (default `SKILL.md`).
    The full instructions are NEVER in the manifest — that is what makes
    progressive disclosure possible (metadata first, instructions on select).
  * A manifest can be valid yet NOT executable: lifecycle `status` gates
    execution separately from well-formedness.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# ── Vocabulary ──────────────────────────────────────────────────────────────

SkillStatus = Literal[
    "draft",       # authored, not yet tested
    "evaluating",  # a candidate patch is under evaluation
    "testing",     # under test / evaluation
    "canary",      # evaluated; routed a fraction of eligible runs (non-mutating only)
    "review",      # evaluation done, awaiting human approval
    "validated",   # passed mandated checks, not yet enabled
    "approved",    # alias of validated: passed checks, awaiting activation
    "enabled",     # approved and active
    "active",      # alias of enabled: the currently authoritative version
    "disabled",    # installed but inert (operator choice)
    "deprecated",  # superseded; retained for history, not selectable
    "archived",    # retired by maintenance (unused/stale); inert but restorable
    "superseded",  # replaced by a newer active version; retained for history
    "rolled_back", # automatically or manually reverted; retained for history
    "rejected",    # reviewed and refused
]

SkillRisk = Literal["low", "medium", "high", "critical"]

SkillCategory = Literal["research", "quality", "finance", "system"]

EvaluationStatus = Literal[
    "not_evaluated",
    "passed",
    "failed",
    "needs_review",
    "blocked",
]

ExecutionMode = Literal["interactive", "workflow", "scheduled", "agent", "evaluation"]

# Statuses that may be executed. `validated` is executable only in
# non-interactive modes (a validated-but-not-enabled skill is a candidate for
# evaluation/scheduled use, never for a live user turn). `canary` is executable
# ONLY when the canary router selects it for a run (see skills/patches.py).
EXECUTABLE_STATUSES: frozenset[str] = frozenset({"enabled", "active", "validated", "testing", "canary"})
# Statuses that are never executable in any mode.
NON_EXECUTABLE_STATUSES: frozenset[str] = frozenset(
    {"draft", "evaluating", "review", "approved", "disabled", "deprecated",
     "archived", "superseded", "rolled_back", "rejected"}
)

# The permission vocabulary. Phase 3 grants only the safe subset (see
# permissions.py); declaring one here does not grant it.
Permission = Literal[
    "data.read",
    "research.read",
    "analysis.execute",
    "report.generate",
    "skill.invoke",
    "skill.create",
    "skill.review",
    "skill.enable",
    "skill.disable",
    "portfolio.read",
    "portfolio.modify",
    "external.network",
    "code.execute",
    "code.write",
    "production.modify",
    "trade.execute",
    "broker.modify",
]

# Permissions that are hard-blocked in Phase 3. A skill declaring one is
# well-formed but can never be enabled.
FORBIDDEN_PERMISSIONS: frozenset[str] = frozenset(
    {"trade.execute", "broker.modify", "production.modify", "code.write"}
)

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


# ── Semver (tiny, dependency-free) ──────────────────────────────────────────


def parse_version(version: str) -> tuple[int, int, int, str]:
    """Parse `MAJOR.MINOR.PATCH[-prerelease]`. Raises ValueError when invalid."""
    match = _SEMVER_RE.match(version.strip())
    if not match:
        raise ValueError(f"invalid semver: {version!r}")
    major, minor, patch, pre = match.groups()
    return int(major), int(minor), int(patch), pre or ""


def version_satisfies(version: str, constraint: Optional[str]) -> bool:
    """Check a concrete version against a dependency constraint.

    Supported constraints: exact (`1.2.3`), caret (`^1.2.3`), tilde (`~1.2.3`),
    greater-or-equal (`>=1.2.3`), and `*`/None/empty (any). Anything else is
    treated as an exact string match — never silently satisfied.
    """
    if constraint is None:
        return True
    constraint = constraint.strip()
    if constraint in ("", "*"):
        return True
    try:
        target = parse_version(version)
    except ValueError:
        return False
    if constraint.startswith("^"):
        base = parse_version(constraint[1:])
        # Same major, >= base (for major > 0); for 0.x, same minor.
        if base[0] > 0:
            return target[0] == base[0] and target >= base
        return target[0] == 0 and target[1] == base[1] and target >= base
    if constraint.startswith("~"):
        base = parse_version(constraint[1:])
        return target[0] == base[0] and target[1] == base[1] and target >= base
    if constraint.startswith(">="):
        return target >= parse_version(constraint[2:])
    return version == constraint


# ── Sub-models ──────────────────────────────────────────────────────────────


class SkillDependencySpec(BaseModel):
    """A skill this skill depends on, with an optional version constraint."""

    skillId: str = Field(min_length=1, max_length=128)  # noqa: N815
    version: Optional[str] = None  # constraint; None = any
    optional: bool = False

    @field_validator("skillId")
    @classmethod
    def _id_shape(cls, value: str) -> str:
        # Skill ids are stable slugs, optionally namespaced: `research.planning`
        # or `fundamental-analysis`. Dots separate namespaces; no spaces.
        if not re.match(r"^[a-z0-9][a-z0-9._-]*$", value):
            raise ValueError(
                "skillId must be a lowercase slug (letters, digits, '.', '-', '_')"
            )
        return value


class ExecutionLimits(BaseModel):
    """Bounded execution. Mirrors AgentConfig limits so a skill cannot exceed
    the runtime's own safety envelope."""

    maxSteps: int = Field(default=8, ge=1, le=32)  # noqa: N815
    timeoutMs: int = Field(default=120_000, ge=1_000, le=600_000)  # noqa: N815
    maxToolCalls: int = Field(default=24, ge=0, le=200)  # noqa: N815


class DeprecationInfo(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    supersededBy: Optional[str] = None  # noqa: N815  skillId of the replacement
    deprecatedAt: Optional[str] = None  # noqa: N815


# ── Manifest ────────────────────────────────────────────────────────────────


class SkillManifest(BaseModel):
    """One immutable, versioned skill declaration.

    Everything here is machine-checkable. Prose belongs in `SKILL.md`; this is
    what code reads to decide whether a skill may be discovered, selected,
    validated, promoted or executed.
    """

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    version: str
    description: str = Field(min_length=1, max_length=2000)
    category: SkillCategory
    tags: list[str] = Field(default_factory=list)
    status: SkillStatus = "draft"

    # Where the human-readable procedure lives, relative to the skill folder.
    # None = manifest-only (a purely declarative skill with no prose procedure).
    instructions: Optional[str] = "SKILL.md"

    # JSON Schema for validated input/output. `inputSchema` must be an object
    # schema; output may be absent for skills that only produce prose.
    inputSchema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})  # noqa: N815
    outputSchema: Optional[dict[str, Any]] = None  # noqa: N815

    requiredTools: list[str] = Field(default_factory=list)  # noqa: N815
    requiredSkills: list[SkillDependencySpec] = Field(default_factory=list)  # noqa: N815
    permissions: list[Permission] = Field(default_factory=list)
    riskLevel: SkillRisk = "low"  # noqa: N815

    limits: ExecutionLimits = Field(default_factory=ExecutionLimits)

    # Origin: who/what authored it. A generated draft carries `origin: learning`
    # and `sourceRunId` so it is always traceable back to the experience.
    author: str = "eclipse"
    origin: Literal["builtin", "author", "learning"] = "builtin"
    sourceRunId: Optional[str] = None  # noqa: N815

    createdAt: Optional[str] = None  # noqa: N815
    updatedAt: Optional[str] = None  # noqa: N815

    evaluationStatus: EvaluationStatus = "not_evaluated"  # noqa: N815
    compatibleRuntime: str = ">=0.1.0"  # noqa: N815

    deprecation: Optional[DeprecationInfo] = None

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not re.match(r"^[a-z0-9][a-z0-9._-]*$", value):
            raise ValueError(
                "id must be a lowercase slug (letters, digits, '.', '-', '_')"
            )
        return value

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        parse_version(value)  # raises on invalid
        return value.strip()

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for tag in value:
            normalized = tag.strip().lower()
            if normalized and normalized not in seen:
                seen.append(normalized)
        return seen

    @field_validator("requiredSkills", mode="before")
    @classmethod
    def _coerce_dependencies(cls, value: Any) -> Any:
        # A dependency may be written as a bare id string (the common case) or
        # as a full object with a version constraint.
        if isinstance(value, list):
            return [
                {"skillId": item} if isinstance(item, str) else item
                for item in value
            ]
        return value

    @field_validator("requiredTools")
    @classmethod
    def _dedupe_tools(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for tool in value:
            name = tool.strip()
            if not name:
                raise ValueError("required tool names must not be blank")
            if not re.match(r"^[A-Za-z0-9_]+$", name):
                raise ValueError(f"invalid tool name: {name!r}")
            if name not in seen:
                seen.append(name)
        return seen

    @field_validator("inputSchema")
    @classmethod
    def _input_is_object(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("inputSchema must be an object schema")
        schema_type = value.get("type", "object")
        if schema_type != "object":
            raise ValueError("inputSchema.type must be 'object'")
        return value

    @model_validator(mode="after")
    def _deprecation_consistency(self) -> "SkillManifest":
        if self.status == "deprecated" and self.deprecation is None:
            raise ValueError("a deprecated skill must carry deprecation info")
        if self.origin == "learning" and not self.sourceRunId:
            raise ValueError("a learning-origin skill must reference its sourceRunId")
        return self

    # ── Derived helpers ─────────────────────────────────────────────────────

    @property
    def forbidden_permissions(self) -> list[str]:
        """Declared permissions that are hard-blocked in Phase 3."""
        return [p for p in self.permissions if p in FORBIDDEN_PERMISSIONS]

    @property
    def is_executable(self) -> bool:
        return self.status in EXECUTABLE_STATUSES

    @property
    def is_active(self) -> bool:
        return self.status in ("enabled", "active")

    def discovery_metadata(self) -> dict[str, Any]:
        """The compact, cacheable metadata used for discovery — never the
        instructions. This is what progressive loading returns at step 1."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "status": self.status,
            "riskLevel": self.riskLevel,
            "permissions": self.permissions,
            "requiredTools": self.requiredTools,
            "evaluationStatus": self.evaluationStatus,
        }

    def content_hash(self) -> str:
        """A stable hash of the manifest's meaning, for version pinning.

        Execution records the manifest hash so an enabled skill's behavior can
        never change silently — any content change yields a new hash.
        """
        import hashlib
        import json

        payload = self.model_dump(exclude={"createdAt", "updatedAt"})
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def version_identity(self, instructions: Optional[str] = None) -> str:
        """A stable identity for the COMPLETE behavior-affecting version.

        `content_hash()` covers only the machine-readable manifest. A skill's
        behavior is also shaped by its `SKILL.md` instructions (and, for a caller
        that supplies them, resolved dependency versions). This folds the
        instruction content into the identity so editing a `SKILL.md` without
        touching `skill.json` still yields a new identity — an enabled skill's
        behavior can never change under the same recorded identity.
        """
        import hashlib
        import json

        base = json.dumps(
            self.model_dump(exclude={"createdAt", "updatedAt"}),
            sort_keys=True, default=str,
        )
        instruction_digest = hashlib.sha256((instructions or "").encode("utf-8")).hexdigest()
        canonical = f"{base}\x1f{instruction_digest}"
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "DeprecationInfo",
    "EvaluationStatus",
    "ExecutionLimits",
    "ExecutionMode",
    "EXECUTABLE_STATUSES",
    "FORBIDDEN_PERMISSIONS",
    "NON_EXECUTABLE_STATUSES",
    "Permission",
    "SkillCategory",
    "SkillDependencySpec",
    "SkillManifest",
    "SkillRisk",
    "SkillStatus",
    "parse_version",
    "version_satisfies",
]
