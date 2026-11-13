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

import logging
import os
from typing import Any, Optional

from . import hardline
from .bootstrap import get_gateway
from .classification import classify_tool
from .effect_tokens import token_mode
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

log = logging.getLogger("harness.security.integration")


def _is_effectful(tool: Any) -> bool:
    if getattr(tool, "effect", None):
        return True
    return str(getattr(tool, "permission", "read")) != "read"


def _audit_hardline(active: Any, *, name: str, verdict: Any, tenant: Optional[str],
                    session_id: str) -> None:
    if active is None:
        return
    try:
        active.audit_event(
            type="security.hardline.blocked", category="hardline",
            tool=name, action="shell.execute", decision=Decision.DENY.value,
            result="denied", error=f"{verdict.rule}: {verdict.reason}",
            tenant_id=tenant, session_id=session_id,
        )
    except Exception:  # noqa: BLE001 - audit is best effort; the denial stands
        pass

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


def profile_requirement(action: str) -> Optional[str]:
    """The sandbox PROFILE the operator configured, and whether it is enforceable.

    `BLACK_ECLIPSE_SANDBOX_PROFILE` names a promise (`read-only`,
    `workspace-write`, `network-allowlist`, `full`). If the host cannot keep that
    promise, the execution is refused rather than silently downgraded.
    """
    if action not in _EXECUTION_ACTIONS:
        return None
    from .profiles import configured_profile, resolve_profile

    profile = configured_profile()
    if profile is None:
        return None
    plan = resolve_profile(profile)
    if not plan.enforceable:
        return plan.reason or f"sandbox profile {profile.value!r} is not enforceable here"
    return None


def _attach_effect_token(
    ctx: Any, *, run_id: str, tool: str, args: dict[str, Any], tenant: Optional[str],
) -> None:
    """Bind the ALLOW decision to this exact call (C6 effect tokens)."""
    from .effect_tokens import attach_token

    attach_token(ctx, run_id=run_id, tool=tool, args=args, tenant_id=tenant)


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
        tenant = _tenant_for(ctx)
        resolved_session = session_id or getattr(ctx, "session_id", None) or run_id

        # W6: the always-on command hardline is evaluated FIRST, before the
        # floor/policy/approval chain. No grant, YOLO or profile can override it.
        verdict = hardline.evaluate(
            hardline.command_from_args(args or {}), tool=name,
        )
        if verdict is not None:
            _audit_hardline(
                active, name=name, verdict=verdict, tenant=tenant,
                session_id=str(resolved_session or run_id),
            )
            return False

        classification = classify_tool(name, args or {})
        if active is None:
            # W6: under `enforce` an effectful call must not run without the
            # gateway that mints its token. Shadow keeps today's behaviour.
            if _is_effectful(tool) and token_mode() == "enforce":
                log.error(
                    "security gateway unavailable; refusing effectful tool %s "
                    "(HARNESS_EFFECT_TOKENS=enforce)", name,
                )
                return False
            return bool(await inner(tool, args, ctx)) if inner is not None else True
        if classification is None:
            return bool(await inner(tool, args, ctx)) if inner is not None else True
        action, resource, permission = classification
        environment = _ENV_BY_ACTION.get(action, _environment_for(ctx))
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
        profile_refusal = profile_requirement(action)
        if profile_refusal:
            try:
                active.audit_event(
                    type="security.sandbox.profile_blocked", category="sandbox",
                    tool=name, action=action, decision=Decision.DENY.value,
                    result="denied", error=profile_refusal, tenant_id=tenant,
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
            if claimed.allowed:
                _attach_effect_token(
                    ctx, run_id=run_id, tool=name, args=args, tenant=tenant,
                )
            return claimed.allowed
        # ALLOW: the inner chain remains the approval authority for the tool's
        # own semantics (single-use, digest-bound, per capability). The effect
        # token binds this decision to the exact tool + arguments the executor
        # is about to run.
        approved = bool(await inner(tool, args, ctx)) if inner is not None else True
        if approved:
            _attach_effect_token(ctx, run_id=run_id, tool=name, args=args, tenant=tenant)
        return approved

    authorize.__security_authorizer__ = True  # type: ignore[attr-defined]
    return authorize


__all__ = ["classify_tool", "make_security_authorizer", "profile_requirement"]
