"""Migration seam — route EVERY effectful capability through the Security Gateway.

`build_effect_authorizer` (in `code/authorizers.py`) wraps the whole composed
authorizer with this module's `make_security_authorizer`, so every non-read tool
of every capability (filesystem, shell, git, browser, computer, execution,
application-runtime, plugins, MCP, skills) is classified by
`security/classification.py` and passes through the gateway. The gateway then:

  * enforces the Security Floor — a hard-deny (credentials, keys, the security
    config, OS dirs, destructive infrastructure) short-circuits to refusal no
    matter what the inner chain decides;
  * enforces a policy DENY;
  * audits and risk-scores every evaluation; and
  * defers approvals to the capability's own established single-use approval
    chain, so the operator UX is unchanged and there is exactly ONE approval.

Hard denies are never deferred. When no gateway is installed the inner authorizer
is returned unchanged — never a permissive stub.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .bootstrap import get_gateway
from .classification import classify_tool
from .models import (
    ACTION_DEPLOY_PRODUCTION,
    ACTION_DEPLOY_STAGING,
    AuthorizationRequest,
    Decision,
    Environment,
)
from .permissions import canonicalize_resource

# The deploy actions whose very name implies an environment.
_ENV_BY_ACTION = {
    ACTION_DEPLOY_PRODUCTION: Environment.PRODUCTION,
    ACTION_DEPLOY_STAGING: Environment.STAGING,
}


def _tenant_for(ctx: Any) -> Optional[str]:
    """Resolve the tenant from the run context or the process default.

    The verified identity is attached to the run context at the API boundary;
    this never trusts a model-supplied value.
    """
    raw = getattr(ctx, "tenant_id", None)
    if raw is None:
        candidate = getattr(ctx, "context", None)
        if isinstance(candidate, dict):
            raw = candidate.get("tenant") or candidate.get("tenantId")
    if raw is None:
        raw = os.environ.get("BLACK_ECLIPSE_DEFAULT_TENANT")
    return str(raw) if raw else None


def _environment_for(ctx: Any) -> Environment:
    """Resolve the environment from the run context, the deploy action, or the
    process default (`BLACK_ECLIPSE_ENVIRONMENT`). Default: development."""
    raw = getattr(ctx, "environment", None)
    if raw is None:
        candidate = getattr(ctx, "context", None)
        if isinstance(candidate, dict):
            raw = candidate.get("environment") or candidate.get("env")
    if raw is None:
        raw = os.environ.get("BLACK_ECLIPSE_ENVIRONMENT")
    return Environment.parse(raw) if raw else Environment.DEVELOPMENT


def make_security_authorizer(
    inner: Optional[Any],
    *,
    run_id: str = "",
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    gateway: Optional[Any] = None,
) -> Optional[Any]:
    """Wrap an existing effect authorizer with the Security Gateway."""

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        active = gateway or get_gateway()
        name = str(getattr(tool, "name", ""))
        classification = classify_tool(name, args or {})
        if active is None or classification is None:
            return bool(await inner(tool, args, ctx)) if inner is not None else True
        action, resource, permission = classification
        environment = _ENV_BY_ACTION.get(action, _environment_for(ctx))
        resolved_session = session_id or getattr(ctx, "session_id", None) or run_id
        tenant = _tenant_for(ctx)
        security_context = None
        if getattr(active, "sessions", None) is not None and resolved_session:
            security_context = active.sessions.get_or_create(
                resolved_session,
                tenant_id=tenant,
                agent_id=getattr(ctx, "agent_id", None),
                workspace_id=workspace_id,
                environment=environment,
            )
        request = AuthorizationRequest(
            action=action,
            resource=resource,
            permission=permission,
            actor=str(getattr(ctx, "agent_id", None) or "agent"),
            tenant=tenant,
            agent=ctx.agent_id if hasattr(ctx, "agent_id") else None,
            session=resolved_session,
            task=getattr(ctx, "task_id", None),
            tool=name,
            environment=environment,
            workspace=workspace_id or (getattr(getattr(ctx, "workspace", None), "root_id", None)),
            context={"runId": run_id, "tool": name, "resource": resource},
        )
        decision = active.authorize(
            request, context=security_context, claim_approval=False,
            defer_policy_approval=True,
        )
        if decision.decision is Decision.DENY:
            # The gateway already audited. Refuse; never fall through to inner.
            return False
        if decision.decision is Decision.APPROVAL_REQUIRED:
            # Only reachable when a caller did NOT defer approvals (the migrated
            # path defers, so the inner chain owns the approval). Try to claim an
            # operator approval; otherwise refuse, fail-closed.
            claimed = active.authorize(
                request, context=security_context, claim_approval=True,
                defer_policy_approval=True,
            )
            return claimed.allowed
        # ALLOW: the inner chain remains the approval authority for the tool's
        # own semantics (single-use, digest-bound, per capability).
        return bool(await inner(tool, args, ctx)) if inner is not None else True

    authorize.__security_authorizer__ = True  # type: ignore[attr-defined]
    return authorize


__all__ = ["classify_tool", "make_security_authorizer"]
