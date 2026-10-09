"""Capability engine — unforgeable, scoped, revocable authority tokens.

A capability is a signed-into-the-store record that grants a specific subject the
right to perform a specific action on a specific resource, under constraints, for
a bounded time and scope. Capabilities are validated before execution and can be
delegated, restricted or revoked.

The non-negotiable invariant: **delegation may only reduce or preserve authority,
never increase it.** A delegated capability is the intersection of the parent's
(subject, scope, constraints, expiry) with the requested subset. If the requested
subset is not contained in the parent, the delegation is refused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .models import Permission, new_id, now_ts
from .permissions import canonicalize_resource, fnmatch_name, resource_matches


@dataclass
class Capability:
    id: str
    subject: str
    resource: str
    action: str
    scope: str = ""
    constraints: tuple[str, ...] = ()
    issued_at: float = field(default_factory=now_ts)
    expires_at: Optional[float] = None
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    tenant_id: Optional[str] = None
    issuer: str = "system"
    revocable: bool = True
    parent_id: Optional[str] = None
    revoked: bool = False
    permission: Optional[Permission] = None

    @property
    def expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= now_ts()

    @property
    def active(self) -> bool:
        return not self.revoked and not self.expired

    def permits(
        self,
        *,
        subject: str,
        action: str,
        resource: str,
        scope: str = "",
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Whether this capability authorizes exactly this request.

        Subject must match. Action must match. Resource must be covered by the
        capability's resource glob. A capability bound to a session/task/tenant
        only authorizes within that session/task/tenant.
        """
        if not self.active:
            return False
        if self.subject != subject:
            return False
        # A tenant-bound capability is usable ONLY within that tenant; a
        # tenant-less capability is usable only in a tenant-less (single-tenant)
        # request — never to cross a tenant boundary.
        if self.tenant_id is not None and self.tenant_id != tenant_id:
            return False
        if self.tenant_id is None and tenant_id is not None:
            return False
        if not fnmatch_name(self.action, action):
            return False
        if not resource_matches(self.resource, resource):
            return False
        if self.scope and scope and self.scope != scope:
            return False
        if self.scope and not scope:
            return False
        if self.session_id is not None and self.session_id != session_id:
            return False
        if self.task_id is not None and self.task_id != task_id:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "resource": self.resource,
            "action": self.action,
            "scope": self.scope,
            "constraints": list(self.constraints),
            "issuedAt": self.issued_at,
            "expiresAt": self.expires_at,
            "sessionId": self.session_id,
            "taskId": self.task_id,
            "tenantId": self.tenant_id,
            "issuer": self.issuer,
            "revocable": self.revocable,
            "parentId": self.parent_id,
            "revoked": self.revoked,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Capability":
        return cls(
            id=str(data.get("id") or new_id("cap")),
            subject=str(data.get("subject") or ""),
            resource=str(data.get("resource") or "**"),
            action=str(data.get("action") or ""),
            scope=str(data.get("scope") or ""),
            constraints=tuple(data.get("constraints") or ()),
            issued_at=float(data.get("issuedAt") or now_ts()),
            expires_at=(float(data["expiresAt"]) if data.get("expiresAt") is not None else None),
            session_id=data.get("sessionId"),
            task_id=data.get("taskId"),
            tenant_id=data.get("tenantId"),
            issuer=str(data.get("issuer") or "system"),
            revocable=bool(data.get("revocable", True)),
            parent_id=data.get("parentId"),
            revoked=bool(data.get("revoked", False)),
        )


class CapabilityError(Exception):
    """A capability operation was refused (bad escalation, unknown id, …)."""


class CapabilityEngine:
    """Issue / validate / delegate / restrict / revoke / expire capabilities.

    In-memory by default; an optional `store` (a `security.store.SecurityStore`)
    persists issued capabilities so they survive a restart. The engine holds the
    rules; the store holds the bytes.
    """

    def __init__(self, store: Any = None) -> None:
        self._by_id: dict[str, Capability] = {}
        self._store = store
        if store is not None:
            for record in store.list_capabilities():
                cap = Capability.from_dict(record)
                self._by_id[cap.id] = cap

    # ── issue ────────────────────────────────────────────────────────────────
    def issue(
        self,
        *,
        subject: str,
        action: str,
        resource: str = "**",
        scope: str = "",
        constraints: Iterable[str] = (),
        ttl_seconds: Optional[float] = None,
        expires_at: Optional[float] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        issuer: str = "system",
        revocable: bool = True,
        permission: Optional[Permission] = None,
    ) -> Capability:
        if not subject or not action:
            raise CapabilityError("a capability needs a subject and an action")
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise CapabilityError("capability ttl must be positive")
        expiry = expires_at
        if expiry is None and ttl_seconds is not None:
            expiry = now_ts() + float(ttl_seconds)
        cap = Capability(
            id=new_id("cap"),
            subject=str(subject),
            action=str(action),
            resource=canonicalize_resource(resource) or "**",
            scope=str(scope or ""),
            constraints=tuple(constraints),
            expires_at=expiry,
            session_id=session_id,
            task_id=task_id,
            tenant_id=tenant_id,
            issuer=issuer,
            revocable=revocable,
            permission=permission,
        )
        self._by_id[cap.id] = cap
        if self._store is not None:
            self._store.save_capability(cap.to_dict())
        return cap

    # ── validate ─────────────────────────────────────────────────────────────
    def get(self, capability_id: str) -> Optional[Capability]:
        cap = self._by_id.get(str(capability_id))
        if cap is not None and cap.expired and not cap.revoked:
            # Reflect the expiry lazily without losing the audit trail.
            pass
        return cap

    def validate(self, capability_id: str) -> bool:
        cap = self.get(capability_id)
        return bool(cap and cap.active)

    def find(
        self,
        *,
        subject: str,
        action: str,
        resource: str,
        scope: str = "",
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Capability]:
        """The first active capability authorizing this exact request, or None."""
        for cap in self._by_id.values():
            if cap.permits(
                subject=subject, action=action, resource=resource,
                scope=scope, session_id=session_id, task_id=task_id,
                tenant_id=tenant_id,
            ):
                return cap
        return None

    def permits(self, capability_id: str, **request: Any) -> bool:
        cap = self.get(capability_id)
        return bool(cap and cap.permits(**request))

    # ── delegate / restrict ──────────────────────────────────────────────────
    def delegate(
        self,
        parent_id: str,
        *,
        subject: str,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        scope: Optional[str] = None,
        constraints: Optional[Iterable[str]] = None,
        ttl_seconds: Optional[float] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Capability:
        """Create a child capability from a parent, refusing any widening.

        The child's action/resource/scope/expiry must be a subset of the parent's.
        """
        parent = self.get(parent_id)
        if parent is None or not parent.active:
            raise CapabilityError("parent capability is missing or inactive")
        if not parent.revocable and parent.issuer != "system":
            raise CapabilityError("parent capability is non-delegable")
        child_action = action if action is not None else parent.action
        child_resource = resource if resource is not None else parent.resource
        child_scope = scope if scope is not None else parent.scope
        child_session = session_id if session_id is not None else parent.session_id
        child_task = task_id if task_id is not None else parent.task_id
        child_constraints = (
            tuple(constraints) if constraints is not None else parent.constraints
        )
        if not fnmatch_name(parent.action, child_action):
            raise CapabilityError("delegation would widen the action")
        if not resource_matches(parent.resource, child_resource):
            raise CapabilityError("delegation would widen the resource")
        if parent.scope and child_scope != parent.scope:
            raise CapabilityError("delegation would widen the scope")
        if parent.session_id is not None and child_session != parent.session_id:
            raise CapabilityError("delegation would widen the session")
        if parent.task_id is not None and child_task != parent.task_id:
            raise CapabilityError("delegation would widen the task")
        if not set(child_constraints).issuperset(parent.constraints):
            raise CapabilityError("delegation would drop a parent constraint")
        expiry = parent.expires_at
        if ttl_seconds is not None:
            candidate = now_ts() + float(ttl_seconds)
            if parent.expires_at is None:
                expiry = candidate
            else:
                expiry = min(parent.expires_at, candidate)
        return self._issue_child(
            child_session, child_task, expiry, child_constraints,
            subject, child_action, child_resource, child_scope, parent,
        )

    def _issue_child(
        self,
        session_id: Optional[str],
        task_id: Optional[str],
        expiry: Optional[float],
        constraints: tuple[str, ...],
        subject: str,
        action: str,
        resource: str,
        scope: str,
        parent: Capability,
    ) -> Capability:
        cap = Capability(
            id=new_id("cap"),
            subject=subject,
            action=action,
            resource=canonicalize_resource(resource) or "**",
            scope=scope,
            constraints=constraints,
            expires_at=expiry,
            session_id=session_id,
            task_id=task_id,
            tenant_id=parent.tenant_id,
            issuer=f"delegate:{parent.id}",
            revocable=parent.revocable,
            parent_id=parent.id,
            permission=parent.permission,
        )
        self._by_id[cap.id] = cap
        if self._store is not None:
            self._store.save_capability(cap.to_dict())
        return cap

    def restrict(self, capability_id: str, **narrowing: Any) -> Capability:
        """Narrow a capability in place-ish by delegating to itself (a new id).

        Kept as a distinct verb because the audit trail should say 'restricted',
        but the mechanism is the delegation subset check.
        """
        parent = self.get(capability_id)
        if parent is None:
            raise CapabilityError("capability not found")
        child = self.delegate(parent_id=capability_id, subject=parent.subject, **narrowing)
        self.revoke(capability_id)
        return child

    # ── revoke / expire ──────────────────────────────────────────────────────
    def revoke(self, capability_id: str) -> bool:
        cap = self.get(capability_id)
        if cap is None:
            return False
        cap.revoked = True
        if self._store is not None:
            self._store.save_capability(cap.to_dict())
        return True

    def revoke_all(self, *, subject: Optional[str] = None, session_id: Optional[str] = None) -> int:
        count = 0
        for cap in self._by_id.values():
            if cap.revoked:
                continue
            if subject is not None and cap.subject != subject:
                continue
            if session_id is not None and cap.session_id != session_id:
                continue
            cap.revoked = True
            if self._store is not None:
                self._store.save_capability(cap.to_dict())
            count += 1
        return count

    def expire_stale(self) -> int:
        """Mark expired capabilities revoked so the store reflects reality."""
        count = 0
        for cap in self._by_id.values():
            if not cap.revoked and cap.expired:
                cap.revoked = True
                if self._store is not None:
                    self._store.save_capability(cap.to_dict())
                count += 1
        return count

    def snapshot(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self._by_id.values()]


__all__ = ["Capability", "CapabilityEngine", "CapabilityError"]
