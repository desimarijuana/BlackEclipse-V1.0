"""Session isolation — one SecurityContext per session, never shared.

The registry owns the lifecycle of `SecurityContext`s and enforces the isolation
invariants: a capability, secret grant, approval and workspace are looked up
within the context of the session making the request. A request that presents a
session id different from the context it is running in is refused before it ever
reaches policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .models import Actor, Environment, SecurityContext


@dataclass
class IsolationViolation(Exception):
    reason: str
    field: str = "session"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"session isolation violation ({self.field}): {self.reason}"


class SessionRegistry:
    """Create, look up and close session security contexts."""

    def __init__(self) -> None:
        self._contexts: dict[str, SecurityContext] = {}
        self._violations: int = 0

    def create(
        self,
        *,
        session_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        environment: Any = Environment.DEVELOPMENT,
        actor: Optional[Actor] = None,
    ) -> SecurityContext:
        context = SecurityContext(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            task_id=task_id,
            workspace_id=workspace_id,
            environment=Environment.parse(environment),
            actor=actor or Actor(id=agent_id or user_id or "local", tenant_id=tenant_id),
        )
        if session_id:
            context.session_id = str(session_id)
        self._contexts[context.session_id] = context
        return context

    def get(self, session_id: str) -> Optional[SecurityContext]:
        return self._contexts.get(str(session_id))

    def get_or_create(self, session_id: str, **kwargs: Any) -> SecurityContext:
        return self.get(session_id) or self.create(session_id=session_id, **kwargs)

    def close(self, session_id: str) -> bool:
        context = self._contexts.get(str(session_id))
        if context is None:
            return False
        context.closed = True
        return True

    def cleanup(self, session_id: str) -> None:
        """Drop a closed context from memory (capabilities/secrets are revoked by
        the gateway before this is called)."""
        self._contexts.pop(str(session_id), None)

    def assert_session(self, context: SecurityContext, presented: Optional[str]) -> None:
        """Refuse a request whose presented session differs from the context's."""
        if context.closed:
            self._violations += 1
            raise IsolationViolation("session is closed", "session")
        if presented and str(presented) != context.session_id:
            self._violations += 1
            raise IsolationViolation(
                f"request named session {presented!r} but is running in {context.session_id!r}",
                "session",
            )

    def assert_workspace(self, context: SecurityContext, workspace: Optional[str]) -> None:
        """Refuse cross-workspace access unless the context has no binding."""
        if context.workspace_id and workspace and str(workspace) != context.workspace_id:
            self._violations += 1
            raise IsolationViolation(
                f"request named workspace {workspace!r} but is bound to {context.workspace_id!r}",
                "workspace",
            )

    def assert_tenant(self, context: SecurityContext, presented: Optional[str]) -> None:
        """Refuse a request whose tenant differs from the context's tenant.

        When multi-tenant mode is on, a context with no tenant is also refused —
        an unbound session must never act on behalf of any tenant.
        """
        from .identity import multi_tenant_required  # noqa: PLC0415

        if context.tenant_id and presented and str(presented) != context.tenant_id:
            self._violations += 1
            raise IsolationViolation(
                f"request named tenant {presented!r} but the session is bound to {context.tenant_id!r}",
                "tenant",
            )
        if multi_tenant_required() and not context.tenant_id:
            self._violations += 1
            raise IsolationViolation("multi-tenant mode requires a tenant-bound session", "tenant")

    def active(self) -> int:
        return sum(1 for c in self._contexts.values() if not c.closed)

    def violations(self) -> int:
        return self._violations


__all__ = ["IsolationViolation", "SessionRegistry"]
