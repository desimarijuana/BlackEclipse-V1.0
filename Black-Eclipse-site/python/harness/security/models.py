"""Core security contracts — the vocabulary the whole subsystem speaks.

This module is deliberately dependency-free (stdlib only). Every other module in
`harness.security` imports these types, and the gateway is the only thing that
combines them into a decision. Keeping the vocabulary here means there is exactly
one definition of `Decision`, `RiskLevel`, `AuthorizationRequest`, etc.

Nothing in this module performs I/O or makes a decision; it is pure data.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ── Decisions ────────────────────────────────────────────────────────────────
class Decision(str, Enum):
    """The three possible outcomes of an authorization request.

    There is no fourth state and no boolean. `APPROVAL_REQUIRED` is distinct from
    `ALLOW` precisely so that an un-approved privileged action can never be
    mistaken for an allowed one.
    """

    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


class Permission(str, Enum):
    """The coarse authorization classes. Every action maps to exactly one.

    Permissions are always evaluated together with a resource scope — a global
    boolean permission is never sufficient (see `permissions.py`).
    """

    DISCOVER = "discover"
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    NETWORK = "network"
    CREDENTIAL = "credential"
    ADMIN = "admin"


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return _RISK_RANK[self]

    # `RiskLevel` subclasses `str`, whose lexicographic ordering would make
    # `"low" >= "high"` true. Define ALL comparisons from `rank` so ordering is
    # by severity, not by spelling.
    def _other_rank(self, other: Any) -> int:
        if isinstance(other, RiskLevel):
            return other.rank
        return _RISK_RANK[RiskLevel(str(other).lower())]

    def __lt__(self, other: Any) -> bool:  # type: ignore[override]
        return self.rank < self._other_rank(other)

    def __le__(self, other: Any) -> bool:  # type: ignore[override]
        return self.rank <= self._other_rank(other)

    def __gt__(self, other: Any) -> bool:  # type: ignore[override]
        return self.rank > self._other_rank(other)

    def __ge__(self, other: Any) -> bool:  # type: ignore[override]
        return self.rank >= self._other_rank(other)

    def max(self, other: "RiskLevel") -> "RiskLevel":
        return self if self.rank >= other.rank else other


_RISK_RANK: dict[RiskLevel, int] = {
    RiskLevel.NONE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

    @classmethod
    def parse(cls, value: Any) -> "Environment":
        if isinstance(value, Environment):
            return value
        text = str(value or "development").strip().lower()
        if text in ("prod", "production", "live"):
            return cls.PRODUCTION
        if text in ("stage", "staging", "preprod", "pre-prod"):
            return cls.STAGING
        return cls.DEVELOPMENT


class Verdict(str, Enum):
    """A single floor rule's effect. `HARD_DENY` can never be overridden by an
    ordinary policy; `MANDATORY_APPROVAL` can never be downgraded to allow by a
    lower policy layer."""

    HARD_DENY = "hard_deny"
    HARD_ALLOW = "hard_allow"
    MANDATORY_APPROVAL = "mandatory_approval"
    NONE = "none"


class ApprovalType(str, Enum):
    ONCE = "once"
    TASK = "task"
    SESSION = "session"
    RESOURCE = "resource"
    TOOL = "tool"
    TIME_LIMITED = "time_limited"
    ADMIN = "admin"


class PolicyProfile(str, Enum):
    LOCKDOWN = "lockdown"
    SECURE = "secure"
    DEVELOPER = "developer"
    AUTONOMOUS = "autonomous"
    CUSTOM = "custom"


# ── Authored action / resource vocabulary ────────────────────────────────────
# Actions are dotted, domain-qualified strings. They are stable identifiers the
# policy and floor match against. Keep them lowercase and append-only.
ACTION_FS_READ = "filesystem.read"
ACTION_FS_WRITE = "filesystem.write"
ACTION_FS_DELETE = "filesystem.delete"
ACTION_FS_DISCOVER = "filesystem.discover"
ACTION_SHELL_EXECUTE = "shell.execute"
ACTION_CODE_EXECUTE = "code.execute"
ACTION_CODE_WRITE = "code.write"
ACTION_EXTERNAL = "external.action"
ACTION_GIT_WRITE = "git.write"
ACTION_GIT_EXTERNAL = "git.external"
ACTION_INFRA_WRITE = "infrastructure.write"
ACTION_INFRA_DESTROY = "infrastructure.destroy"
ACTION_BROWSER = "browser.action"
ACTION_COMPUTER = "computer.action"
ACTION_COMPUTER_FINANCE = "computer.finance"
ACTION_VISION = "vision.external"
ACTION_NETWORK_REQUEST = "network.request"
ACTION_DB_CONNECT = "database.connect"
ACTION_DB_READ = "database.read"
ACTION_DB_WRITE = "database.write"
ACTION_DB_DELETE = "database.delete"
ACTION_DB_DDL = "database.ddl"
ACTION_DB_ADMIN = "database.admin"
ACTION_DEPLOY_DEV = "deploy.dev"
ACTION_DEPLOY_STAGING = "deploy.staging"
ACTION_DEPLOY_PRODUCTION = "deploy.production"
ACTION_DEPLOY_DESTROY = "deploy.destroy"
ACTION_FIN_RESEARCH = "financial.research"
ACTION_FIN_MARKET_READ = "financial.market_read"
ACTION_FIN_PORTFOLIO_READ = "financial.portfolio_read"
ACTION_FIN_PAPER_TRADE = "financial.paper_trade"
ACTION_FIN_LIVE_TRADE = "financial.live_trade"
ACTION_FIN_CANCEL_ORDER = "financial.cancel_order"
ACTION_FIN_TRANSFER = "financial.transfer"
ACTION_FIN_WITHDRAW = "financial.withdraw"
ACTION_SECRET_ACCESS = "credential.access"
ACTION_SECRET_ADMIN = "credential.admin"
ACTION_SECURITY_POLICY = "security.policy"
ACTION_SECURITY_ADMIN = "security.admin"
ACTION_PLUGIN_INVOKE = "plugin.invoke"
ACTION_MCP_INVOKE = "mcp.invoke"
ACTION_SKILL_EXECUTE = "skill.execute"

# The mapping from a coarse Permission to the actions it may carry. Used as a
# fail-closed default when a caller supplies a permission but no action.
_PERMISSION_ACTIONS: dict[Permission, str] = {
    Permission.DISCOVER: ACTION_FS_DISCOVER,
    Permission.READ: ACTION_FS_READ,
    Permission.WRITE: ACTION_FS_WRITE,
    Permission.DELETE: ACTION_FS_DELETE,
    Permission.EXECUTE: ACTION_SHELL_EXECUTE,
    Permission.NETWORK: ACTION_NETWORK_REQUEST,
    Permission.CREDENTIAL: ACTION_SECRET_ACCESS,
    Permission.ADMIN: ACTION_SECURITY_ADMIN,
}


def now_ts() -> float:
    return time.time()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def permission_for_action(action: str) -> Permission:
    """The coarse permission an action belongs to (fail-closed: unknown → ADMIN,
    so an unrecognised action never inherits a weak permission)."""
    domain = str(action or "").split(".", 1)[0]
    if action.startswith("filesystem.read") or action.startswith("filesystem.discover"):
        return Permission.READ
    if action.startswith("filesystem.write"):
        return Permission.WRITE
    if action.startswith("filesystem.delete"):
        return Permission.DELETE
    if action.startswith("shell.") or action.startswith("code.execute"):
        return Permission.EXECUTE
    if action.startswith("code.write") or action.startswith("git.write"):
        return Permission.WRITE
    if action.startswith("git.external"):
        return Permission.EXECUTE
    if action.startswith("network.") or action.startswith("vision.") or action.startswith("browser."):
        return Permission.NETWORK
    if action.startswith("credential."):
        return Permission.CREDENTIAL
    if (
        action.startswith("database.")
        or action.startswith("deploy.")
        or action.startswith("financial.")
        or action.startswith("infrastructure.")
        or action.startswith("computer.finance")
    ):
        return Permission.ADMIN
    if action.startswith("security."):
        return Permission.ADMIN
    if action.startswith("external."):
        return Permission.EXECUTE
    if action.startswith("computer."):
        return Permission.EXECUTE
    if action.startswith("plugin.") or action.startswith("mcp.") or action.startswith("skill."):
        return Permission.EXECUTE
    if not domain:
        return Permission.ADMIN
    return Permission.ADMIN


def action_for_permission(permission: Permission) -> str:
    return _PERMISSION_ACTIONS.get(permission, ACTION_SECURITY_ADMIN)


# ── Actor + context ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Actor:
    """Who is asking. `id` is a label; authority is never derived from it alone."""

    id: str = "local"
    kind: str = "agent"  # user | agent | plugin | mcp | skill | system
    operator: bool = False
    grants: frozenset[str] = frozenset()
    tenant_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "operator": self.operator,
                "tenantId": self.tenant_id}


@dataclass
class SecurityContext:
    """A per-session security context. There is exactly one per running session,
    and capabilities/secrets/approvals are looked up within it — never shared
    across sessions."""

    session_id: str = field(default_factory=lambda: new_id("secsess"))
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    workspace_id: Optional[str] = None
    environment: Environment = Environment.DEVELOPMENT
    actor: Actor = field(default_factory=Actor)
    capabilities: list[str] = field(default_factory=list)
    network_policy: Optional[str] = None
    approval_state: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=now_ts)
    closed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "tenantId": self.tenant_id,
            "userId": self.user_id,
            "agentId": self.agent_id,
            "taskId": self.task_id,
            "workspaceId": self.workspace_id,
            "environment": self.environment.value,
            "actor": self.actor.to_dict(),
            "capabilities": list(self.capabilities),
            "networkPolicy": self.network_policy,
            "createdAt": self.created_at,
            "closed": self.closed,
        }


# ── Request / decision ───────────────────────────────────────────────────────
@dataclass
class AuthorizationRequest:
    """A complete description of a privileged operation.

    Every field is optional except the action; a missing field is *not* treated as
    authority. The gateway fills in the environment/session/task from the context
    when not supplied, and computes risk server-side.
    """

    action: str
    resource: str = ""
    permission: Optional[Permission] = None
    actor: str = "agent"
    user: Optional[str] = None
    tenant: Optional[str] = None
    agent: Optional[str] = None
    session: Optional[str] = None
    task: Optional[str] = None
    tool: Optional[str] = None
    environment: Environment = Environment.DEVELOPMENT
    workspace: Optional[str] = None
    requested_capabilities: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    def resolved_permission(self) -> Permission:
        return self.permission or permission_for_action(self.action)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "resource": self.resource,
            "permission": self.resolved_permission().value,
            "actor": self.actor,
            "user": self.user,
            "tenant": self.tenant,
            "agent": self.agent,
            "session": self.session,
            "task": self.task,
            "tool": self.tool,
            "environment": self.environment.value,
            "workspace": self.workspace,
            "requestedCapabilities": list(self.requested_capabilities),
            "context": dict(self.context),
        }


@dataclass
class AuthorizationDecision:
    """The gateway's single answer. `allowed` is only True for `ALLOW`; an
    approval-required decision is NOT allowed until it is claimed."""

    decision: Decision
    reason: str = ""
    policy: str = ""
    risk: RiskLevel = RiskLevel.NONE
    matched_rules: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    approval_id: Optional[str] = None
    capability_id: Optional[str] = None
    expiration: Optional[float] = None
    audit_reference: Optional[str] = None

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW

    @property
    def needs_approval(self) -> bool:
        return self.decision is Decision.APPROVAL_REQUIRED

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "policy": self.policy,
            "risk": self.risk.value,
            "matchedRules": list(self.matched_rules),
            "constraints": list(self.constraints),
            "approvalId": self.approval_id,
            "capabilityId": self.capability_id,
            "expiration": self.expiration,
            "auditReference": self.audit_reference,
        }


class SecurityDenied(Exception):
    """Raised by `SecurityGateway.require` when a request is denied."""

    def __init__(self, decision: AuthorizationDecision) -> None:
        self.decision = decision
        super().__init__(decision.reason or f"security denied: {decision.decision.value}")


class ApprovalRequired(Exception):
    """Raised by `SecurityGateway.require` when an approval is required and not
    supplied. Carries the approval id so a caller can surface the request."""

    def __init__(self, decision: AuthorizationDecision) -> None:
        self.decision = decision
        super().__init__(decision.reason or "security approval required")


__all__ = [
    "ACTION_BROWSER",
    "ACTION_CODE_EXECUTE",
    "ACTION_CODE_WRITE",
    "ACTION_COMPUTER",
    "ACTION_COMPUTER_FINANCE",
    "ACTION_DB_ADMIN",
    "ACTION_DB_CONNECT",
    "ACTION_DB_DDL",
    "ACTION_DB_DELETE",
    "ACTION_DB_READ",
    "ACTION_DB_WRITE",
    "ACTION_DEPLOY_DEV",
    "ACTION_DEPLOY_DESTROY",
    "ACTION_DEPLOY_PRODUCTION",
    "ACTION_DEPLOY_STAGING",
    "ACTION_FIN_CANCEL_ORDER",
    "ACTION_FIN_LIVE_TRADE",
    "ACTION_FIN_MARKET_READ",
    "ACTION_FIN_PAPER_TRADE",
    "ACTION_FIN_PORTFOLIO_READ",
    "ACTION_FIN_RESEARCH",
    "ACTION_FIN_TRANSFER",
    "ACTION_FIN_WITHDRAW",
    "ACTION_EXTERNAL",
    "ACTION_FS_DELETE",
    "ACTION_FS_DISCOVER",
    "ACTION_FS_READ",
    "ACTION_FS_WRITE",
    "ACTION_GIT_EXTERNAL",
    "ACTION_GIT_WRITE",
    "ACTION_INFRA_DESTROY",
    "ACTION_INFRA_WRITE",
    "ACTION_MCP_INVOKE",
    "ACTION_NETWORK_REQUEST",
    "ACTION_PLUGIN_INVOKE",
    "ACTION_SECRET_ACCESS",
    "ACTION_SECRET_ADMIN",
    "ACTION_SECURITY_ADMIN",
    "ACTION_SECURITY_POLICY",
    "ACTION_SHELL_EXECUTE",
    "ACTION_SKILL_EXECUTE",
    "ACTION_VISION",
    "Actor",
    "ApprovalRequired",
    "ApprovalType",
    "AuthorizationDecision",
    "AuthorizationRequest",
    "Decision",
    "Environment",
    "Permission",
    "PolicyProfile",
    "RiskLevel",
    "SecurityContext",
    "SecurityDenied",
    "Verdict",
    "action_for_permission",
    "new_id",
    "now_ts",
    "permission_for_action",
]
