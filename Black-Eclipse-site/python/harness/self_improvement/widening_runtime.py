"""Runtime overlay for operator-applied read-only tool grants.

A grant is an `active` `SelfModificationAction` row of kind `widen_tool`. The
surface reads the in-process overlay, which is refreshed on boot, apply and
revoke. Expired grants are ignored immediately and expired by the executor.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Optional

from ..persistence import now_iso
from .self_modification import SelfModificationAudit
from .tool_shadow import shadow_report
from .widening_queue import WideningProposalStore

_ACTIVE: dict[str, frozenset[str]] = {}


def _expiry(days: int) -> str:
    moment = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=max(1, int(days)))
    return moment.isoformat().replace("+00:00", "Z")


def _detail(row: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(row.get("detail") or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def granted_tools(agent_id: str) -> frozenset[str]:
    return _ACTIVE.get(str(agent_id), frozenset())


def refresh(store: Any) -> dict[str, list[str]]:
    """Rebuild the overlay from durable active grants (expired ones excluded)."""
    audit = SelfModificationAudit(store)
    now = now_iso()
    grouped: dict[str, set[str]] = {}
    for row in audit.active("widen_tool"):
        expires = str(row.get("expiresAt") or "")
        if expires and expires <= now:
            continue
        agent_id = str(_detail(row).get("agentId") or "eclipse-agent")
        grouped.setdefault(agent_id, set()).add(str(row.get("subject") or ""))
    global _ACTIVE
    _ACTIVE = {agent: frozenset(tools) for agent, tools in grouped.items() if tools}
    return {agent: sorted(tools) for agent, tools in _ACTIVE.items()}


def list_grants(store: Any) -> list[dict[str, Any]]:
    rows = SelfModificationAudit(store).active("widen_tool")
    for row in rows:
        row["detail"] = _detail(row)
    return rows


def apply_proposal(
    store: Any,
    registry: Any,
    proposal_id: str,
    *,
    ttl_days: int = 7,
    agent_id: str = "eclipse-agent",
) -> dict[str, Any]:
    """Apply an APPROVED proposal as a read-only grant. Revalidates every time."""
    proposals = WideningProposalStore(store)
    proposal = proposals.find_by_id(proposal_id)
    if proposal is None:
        return {"ok": False, "reason": "proposal_not_found"}
    if proposal.get("status") != "approved_pending_application":
        return {"ok": False, "reason": "proposal_not_approved", "status": proposal.get("status")}
    tool_name = str(proposal.get("toolName") or "")
    tool = registry.get(tool_name)
    if tool is None:
        return {"ok": False, "reason": "tool_not_registered"}
    report = shadow_report(registry, granted_tools=(), blocked_tools=())
    row = next((item for item in report.get("rows") or [] if item.get("name") == tool_name), None)
    if row is None or row.get("status") != "eligible_shadow":
        return {"ok": False, "reason": "tool_no_longer_eligible", "reasons": (row or {}).get("reasons")}
    audit = SelfModificationAudit(store)
    for existing in audit.active("widen_tool"):
        if str(existing.get("subject") or "") != tool_name:
            continue
        if str(_detail(existing).get("agentId") or "eclipse-agent") == agent_id:
            return {"ok": False, "reason": "already_granted", "grantId": existing.get("id")}
    expires_at = _expiry(ttl_days)
    grant_id = audit.record(
        kind="widen_tool", subject=tool_name, evidence=proposal_id,
        expires_at=expires_at,
        detail={
            "agentId": agent_id, "proposalId": proposal_id,
            "permission": row.get("permission"), "effect": row.get("effect"),
        },
    )
    store._db.execute(
        "UPDATE WideningProposal SET status='applied' WHERE id=?", (proposal_id,),
    )
    store._db.commit()
    refresh(store)
    return {
        "ok": True, "grantId": grant_id, "toolName": tool_name,
        "agentId": agent_id, "expiresAt": expires_at,
        "proposal": proposals.find_by_id(proposal_id),
    }


def revoke_grant(store: Any, grant_id: str) -> dict[str, Any]:
    row = SelfModificationAudit(store).revoke(grant_id)
    refresh(store)
    if row is None:
        return {"ok": False, "reason": "not_found_or_not_active"}
    return {"ok": True, "grant": row}


def expire_due(store: Any) -> list[str]:
    """Expire widen grants only; skill-grant expiry is the skill executor's job."""
    audit = SelfModificationAudit(store)
    now = now_iso()
    expired: list[str] = []
    for row in audit.active("widen_tool"):
        expires = str(row.get("expiresAt") or "")
        if expires and expires <= now:
            if audit.revoke(str(row.get("id") or "")) is not None:
                expired.append(str(row.get("id") or ""))
    if expired:
        refresh(store)
    return expired


__all__ = [
    "apply_proposal", "expire_due", "granted_tools", "list_grants",
    "refresh", "revoke_grant",
]
