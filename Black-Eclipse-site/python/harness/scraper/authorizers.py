"""The scraper lane's approval layer — one approval per DOMAIN.

A generated scraper reaches the internet, so it cannot run on the model's say-so.
The gate is deliberately COARSE and deliberately SHARP:

  * the unit of consent is the DOMAIN, not the program. The operator approves
    "collect from example.com" once; the scraper for that site may then be
    written and re-run without another question, and a DIFFERENT site asks
    again;
  * the consent is a real, revocable standing grant (the same store the
    Permissions surface lists), so it can be withdrawn like any other;
  * the approval is still the single-use, digest-bound kind every other
    effectful action uses — the operator's decision is recorded, auditable, and
    bound to the exact domain that was asked for.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlsplit

from ..code import policy
from ..mcp.approvals import _await_then_reclaim, _mark_authorized, _pause_requested, args_digest

#: The approval kind for "collect from this site".
SCRAPER_APPROVAL_KIND = "scraper_domain"


def domain_of(url: str) -> str:
    """The host a URL points at (lower-cased, port dropped). Empty when unusable."""
    text = str(url or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    host = (parsed.hostname or "").strip().lower()
    return host


def make_scraper_authorizer(
    approvals: Optional[Any], run_id: str, workspace_id: str = "",
    emitter: Any = None, inner: Any = None,
):
    """Compose the scraper admission + per-domain approval layer over `inner`."""

    scope = str(workspace_id or "")

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name not in policy.SCRAPER_TOOLS:
            if inner is not None:
                return bool(await inner(tool, args, ctx))
            return False
        if approvals is None:
            return False
        domain = domain_of(str((args or {}).get("target_url") or ""))
        if not domain:
            return False
        digest = args_digest({"domain": domain})
        if ctx is not None and getattr(ctx, "effect_authorized_digest", None) == digest:
            return True

        # A remembered consent for this site: no second question.
        grants = getattr(approvals, "grants", None)
        if grants is not None and grants.matches(SCRAPER_APPROVAL_KIND, scope, domain) is not None:
            _mark_authorized(ctx, digest)
            if emitter is not None:
                await emitter.emit("scraper.domain.approved", {
                    "tool": name, "domain": domain, "grant": True,
                })
            return True

        # An operator decision that has not been spent yet.
        claimed = approvals.consume_kind(
            kind=SCRAPER_APPROVAL_KIND, request_key=domain, digest=digest,
        )
        if claimed is not None:
            _remember_domain(approvals, scope, domain)
            _mark_authorized(ctx, digest)
            if emitter is not None:
                await emitter.emit("scraper.domain.approved", {
                    "tool": name, "domain": domain,
                    "approvalId": claimed.get("id"), "singleUse": True,
                })
            return True

        pending = None
        try:
            pending = approvals.request_kind(
                kind=SCRAPER_APPROVAL_KIND, request_key=domain, digest=digest,
                effect="write",
                run_id=run_id, workspace_id=workspace_id or None,
                action_summary=f"Collect data from {domain}",
                risk="medium",
                grant_kind=SCRAPER_APPROVAL_KIND, grant_pattern=domain, grant_scope=scope,
            )
            if emitter is not None:
                await emitter.emit("approval.requested", {
                    "approvalId": (pending or {}).get("id"),
                    "kind": SCRAPER_APPROVAL_KIND,
                    "title": f"Collect data from {domain}",
                    "summary": (
                        f"Eclipse wants to collect data from {domain}. "
                        "Approve once and it may scrape that site from then on."
                    ),
                    "effect": "write", "risk": "medium", "tool": name,
                    "domain": domain,
                    "grantPattern": domain,
                    "grantLabel": f"Always allow collecting from {domain}",
                })
        except Exception:  # noqa: BLE001 - a store failure must never authorize
            pending = None

        if pending is not None and ctx is not None and _pause_requested(ctx):
            await _await_then_reclaim(
                approvals, pending.get("id"),
                lambda: approvals.consume_kind(
                    kind=SCRAPER_APPROVAL_KIND, request_key=domain, digest=digest,
                ),
                emitter, ctx, digest, {"tool": name, "domain": domain},
                event_type="scraper.domain.approved",
            )
            if ctx is not None and getattr(ctx, "effect_authorized_digest", None) == digest:
                _remember_domain(approvals, scope, domain)
                return True
        return False

    return authorize


def _remember_domain(approvals: Any, scope: str, domain: str) -> None:
    """Remember the consent for this domain so the next scrape does not ask."""
    grants = getattr(approvals, "grants", None)
    if grants is None:
        return
    try:
        grants.add(
            kind=SCRAPER_APPROVAL_KIND, pattern=domain, scope=scope,
            label=f"Collect from {domain}", risk="medium",
            source=SCRAPER_APPROVAL_KIND, created_by="operator",
        )
    except Exception:  # noqa: BLE001 - a grant failure must never authorize
        pass


__all__ = ["SCRAPER_APPROVAL_KIND", "domain_of", "make_scraper_authorizer"]
