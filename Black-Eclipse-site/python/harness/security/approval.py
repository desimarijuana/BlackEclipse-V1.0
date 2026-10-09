"""Approval engine — the ONE broker for operator decisions.

This is a complete, self-contained approval engine over the existing single-use
approval store (`mcp.approvals.ApprovalStore`) and standing grants
(`grants.GrantStore`). It does not replace them — it gives the security gateway a
single, typed API and enforces the security rules around them:

  * an approval is bound to the exact action, resource, session and task;
  * the digest of the request must match on claim (single-use);
  * broader approval types (session/task/time) are expressed as standing grants
    that are narrow by construction — an "approve anything" is never created;
  * a timeout, a missing store, or any communication failure fails CLOSED.

The physical record remains in `McpApproval` with `kind = "security"`, so the
operator UI and every existing approval surface see it unchanged.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Any, Optional

from .models import ApprovalType, new_id, now_ts
from .permissions import canonicalize_resource

APPROVAL_KIND = "security"
GRANT_KIND = "security"


def approval_digest(
    *, action: str, resource: str, session_id: Optional[str], task_id: Optional[str],
    approval_type: str, extra: Optional[dict[str, Any]] = None,
) -> str:
    payload = {
        "action": str(action or ""),
        "resource": canonicalize_resource(resource),
        "session": str(session_id or ""),
        "task": str(task_id or ""),
        "type": str(approval_type),
        "extra": extra or {},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class ApprovalTicket:
    id: str
    kind: str
    digest: str
    status: str
    action: str
    resource: str
    approval_type: str
    session_id: Optional[str]
    task_id: Optional[str]
    expires_at: Optional[str]
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "digest": self.digest,
            "status": self.status,
            "action": self.action,
            "resource": self.resource,
            "approvalType": self.approval_type,
            "sessionId": self.session_id,
            "taskId": self.task_id,
            "expiresAt": self.expires_at,
            "summary": self.summary,
        }


class ApprovalEngine:
    """Typed approval operations over the existing single-use store."""

    def __init__(self, approvals: Any) -> None:
        self._approvals = approvals
        # The underlying single-use store shares one connection; serialize our
        # claims so concurrent authorization is safe (the guarded UPDATE is the
        # semantic guard; this lock removes the driver-level race).
        self._lock = threading.RLock()

    @property
    def available(self) -> bool:
        return self._approvals is not None

    # ── request ──────────────────────────────────────────────────────────────
    def request(
        self,
        *,
        action: str,
        resource: str = "",
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        approval_type: ApprovalType = ApprovalType.ONCE,
        risk: Optional[str] = None,
        ttl_seconds: int = 900,
        summary: Optional[str] = None,
        grant_pattern: Optional[str] = None,
    ) -> Optional[ApprovalTicket]:
        """Create (or return the existing) pending approval for this exact action.

        Returns None when no store is reachable — the caller MUST treat that as
        fail-closed (deny), never as an implicit allow.
        """
        if self._approvals is None:
            return None
        digest = approval_digest(
            action=action, resource=resource, session_id=session_id, task_id=task_id,
            approval_type=approval_type.value,
        )
        request_key = f"{action}::{canonicalize_resource(resource)}"
        with self._lock:
            record = self._approvals.request_kind(
                kind=APPROVAL_KIND,
                request_key=request_key,
                digest=digest,
                effect="external_action",
                run_id=run_id,
                workspace_id=None,
                action_summary=summary or f"Approve {action} on {resource or '(no resource)'}",
                risk=risk,
                ttl_seconds=ttl_seconds,
                grant_kind=GRANT_KIND,
                grant_pattern=grant_pattern or f"{action}:{canonicalize_resource(resource)}",
                grant_scope=str(session_id or ""),
            )
        return self._ticket(record, action, resource, approval_type, session_id, task_id, digest)

    def _ticket(
        self, record: Any, action: str, resource: str, approval_type: ApprovalType,
        session_id: Optional[str], task_id: Optional[str], digest: str,
    ) -> ApprovalTicket:
        record = record or {}
        return ApprovalTicket(
            id=str(record.get("id") or ""),
            kind=str(record.get("kind") or APPROVAL_KIND),
            digest=digest,
            status=str(record.get("status") or "pending"),
            action=action,
            resource=resource,
            approval_type=approval_type.value,
            session_id=session_id,
            task_id=task_id,
            expires_at=record.get("expiresAt"),
            summary=str(record.get("actionSummary") or ""),
        )

    # ── claim ────────────────────────────────────────────────────────────────
    def claim(
        self,
        *,
        action: str,
        resource: str = "",
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        approval_type: ApprovalType = ApprovalType.ONCE,
    ) -> Optional[ApprovalTicket]:
        """Atomically consume a matching approved approval (single-use).

        Returns None unless an approved, unexpired, exactly-matching approval was
        claimed. A standing grant short-circuits the prompt but NOT this claim:
        a grant is checked by `granted`, and grants are never created here.
        """
        if self._approvals is None:
            return None
        digest = approval_digest(
            action=action, resource=resource, session_id=session_id, task_id=task_id,
            approval_type=approval_type.value,
        )
        request_key = f"{action}::{canonicalize_resource(resource)}"
        with self._lock:
            record = self._approvals.consume_kind(
                kind=APPROVAL_KIND, request_key=request_key, digest=digest, workspace_id=None,
            )
        if record is None:
            return None
        return self._ticket(record, action, resource, approval_type, session_id, task_id, digest)

    def status(self, approval_id: str) -> Optional[dict[str, Any]]:
        if self._approvals is None:
            return None
        return self._approvals.get(approval_id)

    def decide(self, approval_id: str, *, approve: bool, decided_by: str = "operator", reason: str = "") -> Optional[dict[str, Any]]:
        if self._approvals is None:
            return None
        return self._approvals.decide(approval_id, approve=approve, decided_by=decided_by, reason=reason)

    async def wait_for_decision(self, approval_id: str, timeout_s: float = 900.0) -> Optional[dict[str, Any]]:
        if self._approvals is None:
            return None
        return await self._approvals.wait_for_decision(approval_id, timeout_s=timeout_s)

    def list_pending(self, limit: int = 100) -> list[dict[str, Any]]:
        if self._approvals is None:
            return []
        return self._approvals.list_kind(APPROVAL_KIND, status="pending", limit=limit)

    # ── grants ───────────────────────────────────────────────────────────────
    def granted(
        self, *, action: str, resource: str = "", scope: str = "",
    ) -> bool:
        """Whether a standing grant authorizes this exact action/resource.

        A grant is consulted by the gateway to decide whether an approval is
        needed at all; it is never a substitute for the claim when an approval was
        actually requested.
        """
        if self._approvals is None:
            return False
        pattern = f"{action}:{canonicalize_resource(resource)}"
        try:
            return self._approvals.grants.matches(GRANT_KIND, scope, pattern) is not None
        except Exception:  # noqa: BLE001 - a grant lookup failure never grants
            return False

    def remember(self, approval_id: str) -> Optional[dict[str, Any]]:
        if self._approvals is None:
            return None
        return self._approvals.remember_grant(approval_id)

    def stats(self) -> dict[str, Any]:
        return {"available": self.available}


__all__ = ["APPROVAL_KIND", "GRANT_KIND", "ApprovalEngine", "ApprovalTicket", "approval_digest"]
