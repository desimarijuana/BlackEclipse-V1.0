"""Security Gateway — the ONE decision path for every privileged operation.

Every authorization request is evaluated in a fixed order, and each stage can only
make the outcome *more* restrictive:

    1. session/workspace isolation
    2. Security Floor        (hard deny / mandatory approval / hard allow)
    3. Risk Engine           (server-side)
    4. Policy Engine         (layered, restrict-only)
    5. Capability Engine     (an explicit capability may satisfy an approval)
    6. Approval Engine       (standing grants, then a pending request)

The result is exactly one `AuthorizationDecision`. Failures anywhere fail CLOSED.
`authorize` never raises; `require` raises on anything that is not ALLOW.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .approval import ApprovalEngine
from .audit import AuditLog, AuditSink
from .capabilities import Capability, CapabilityEngine, CapabilityError
from .context import IsolationViolation, SessionRegistry
from .floor import Verdict, default_floor
from .models import (
    Actor,
    ApprovalRequired,
    ApprovalType,
    AuthorizationDecision,
    AuthorizationRequest,
    Decision,
    Environment,
    RiskLevel,
    SecurityContext,
    SecurityDenied,
)
from .network import NetworkPolicyEngine, default_network_engine
from .permissions import canonicalize_resource
from .policy import PolicyEngine, default_policy
from .risk import RiskEngine
from .secrets import SecretsManager, build_default_secrets_manager
from .store import SecurityStore

log = logging.getLogger("harness.security.gateway")

# Risk at or above this level requires an approval even when policy would allow,
# unless an explicit capability or a standing grant covers the exact request.
_APPROVAL_RISK_FLOOR = RiskLevel.HIGH


class SecurityGateway:
    """The single entry point. Construct once per process (see `bootstrap.py`)."""

    def __init__(
        self,
        *,
        store: Any = None,
        approvals: Any = None,
        metrics: Any = None,
        events: Any = None,
        floor: Any = None,
        policy: Optional[PolicyEngine] = None,
        risk: Optional[RiskEngine] = None,
        network: Optional[NetworkPolicyEngine] = None,
        secrets: Optional[SecretsManager] = None,
        profile: Optional[str] = None,
    ) -> None:
        self.security_store = SecurityStore(store) if store is not None else None
        self.floor = floor or default_floor()
        self.policy = policy or PolicyEngine()
        if profile:
            from .models import PolicyProfile

            if isinstance(profile, PolicyProfile):
                self.policy.set_profile(profile)
            else:
                try:
                    self.policy.set_profile(PolicyProfile(str(profile).lower()))
                except ValueError:
                    pass
        self.risk = risk or RiskEngine()
        self.network = network or default_network_engine()
        self.secrets = secrets or build_default_secrets_manager()
        self._approvals_raw = approvals
        self.approvals = ApprovalEngine(approvals)
        self.capabilities = CapabilityEngine(self.security_store)
        self.sessions = SessionRegistry()
        # An optional external append-only anchor (JSONL + HMAC-signed head) so the
        # audit trail survives outside the runtime's writable database.
        sink = None
        audit_log_path = os.environ.get("BLACK_ECLIPSE_SECURITY_AUDIT_LOG")
        if audit_log_path:
            try:
                sink = AuditSink(audit_log_path)
            except Exception:  # noqa: BLE001 - a bad sink path must not block the gateway
                log.warning("security audit sink unavailable", exc_info=True)
        self.audit = AuditLog(
            self.security_store, secrets=self.secrets, events=events, metrics=metrics, sink=sink,
        )

        self._authorizations = 0
        self._denials = 0
        self._approval_required = 0
        self._failures = 0
        # Multi-tenant mode: a request with no resolved tenant is refused unless
        # it is an explicit operator context. Off zero-config; auto-on when the
        # front door requires auth (see `security.identity`).
        try:
            from .identity import multi_tenant_required  # noqa: PLC0415

            self.multi_tenant = multi_tenant_required()
        except Exception:  # noqa: BLE001
            self.multi_tenant = False

        self._record_policy_version()

    # ── context ──────────────────────────────────────────────────────────────
    def open_session(self, **kwargs: Any) -> SecurityContext:
        return self.sessions.create(**kwargs)

    def close_session(self, session_id: str) -> dict[str, Any]:
        """Close a session and revoke its temporary authority (fail-closed)."""
        revoked_caps = self.capabilities.revoke_all(session_id=session_id)
        context = self.sessions.get(session_id)
        if context is not None:
            context.capabilities = []
            self.sessions.close(session_id)
        self.audit.record(
            type="security.session.closed", category="session",
            session_id=session_id, result="ok",
            payload={"revokedCapabilities": revoked_caps},
        )
        return {"sessionId": session_id, "revokedCapabilities": revoked_caps}

    # ── authorize ────────────────────────────────────────────────────────────
    def authorize(
        self,
        request: AuthorizationRequest,
        *,
        context: Optional[SecurityContext] = None,
        claim_approval: bool = False,
        defer_policy_approval: bool = False,
    ) -> AuthorizationDecision:
        """Evaluate one request. Never raises; always returns a decision.

        `defer_policy_approval` lets a migrated capability delegate *policy-driven*
        approvals to its own established approval chain while the floor's
        mandatory approvals remain enforced here. It never weakens the floor or a
        policy deny.
        """
        self._authorizations += 1
        try:
            return self._authorize(
                request, context=context, claim_approval=claim_approval,
                defer_policy_approval=defer_policy_approval,
            )
        except Exception as exc:  # noqa: BLE001 - any failure is fail-closed
            self._failures += 1
            log.warning("security authorization failed closed: %s", exc)
            return self._finalize(
                AuthorizationDecision(
                    decision=Decision.DENY,
                    reason="security evaluation failed — failing closed",
                    policy="error",
                    risk=RiskLevel.CRITICAL,
                    matched_rules=("gateway.fail-closed",),
                ),
                request, context=None, category="failure",
            )

    def _authorize(
        self,
        request: AuthorizationRequest,
        *,
        context: Optional[SecurityContext],
        claim_approval: bool,
        defer_policy_approval: bool = False,
    ) -> AuthorizationDecision:
        action = str(request.action or "")
        resource = str(request.resource or "")
        environment = request.environment or Environment.DEVELOPMENT
        tenant = (
            request.tenant
            or (context.tenant_id if context is not None else None)
            or str((request.context or {}).get("tenant") or "")
            or None
        )
        is_operator = bool((request.context or {}).get("operator"))
        request.context = {**(request.context or {}), "_tenant": tenant}
        if context is not None:
            try:
                self.sessions.assert_session(context, request.session)
                self.sessions.assert_workspace(context, request.workspace)
                self.sessions.assert_tenant(context, request.tenant)
            except IsolationViolation as exc:
                return self._finalize(
                    AuthorizationDecision(
                        decision=Decision.DENY, reason=str(exc), policy="isolation",
                        risk=RiskLevel.HIGH, matched_rules=("isolation",),
                    ),
                    request, context=context, category="isolation",
                )
            if request.environment is Environment.DEVELOPMENT:
                environment = context.environment
        if self.multi_tenant and not tenant and not is_operator:
            self._denials += 1
            return self._finalize(
                AuthorizationDecision(
                    decision=Decision.DENY, reason="tenant context required",
                    policy="tenant", risk=RiskLevel.HIGH, matched_rules=("tenant",),
                ),
                request, context=context, category="isolation",
            )

        risk = self.risk.evaluate(
            action=action, resource=resource, environment=environment,
            network_destination=(resource if action.startswith("network.") else None),
            hint=(request.context or {}).get("risk"),
        )
        permission = request.resolved_permission()

        # 1. Security Floor ────────────────────────────────────────────────────
        floor_verdict = self.floor.evaluate(action=action, resource=resource, environment=environment)
        floor_approval = False
        if floor_verdict is not None:
            if floor_verdict.verdict is Verdict.HARD_DENY:
                return self._deny(request, risk, "floor", floor_verdict.reason,
                                  rules=(floor_verdict.rule,), category="floor",
                                  reason_prefix="blocked by the security floor")
            if floor_verdict.verdict is Verdict.HARD_ALLOW:
                return self._finalize(
                    AuthorizationDecision(
                        decision=Decision.ALLOW,
                        reason=floor_verdict.reason or "allowed by the security floor",
                        policy="floor", risk=risk, matched_rules=(floor_verdict.rule,),
                    ),
                    request, context=context, category="floor",
                )
            floor_approval = True

        # 2. Policy ────────────────────────────────────────────────────────────
        match = self.policy.evaluate(action=action, resource=resource, environment=environment)
        if match.verdict == "deny":
            return self._deny(request, risk, match.layer, match.reason,
                              rules=(match.layer,), category="policy",
                              reason_prefix="denied by policy")

        # 3. Capability — an explicit capability satisfies an approval. ─────────
        capability = self._find_capability(request, context)
        if capability is not None:
            return self._finalize(
                AuthorizationDecision(
                    decision=Decision.ALLOW,
                    reason="authorized by capability",
                    policy="capability", risk=risk,
                    matched_rules=(match.layer,), capability_id=capability.id,
                    expiration=capability.expires_at,
                ),
                request, context=context, category="authorization",
            )

        # 4. Approval decision ─────────────────────────────────────────────────
        policy_needs_approval = (
            match.verdict == "approval"
            or (match.verdict == "allow" and risk >= _APPROVAL_RISK_FLOOR)
        )
        if defer_policy_approval:
            # A migrated capability's own single-use approval chain owns BOTH
            # policy-driven and floor-mandated approvals (so there is exactly one
            # approval, not two). Floor HARD_DENY and policy DENY are still
            # terminal and were handled above; only the *approval* is deferred.
            policy_needs_approval = False
            floor_approval = False
        needs_approval = floor_approval or policy_needs_approval
        if needs_approval:
            scope = self._grant_scope(request, context)
            action_key = self._approval_action(request)
            if self.approvals.granted(action=action_key, resource=resource, scope=scope):
                return self._finalize(
                    AuthorizationDecision(
                        decision=Decision.ALLOW, reason="authorized by standing grant",
                        policy=match.layer, risk=risk, matched_rules=(match.layer, "grant"),
                    ),
                    request, context=context, category="approval",
                )
            if claim_approval:
                ticket = self.approvals.claim(
                    action=action_key, resource=resource,
                    session_id=(context.session_id if context else request.session),
                    task_id=request.task, approval_type=ApprovalType.ONCE,
                )
                if ticket is not None:
                    return self._finalize(
                        AuthorizationDecision(
                            decision=Decision.ALLOW, reason="approved by operator",
                            policy="approval", risk=risk, approval_id=ticket.id,
                            matched_rules=(match.layer, "approval"),
                        ),
                        request, context=context, category="approval",
                    )
            ticket = self.approvals.request(
                action=action_key, resource=resource,
                session_id=(context.session_id if context else request.session),
                task_id=request.task, run_id=request.context.get("runId"),
                approval_type=ApprovalType.ONCE, risk=risk.value,
                summary=f"Approve {action} on {resource or '(no resource)'}",
            )
            if ticket is None:
                # No approval store reachable → fail closed.
                return self._deny(request, risk, match.layer,
                                  "approval service unavailable", rules=(match.layer,),
                                  category="approval", reason_prefix="approval required but unavailable")
            self._approval_required += 1
            return self._finalize(
                AuthorizationDecision(
                    decision=Decision.APPROVAL_REQUIRED,
                    reason=match.reason or "requires operator approval",
                    policy=match.layer, risk=risk, approval_id=ticket.id,
                    matched_rules=(match.layer,),
                    constraints=tuple(request.requested_capabilities),
                ),
                request, context=context, category="approval",
            )

        # 5. Allow ─────────────────────────────────────────────────────────────
        return self._finalize(
            AuthorizationDecision(
                decision=Decision.ALLOW, reason=match.reason or "allowed by policy",
                policy=match.layer, risk=risk, matched_rules=(match.layer,),
            ),
            request, context=context, category="authorization",
        )

    # ── helpers ──────────────────────────────────────────────────────────────
    def _find_capability(self, request: AuthorizationRequest, context: Optional[SecurityContext]) -> Optional[Capability]:
        subject = request.actor or (context.actor.id if context else "agent")
        return self.capabilities.find(
            subject=subject,
            action=request.action,
            resource=request.resource,
            scope=self._grant_scope(request, context),
            session_id=(context.session_id if context else request.session),
            task_id=request.task,
            tenant_id=str((request.context or {}).get("_tenant") or "") or None,
        )

    def _grant_scope(self, request: AuthorizationRequest, context: Optional[SecurityContext]) -> str:
        if context is not None and context.workspace_id:
            return context.workspace_id
        return request.workspace or str((request.context or {}).get("scope") or "")

    def _approval_action(self, request: AuthorizationRequest) -> str:
        # Bind the approval to the tool when present, so a different tool cannot
        # reuse it, plus the action itself.
        return f"{request.tool}::{request.action}" if request.tool else request.action

    def _deny(
        self, request: AuthorizationRequest, risk: RiskLevel, policy: str, reason: str,
        *, rules: tuple[str, ...], category: str, reason_prefix: str,
    ) -> AuthorizationDecision:
        self._denials += 1
        return self._finalize(
            AuthorizationDecision(
                decision=Decision.DENY,
                reason=f"{reason_prefix}: {reason}" if reason_prefix else reason,
                policy=policy, risk=risk, matched_rules=rules,
            ),
            request, context=None, category=category,
        )

    def _finalize(
        self, decision: AuthorizationDecision, request: AuthorizationRequest,
        *, context: Optional[SecurityContext], category: str,
    ) -> AuthorizationDecision:
        record = self.audit.record(
            type=f"security.authorization.{decision.decision.value}",
            category=category,
            actor=request.actor,
            user_id=request.user,
            tenant_id=str((request.context or {}).get("_tenant") or "") or None,
            agent_id=request.agent,
            session_id=(context.session_id if context else request.session),
            task_id=request.task,
            tool=request.tool,
            action=request.action,
            resource=request.resource,
            decision=decision.decision.value,
            risk=decision.risk.value,
            policy=decision.policy,
            approval_id=decision.approval_id,
            capability_id=decision.capability_id,
            payload={"reason": decision.reason, "matchedRules": list(decision.matched_rules)},
        )
        decision.audit_reference = (record or {}).get("id")
        return decision

    # ── public seams ─────────────────────────────────────────────────────────
    def check(self, request: AuthorizationRequest, **kwargs: Any) -> bool:
        return self.authorize(request, **kwargs).allowed

    def require(self, request: AuthorizationRequest, **kwargs: Any) -> AuthorizationDecision:
        """Authorize or raise. `SecurityDenied` / `ApprovalRequired` on non-allow."""
        decision = self.authorize(request, **kwargs)
        if decision.decision is Decision.APPROVAL_REQUIRED:
            raise ApprovalRequired(decision)
        if decision.decision is Decision.DENY:
            raise SecurityDenied(decision)
        return decision

    def request_approval(self, request: AuthorizationRequest, **kwargs: Any) -> AuthorizationDecision:
        kwargs.setdefault("claim_approval", False)
        return self.authorize(request, **kwargs)

    # ── capabilities ─────────────────────────────────────────────────────────
    def issue_capability(self, **kwargs: Any) -> Capability:
        cap = self.capabilities.issue(**kwargs)
        self.audit.record(
            type="security.capability.issued", category="capability",
            actor=kwargs.get("subject"), action=kwargs.get("action"),
            resource=kwargs.get("resource"), capability_id=cap.id,
            result="ok", payload={"issuer": kwargs.get("issuer")},
        )
        return cap

    def revoke_capability(self, capability_id: str) -> bool:
        ok = self.capabilities.revoke(capability_id)
        self.audit.record(
            type="security.capability.revoked", category="capability",
            capability_id=capability_id, result="ok" if ok else "not_found",
        )
        return ok

    def delegate_capability(self, parent_id: str, **kwargs: Any) -> Capability:
        try:
            cap = self.capabilities.delegate(parent_id, **kwargs)
        except CapabilityError:
            self.audit.record(
                type="security.capability.delegation_denied", category="capability",
                capability_id=parent_id, result="denied",
            )
            raise
        self.audit.record(
            type="security.capability.delegated", category="capability",
            capability_id=cap.id, result="ok", payload={"parent": parent_id},
        )
        return cap

    # ── secrets ──────────────────────────────────────────────────────────────
    def validate_secret_access(
        self, ref: str, *, consumer: str, context: Optional[SecurityContext] = None,
        action: str = "", resource: str = "", session_id: Optional[str] = None,
        task_id: Optional[str] = None, tenant_id: Optional[str] = None,
    ) -> bool:
        try:
            value = self.secrets.resolve(
                ref, consumer=consumer, action=action, resource=resource,
                session_id=session_id or (context.session_id if context else None),
                task_id=task_id or (context.task_id if context else None),
                tenant_id=tenant_id or (context.tenant_id if context else None),
            )
            granted = value is not None
        except Exception:  # noqa: BLE001
            granted = False
        self.audit.record(
            type="security.secret.accessed" if granted else "security.secret.denied",
            category="secret", action="credential.access", resource=ref,
            decision=Decision.ALLOW.value if granted else Decision.DENY.value,
            result="ok" if granted else "denied",
            session_id=session_id or (context.session_id if context else None),
        )
        return granted

    def resolve_secret(self, ref: str, **kwargs: Any) -> Optional[str]:
        """Resolve a secret value (never audit the value itself)."""
        try:
            value = self.secrets.resolve(ref, **kwargs)
        except Exception:  # noqa: BLE001
            self.audit.record(
                type="security.secret.denied", category="secret",
                resource=ref, decision=Decision.DENY.value, result="denied",
            )
            return None
        self.audit.record(
            type="security.secret.accessed", category="secret",
            resource=ref, decision=Decision.ALLOW.value, result="ok",
        )
        return value

    def redact(self, value: Any) -> Any:
        return self.secrets.redact(value)

    # ── network ──────────────────────────────────────────────────────────────
    def check_network(self, url: str, *, direction: str = "egress") -> AuthorizationDecision:
        decision, reason, pinned = self.network.resolve(url, direction=direction)
        audit = self.audit.record(
            type=f"security.network.{decision.value}", category="network",
            action="network.request", resource=url, decision=decision.value,
            risk=self.risk.evaluate(action="network.request", resource=url,
                                    network_destination=url).value,
            payload={"reason": reason, "pid": pinned},
        )
        return AuthorizationDecision(
            decision=decision, reason=reason,
            policy="network", risk=self.risk.evaluate(action="network.request", resource=url),
            matched_rules=("network",), audit_reference=(audit or {}).get("id"),
        )

    # ── policy / audit ───────────────────────────────────────────────────────
    def get_policy(self) -> dict[str, Any]:
        return self.policy.snapshot()

    def reload_policy(self, documents: dict[str, Any], *, profile: Optional[str] = None, actor: str = "operator") -> dict[str, Any]:
        """Validate + atomically activate a new policy; record the change."""
        record = self.policy.reload(documents, profile=profile, actor=actor)
        if self.security_store is not None:
            self.security_store.save_policy_version(record, self.policy.snapshot())
        self.audit.record(
            type="security.policy.changed", category="policy",
            action="security.policy", actor=actor, result="ok",
            payload=record,
        )
        return record

    def audit_event(self, **kwargs: Any) -> Optional[dict[str, Any]]:
        return self.audit.record(**kwargs)

    def _record_policy_version(self) -> None:
        if self.security_store is None:
            return
        try:
            self.security_store.save_policy_version(
                {"version": self.policy.version, "profile": self.policy.profile.value,
                 "actor": "boot", "at": 0.0},
                self.policy.snapshot(),
            )
        except Exception:  # noqa: BLE001
            pass

    def health(self) -> dict[str, Any]:
        return {
            "ok": self._failures == 0,
            "authorizations": self._authorizations,
            "denials": self._denials,
            "approvalRequired": self._approval_required,
            "failures": self._failures,
            "floorRules": len(self.floor.rules),
            "policyVersion": self.policy.version,
            "profile": self.policy.profile.value,
            "networkRules": self.network.version,
            "secrets": self.secrets.stats(),
            "sessionsActive": self.sessions.active(),
            "capabilities": len(self.capabilities.snapshot()),
            "audit": self.audit.summary(),
        }

    def status(self) -> dict[str, Any]:
        return {
            "profile": self.policy.profile.value,
            "policyVersion": self.policy.version,
            "floor": self.floor.snapshot(),
            "network": self.network.snapshot(),
            "secrets": self.secrets.stats(),
            "audit": self.audit.summary(),
            "approvals": self.approvals.stats(),
        }


__all__ = ["SecurityGateway"]
