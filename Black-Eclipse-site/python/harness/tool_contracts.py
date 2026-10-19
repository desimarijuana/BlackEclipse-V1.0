"""Tool capability contracts (round 4, W13) — a registered name is not proof.

Every advertised tool must carry a checkable contract: a stable identity, a
typed input schema, valid permission/risk metadata, a bounded timeout and a
declared effect where one applies. `check_tool_contract` verifies one tool;
`audit_registry` audits a live registry and reports HARD violations (the tool
is not honestly advertised) and WARNINGS (advisory gaps an operator should
close) — never a blended score.

The audit extends the existing advertised-but-dead guards (admission) to the
tool's own metadata (behaviour): a tool whose contract fails is named, not
silently dropped. Health is reported as `registered` — a static contract
cannot probe a live dependency; a per-tool health probe remains the
operator-facing check (`get_source_health`, MCP verify), and claiming more
here would be fabrication.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

#: The hard rules a tool must satisfy to be honestly advertised.
CONTRACT_VERSION = "1"
PERMISSIONS: frozenset[str] = frozenset({"read", "write", "external_action"})
RISKS: frozenset[str] = frozenset({"none", "low", "medium", "high"})
MIN_DESCRIPTION_CHARS = 10
#: A sanity ceiling on a declared per-call timeout. Heavy operation families
#: (terminal, package builds, container/compose pulls, runtime/workspace
#: lifecycle) deliberately declare 15 minutes; the ceiling catches an absurd
#: value without re-deciding a per-tool budget.
MAX_TIMEOUT_MS = 1_800_000  # 30 minutes
_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")


@dataclass
class ToolContract:
    """The checked contract of one tool."""

    name: str
    version: str
    permission: str
    risk: str
    timeout_ms: int
    effect: Optional[str]
    has_output_schema: bool
    health: str = "registered"
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "version": self.version,
            "permission": self.permission, "risk": self.risk,
            "timeoutMs": self.timeout_ms, "effect": self.effect,
            "outputTyped": self.has_output_schema, "health": self.health,
            "ok": self.ok, "violations": list(self.violations),
            "warnings": list(self.warnings),
        }


def check_tool_contract(tool: Any) -> ToolContract:
    """Verify one registered tool's metadata against the contract."""
    name = str(getattr(tool, "name", "") or "")
    contract = ToolContract(
        name=name,
        version=str(getattr(tool, "version", "") or ""),
        permission=str(getattr(tool, "permission", "") or ""),
        risk=str(getattr(tool, "risk", "") or ""),
        timeout_ms=int(getattr(tool, "timeout_ms", 0) or 0),
        effect=getattr(tool, "effect", None),
        has_output_schema=bool(getattr(tool, "output_schema", None)),
    )

    if not _NAME_RE.match(name):
        contract.violations.append(
            "name must be stable snake_case (a-z0-9_), <= 64 chars"
        )
    description = str(getattr(tool, "description", "") or "").strip()
    if len(description) < MIN_DESCRIPTION_CHARS:
        contract.violations.append("description is missing or too short to identify the tool")

    schema = getattr(tool, "input_schema", None)
    if not isinstance(schema, dict) or schema.get("type") != "object":
        contract.violations.append("input schema must be a typed JSON object schema")
    elif not isinstance(schema.get("properties"), dict):
        contract.violations.append("input schema must declare its properties (typed input)")

    if contract.permission not in PERMISSIONS:
        contract.violations.append(
            f"permission {contract.permission!r} is not one of {sorted(PERMISSIONS)}"
        )
    if contract.risk not in RISKS:
        contract.violations.append(
            f"risk {contract.risk!r} is not one of {sorted(RISKS)}"
        )
    if not (0 < contract.timeout_ms <= MAX_TIMEOUT_MS):
        contract.violations.append(
            f"timeout_ms must be within 1..{MAX_TIMEOUT_MS} (got {contract.timeout_ms})"
        )

    # Advisory gaps — named, never silently tolerated.
    if contract.permission != "read" and not contract.effect:
        contract.warnings.append(
            "a non-read tool declares no effect metadata; admission relies on the policy groups"
        )
    if not contract.has_output_schema:
        contract.warnings.append("no output schema declared (output shape is untyped)")
    if getattr(tool, "deprecated", False) and not getattr(tool, "replacement", None):
        contract.warnings.append("deprecated without a named replacement")
    return contract


def audit_registry(registry: Any, *, limit: int = 50) -> dict[str, Any]:
    """Audit every registered tool. Hard failures are named, never dropped."""
    try:
        tools = list(registry.list())
    except Exception:  # noqa: BLE001 - an unauditable registry is reported, not guessed
        return {"total": 0, "ok": 0, "violations": [], "error": "registry could not be enumerated"}
    violations: list[dict[str, Any]] = []
    warning_count = 0
    by_permission: dict[str, int] = {}
    for tool in tools:
        contract = check_tool_contract(tool)
        by_permission[contract.permission] = by_permission.get(contract.permission, 0) + 1
        warning_count += len(contract.warnings)
        if not contract.ok and len(violations) < limit:
            violations.append({"name": contract.name, "violations": contract.violations})
    return {
        "contractVersion": CONTRACT_VERSION,
        "total": len(tools),
        "ok": len(tools) - len([v for v in violations]),
        "violations": violations,
        "violationCount": len([t for t in tools if not check_tool_contract(t).ok]),
        "warningCount": warning_count,
        "byPermission": dict(sorted(by_permission.items())),
        "health": "registered",
    }


__all__ = [
    "CONTRACT_VERSION",
    "MAX_TIMEOUT_MS",
    "PERMISSIONS",
    "RISKS",
    "ToolContract",
    "audit_registry",
    "check_tool_contract",
]
