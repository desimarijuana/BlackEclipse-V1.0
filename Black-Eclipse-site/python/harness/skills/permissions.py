"""Permission policy — the single authority for skill authorization.

Every skill permission decision in Phase 3 goes through this module. There are
NO scattered permission checks: a skill that needs `analysis.execute` is gated
here, and a tool is still independently gated by `ToolRegistry` (which only
allows read-only tools at all).

Model
-----
An **actor** has a set of granted permissions. A **skill** declares a set it
requires. Execution is allowed iff the actor's granted set is a superset of the
skill's required set, and no required permission is hard-blocked.

Default-deny: an actor grants only what it explicitly holds. The safe local
actor holds the read-only research/analysis set. Anything beyond that — creating,
reviewing, enabling skills, executing code, trading — must be granted by an
explicitly authorized actor (an operator with the runtime secret).

Markdown instructions are NOT a security boundary. A skill's `SKILL.md` can
describe any procedure; the permission check below runs in code on the composed
`AgentConfig` regardless of what the prose says. Retrieved web/document content
is untrusted data and can never widen an actor's grants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from ..code.policy import code_grants
from .manifest import CODE_PERMISSIONS, FORBIDDEN_PERMISSIONS, Permission

# The Phase-3 safe set: read-only financial research + analysis + reporting.
# No skill may be *enabled* with anything outside this set (except the
# explicitly-authorized operator permissions below).
SAFE_PERMISSIONS: frozenset[str] = frozenset(
    {
        "data.read",
        "research.read",
        "analysis.execute",
        "report.generate",
        "skill.invoke",
        "portfolio.read",
        "external.network",  # web research is a read-only, audited path
    }
)

# Permissions that require explicit operator authorization (never the default
# local actor). These gate the learning/review lifecycle, not execution.
OPERATOR_PERMISSIONS: frozenset[str] = frozenset(
    {"skill.create", "skill.review", "skill.enable", "skill.disable", "portfolio.modify"}
)

# Data-collection permissions (Phase 16, first slice): granted ONLY by an
# operator-set acquisition profile (`code/policy.acquisition_grants`), never by
# the safe or operator sets above. The noun is declared here so a skill manifest
# that names one stays well-formed while the grant stays impossible by default.
DATA_PERMISSIONS: frozenset[str] = frozenset({"data.collect"})

# Never granted in Phase 3, to any actor. Declaring one is allowed (the manifest
# stays well-formed) but it can never resolve to a grant. `code.execute` /
# `code.write` left this set in Phase 0: they are now grantable ONLY through the
# workspace-bound path (`code_grants`, below), never to the safe or operator set.
BLOCKED_PERMISSIONS: frozenset[str] = FORBIDDEN_PERMISSIONS


@dataclass(frozen=True)
class Actor:
    """Who is invoking. `operator=True` means an explicitly authorized caller
    (request carried the runtime secret / admin context)."""

    id: str = "local"
    operator: bool = False
    # Extra grants beyond the defaults; only an operator may widen the set.
    grants: frozenset[str] = field(default_factory=frozenset)
    # Per-request scopes a surface may narrow (e.g. a workflow pins read-only).
    scopes: frozenset[str] = field(default_factory=frozenset)
    # NEW — set only by the code run path (Phase 1+). Absent = no code capability.
    # The code verbs are unioned in ONLY when BOTH a workspace binding and a
    # known autonomy profile are present (fail-closed otherwise).
    workspace_id: Optional[str] = None
    autonomy: Optional[str] = None

    def granted(self) -> frozenset[str]:
        """The resolved permission set for this actor (never includes blocked)."""
        base = set(SAFE_PERMISSIONS)
        if self.operator:
            base |= OPERATOR_PERMISSIONS
            base |= set(self.grants)
        # Forbidden permissions (trade/broker/production) can never be granted.
        base -= BLOCKED_PERMISSIONS
        # The code verbs are NOT reachable through a caller-supplied grant: only
        # the workspace-bound path below may hold them. Without this an operator
        # could smuggle `code.write` in via `grants`, defeating the freeze.
        base -= set(CODE_PERMISSIONS)
        # A workspace-bound actor may hold the code verbs for its profile. An
        # unknown profile grants nothing: `code_grants` returns an empty set.
        if self.workspace_id and self.autonomy:
            base |= set(code_grants(self.autonomy))
        # A non-operator cannot widen; scopes only *narrow* when both are given.
        if self.scopes:
            narrowed = base & {p for p in self.scopes}
            return frozenset(narrowed)
        return frozenset(base)


DEFAULT_ACTOR = Actor(id="local", operator=False)
OPERATOR_ACTOR = Actor(id="operator", operator=True)


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    missing: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()
    reason: Optional[str] = None

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "missing": list(self.missing),
            "blocked": list(self.blocked),
            "reason": self.reason,
        }


def check_permissions(
    required: Iterable[str], actor: Actor = DEFAULT_ACTOR
) -> PermissionDecision:
    """Decide whether `actor` may satisfy `required` permissions.

    A required permission that is hard-blocked fails the decision even if the
    actor somehow holds it — defense in depth.
    """
    required_set = {p for p in required if p}
    blocked = tuple(sorted(required_set & BLOCKED_PERMISSIONS))
    if blocked:
        return PermissionDecision(
            allowed=False,
            blocked=blocked,
            reason=f"blocked in this phase: {', '.join(blocked)}",
        )
    granted = actor.granted()
    missing = tuple(sorted(required_set - granted))
    if missing:
        return PermissionDecision(
            allowed=False,
            missing=missing,
            reason=f"missing permission(s): {', '.join(missing)}",
        )
    return PermissionDecision(allowed=True)


def can_enable(manifest_permissions: Iterable[str], actor: Actor) -> PermissionDecision:
    """A skill may be enabled only if its permissions are within the safe set
    (or operator-grantable) and the actor may enable."""
    if "skill.enable" not in actor.granted():
        return PermissionDecision(
            allowed=False,
            missing=("skill.enable",),
            reason="skill.enable requires an authorized operator",
        )
    required = {p for p in manifest_permissions if p}
    blocked = tuple(sorted(required & BLOCKED_PERMISSIONS))
    if blocked:
        return PermissionDecision(
            allowed=False,
            blocked=blocked,
            reason=f"cannot enable a skill declaring blocked permissions: {', '.join(blocked)}",
        )
    outside = tuple(sorted(required - SAFE_PERMISSIONS - OPERATOR_PERMISSIONS))
    if outside:
        return PermissionDecision(
            allowed=False,
            blocked=outside,
            reason=f"permissions outside the approved set: {', '.join(outside)}",
        )
    return PermissionDecision(allowed=True)


__all__ = [
    "Actor",
    "BLOCKED_PERMISSIONS",
    "DATA_PERMISSIONS",
    "DEFAULT_ACTOR",
    "OPERATOR_ACTOR",
    "OPERATOR_PERMISSIONS",
    "PermissionDecision",
    "SAFE_PERMISSIONS",
    "check_permissions",
    "can_enable",
]
