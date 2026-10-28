"""Read-only tool-contract shadow.

Inventories registered tools that are NOT on an agent's surface and classifies
whether they could be widened later. It grants nothing, writes nothing, and
never changes an allowlist. The output is an operator-facing shadow report.

Eligibility is deliberately narrow: read permission, read/None effect,
none/low risk, a valid contract, and no financial/mechanism name.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..tool_contracts import check_tool_contract
from .widening import FINANCIAL_ACTION_MARKERS, MECHANISM_TOOL_MARKERS


def _name_reason(name: str) -> str:
    lowered = name.casefold()
    if any(marker in lowered for marker in FINANCIAL_ACTION_MARKERS):
        return "financial_action"
    if any(lowered == marker or lowered.startswith(marker) for marker in MECHANISM_TOOL_MARKERS):
        return "mechanism"
    return ""


def shadow_report(
    registry: Any,
    granted_tools: Iterable[str],
    *,
    blocked_tools: Iterable[str] = (),
) -> dict[str, Any]:
    """Classify every registered tool not already granted. No write path."""
    granted = {str(name) for name in granted_tools}
    blocked = {str(name) for name in blocked_tools}
    rows: list[dict[str, Any]] = []
    counts = {"total": 0, "eligible": 0, "ineligible": 0}
    try:
        tools = list(registry.list())
    except Exception as exc:  # noqa: BLE001 - an unauditable registry is reported
        return {"ok": False, "error": str(exc), "rows": [], **counts}
    for tool in tools:
        name = str(getattr(tool, "name", "") or "")
        if not name or name in granted:
            continue
        counts["total"] += 1
        reasons: list[str] = []
        contract = check_tool_contract(tool)
        if not contract.ok:
            reasons.extend(contract.violations)
        if contract.permission != "read":
            reasons.append("not_read_permission")
        if str(contract.effect or "") not in ("", "read"):
            reasons.append("effectful")
        if contract.risk not in ("none", "low"):
            reasons.append("high_risk")
        if name in blocked:
            reasons.append("blocked_tool")
        name_reason = _name_reason(name)
        if name_reason:
            reasons.append(name_reason)
        eligible = not reasons
        counts["eligible" if eligible else "ineligible"] += 1
        rows.append({
            "name": name,
            "permission": contract.permission,
            "effect": contract.effect,
            "risk": contract.risk,
            "timeoutMs": contract.timeout_ms,
            "status": "eligible_shadow" if eligible else "ineligible",
            "reasons": reasons,
            "warnings": list(contract.warnings),
        })
    rows.sort(key=lambda row: (row["status"] != "eligible_shadow", row["name"]))
    return {
        "ok": True,
        "counts": counts,
        "rows": rows,
        "note": (
            "shadow only: no tool is granted or activated; this report is "
            "evidence for a later operator decision"
        ),
    }


__all__ = ["shadow_report"]
