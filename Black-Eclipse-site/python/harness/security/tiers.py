"""Autonomy tiers (round 4, W15) — the brief's three tiers mapped onto the
existing policy, so the RUNTIME (not the prompt) decides how much freedom an
action gets.

  * **Tier 1 — autonomous**: read, search, analyze, draft, permitted tests in
    the authorized workspace. No approval per call; the run's resolved
    allowlist and autonomy profile are the boundary.
  * **Tier 2 — guarded**: workspace writes, execution, dependency install and
    config changes. Policy + resource caps + the autonomy envelope apply.
  * **Tier 3 — approval**: external publication, destructive actions,
    credential changes, live financial transactions. A single-use, operator
    approval is required by the effect authorizer.

This module does NOT add a second policy: every classification is derived from
the existing `code/policy.py` groups (the ones the authorizer enforces) plus a
tool's own declared `permission`/`effect` metadata, and `tier_report` audits a
live registry against the mapping. An action class the mapping cannot place
falls to the SAFER tier for its declared effect — never to Tier 1 by accident.
"""

from __future__ import annotations

from typing import Any, Optional

TIER_AUTONOMOUS = 1
TIER_GUARDED = 2
TIER_APPROVAL = 3

TIER_NAMES: dict[int, str] = {
    TIER_AUTONOMOUS: "autonomous",
    TIER_GUARDED: "guarded",
    TIER_APPROVAL: "approval",
}

#: Effects that always require an operator approval, whatever the group.
_APPROVAL_EFFECTS = frozenset({"external", "destructive"})
#: Effects that are at least guarded.
_GUARDED_EFFECTS = frozenset({"write", "execute"})


def _approval_groups() -> frozenset[str]:
    """Tool names the existing policy treats as external/approval-gated."""
    from ..code import policy  # noqa: PLC0415 - the ONE policy owner

    return frozenset(
        set(policy.EXTERNAL_ACTION_TOOLS)
        | set(policy.VISION_EXTERNAL_TOOLS)
        | set(policy.BROWSER_EFFECTFUL_TOOLS)
        | set(policy.COMPUTER_EFFECTFUL_TOOLS)
        | set(policy.AUTOMATION_EFFECT_TOOLS)
        | set(policy.SCHEDULING_EFFECT_TOOLS)
        | set(policy.GIT_EXTERNAL_TOOLS)
    )


def _guarded_groups() -> frozenset[str]:
    """Tool names that write/execute/install inside the workspace."""
    from ..code import policy  # noqa: PLC0415

    return frozenset(
        set(policy.WRITE_TOOLS)
        | set(policy.EXECUTION_WRITE_TOOLS)
        | set(policy.APP_RUNTIME_WRITE_TOOLS)
        | set(policy.FS_WRITE_TOOLS)
        | set(policy.INTEL_WRITE_TOOLS)
        | set(policy.ACQUISITION_WRITE_TOOLS)
    )


def classify_tool(
    name: str, *, permission: Optional[str] = None, effect: Optional[str] = None,
) -> int:
    """The autonomy tier for one tool/action. Deterministic; fails safe.

    Order: an explicit approval effect > the policy's approval groups > an
    explicit guarded effect > the policy's write/execute groups > a declared
    `write` permission > Tier 1 (read-only).
    """
    if effect in _APPROVAL_EFFECTS:
        return TIER_APPROVAL
    if name in _approval_groups():
        return TIER_APPROVAL
    if effect in _GUARDED_EFFECTS:
        return TIER_GUARDED
    if name in _guarded_groups():
        return TIER_GUARDED
    if str(permission or "") == "write":
        return TIER_GUARDED
    return TIER_AUTONOMOUS


def tier_requires_approval(tier: int) -> bool:
    """Whether the runtime must demand a single-use operator approval."""
    return int(tier) >= TIER_APPROVAL


def tier_report(registry: Any, *, limit: int = 25) -> dict[str, Any]:
    """Audit a live registry against the tier mapping.

    Returns per-tier counts plus the approval-tier names (bounded), so an
    operator can see exactly which registered tools the runtime will gate.
    """
    counts = {TIER_AUTONOMOUS: 0, TIER_GUARDED: 0, TIER_APPROVAL: 0}
    approval_tier: list[str] = []
    guarded_tier: list[str] = []
    try:
        names = list(registry.names())
    except Exception:  # noqa: BLE001 - an unauditable registry is reported, not guessed
        return {"counts": counts, "error": "registry could not be enumerated"}
    for name in names:
        permission = effect = None
        try:
            tool = registry.get(name)
            permission = getattr(tool, "permission", None)
            effect = getattr(tool, "effect", None)
        except Exception:  # noqa: BLE001
            pass
        tier = classify_tool(name, permission=permission, effect=effect)
        counts[tier] = counts.get(tier, 0) + 1
        if tier == TIER_APPROVAL and len(approval_tier) < limit:
            approval_tier.append(name)
        if tier == TIER_GUARDED and len(guarded_tier) < limit:
            guarded_tier.append(name)
    return {
        "counts": {TIER_NAMES[tier]: counts.get(tier, 0) for tier in sorted(TIER_NAMES)},
        "approvalTierTools": sorted(approval_tier),
        "guardedTierTools": sorted(guarded_tier),
        "total": len(names),
    }


__all__ = [
    "TIER_APPROVAL",
    "TIER_AUTONOMOUS",
    "TIER_GUARDED",
    "TIER_NAMES",
    "classify_tool",
    "tier_report",
    "tier_requires_approval",
]
