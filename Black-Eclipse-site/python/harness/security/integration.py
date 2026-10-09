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
    ACTION_CODE_EXECUTE,
    ACTION_DEPLOY_PRODUCTION,
    ACTION_DEPLOY_STAGING,
    ACTION_SHELL_EXECUTE,
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


_EXECUTION_ACTIONS = (ACTION_SHELL_EXECUTE, ACTION_CODE_EXECUTE)


def sandbox_requirement(action: str) -> Optional[str]:
    """The isolation backend a policy REQUIRES for an execution action, or None.

    `BLACK_ECLIPSE_SANDBOX_REQUIRED`:
      * unset/""  → no extra requirement (the execution layer still uses
                    `code/sandbox.py`, which refuses when no primitive exists);
      * "1"       → any available sandbox backend must exist;
      * "docker"  → a Docker sandbox must be the active backend.

    Returns a refusal reason when the requirement is not met.
    """
    if action not in _EXECUTION_ACTIONS:
        return None
    required = (os.environ.get("BLACK_ECLIPSE_SANDBOX_REQUIRED") or "").strip().lower()
    if not required or required in ("0", "false", "no", "off"):
        return None
    from .sandbox import get_sandbox

    sandbox = get_sandbox()
    if required == "docker" and sandbox.name != "docker":
        return f"a docker sandbox is required but {sandbox.name!r} is the active backend"
    if not sandbox.available():
        return "no execution sandbox is available"
    return None


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
        tenant = _tenant_for(ctx)
        resolved_session = session_id or getattr(ctx, "session_id", None) or run_id
        # Sandbox non-bypass: when a backend is required but absent, refuse the
        # execution BEFORE it can run, and record why.
        refusal = sandbox_requirement(action)
        if refusal:
            try:
                active.audit_event(
                    type="security.sandbox.blocked", category="sandbox",
                    tool=name, action=action, decision=Decision.DENY.value,
                    result="denied", error=refusal, tenant_id=tenant,
                    session_id=(session_id or run_id),
                )
            except Exception:  # noqa: BLE001
                pass
            return False
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
