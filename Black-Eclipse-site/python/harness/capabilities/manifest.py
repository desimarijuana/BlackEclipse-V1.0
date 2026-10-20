"""The validated contract for a generated capability."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic.alias_generators import to_camel

from ..code.execution import IMPORT_ALLOWLIST

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

KINDS: tuple[str, ...] = (
    "recipe", "report_template", "tool", "skill", "ui_widget", "ui_page",
    "plugin", "harness_change",
)
SCOPES: tuple[str, ...] = ("workspace", "global")
EFFECTS: tuple[str, ...] = ("read", "write", "external_action")
PORT_KINDS: tuple[str, ...] = ("series", "table", "scalar", "text")
PURE_KINDS: frozenset[str] = frozenset({"recipe", "report_template"})
PURE_PERMISSIONS: frozenset[str] = frozenset({"analysis.execute", "analysis.read"})
CORE_WRITE_DENY: tuple[str, ...] = (
    "python/harness/code/policy.py",
    "python/harness/skills/permissions.py",
    "python/harness/mcp/approvals.py",
    "scripts/check-all.js",
)

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class CapabilityPort(BaseModel):
    model_config = _CAMEL

    name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,40}$")
    kind: Literal["series", "table", "scalar", "text"] = "series"
    required: bool = True
    description: str = Field(default="", max_length=300)


class CapabilityManifest(BaseModel):
    model_config = _CAMEL

    id: str
    version: str = "1.0.0"
    kind: Literal[
        "recipe", "report_template", "tool", "skill", "ui_widget", "ui_page",
        "plugin", "harness_change",
    ]
    title: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1, max_length=600)
    scope: Literal["workspace", "global"] = "workspace"
    inputs: list[CapabilityPort] = Field(default_factory=list, max_length=24)
    outputs: list[CapabilityPort] = Field(default_factory=list, max_length=24)
    permissions: list[str] = Field(default_factory=list, max_length=16)
    effect: Literal["read", "write", "external_action"] = "read"
    timeout_ms: int = Field(default=30_000, ge=100, le=600_000)
    imports: list[str] = Field(default_factory=list, max_length=32)
    tests: list[str] = Field(default_factory=lambda: ["test_capability.py"], max_length=8)
    acceptance: str = Field(default="", max_length=1_000)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_RE.match(value or ""):
            raise ValueError("id must be a lower_snake_case slug of 2..64 characters")
        return value

    @field_validator("version")
    @classmethod
    def _valid_version(cls, value: str) -> str:
        if not _VERSION_RE.match(value or ""):
            raise ValueError("version must be MAJOR.MINOR.PATCH")
        return value

    @field_validator("imports")
    @classmethod
    def _permitted_imports(cls, value: list[str]) -> list[str]:
        allowed = set(IMPORT_ALLOWLIST)
        bad = [name for name in value if name not in allowed]
        if bad:
            raise ValueError(f"imports outside the analysis allowlist: {', '.join(bad)}")
        return value

    @field_validator("permissions")
    @classmethod
    def _no_unknown_permissions(cls, value: list[str]) -> list[str]:
        bad = [name for name in value if name not in PURE_PERMISSIONS]
        if bad:
            raise ValueError(f"unsupported capability permissions: {', '.join(bad)}")
        return value

    @model_validator(mode="after")
    def _kind_rules(self) -> "CapabilityManifest":
        if self.kind in PURE_KINDS:
            if self.effect != "read":
                raise ValueError("a recipe or report template must be a read-only capability")
            if not self.inputs:
                raise ValueError("a reusable analysis recipe declares at least one input")
        if not self.tests:
            raise ValueError("a capability must declare its contract test")
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)

    def to_json(self, *, indent: int = 2) -> str:
        import json

        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def digest(self) -> str:
        import hashlib
        import json

        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, raw: Any) -> "CapabilityManifest":
        if not isinstance(raw, dict):
            raise ValueError("manifest must be a JSON object")
        return cls.model_validate(raw)

    @classmethod
    def load(cls, path: Path) -> "CapabilityManifest":
        import json

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(f"manifest is not readable: {exc}") from exc
        except ValueError as exc:
            raise ValueError(f"manifest is not valid JSON: {exc}") from exc
        return cls.from_dict(raw)

    def source_policy_violations(self) -> list[str]:
        violations: list[str] = []
        for denied in CORE_WRITE_DENY:
            if denied in self.title or denied in self.description or denied in self.acceptance:
                violations.append(f"references protected path: {denied}")
        return violations


def parse_manifest(raw: Any) -> tuple[Optional[CapabilityManifest], list[str]]:
    try:
        return CapabilityManifest.from_dict(raw), []
    except (ValidationError, ValueError) as exc:
        return None, [str(exc)]


__all__ = [
    "CapabilityManifest",
    "CapabilityPort",
    "CORE_WRITE_DENY",
    "EFFECTS",
    "KINDS",
    "PORT_KINDS",
    "PURE_KINDS",
    "SCOPES",
    "parse_manifest",
]
