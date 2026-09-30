"""Redirect and origin policy for remote MCP transports (Phase 6, Milestone 3).

A remote MCP endpoint may redirect. Every hop must be re-validated: a redirect
that changes origin, drops https, or lands on a private/metadata address must
abort the connection with a diagnostic. This closes the gap where the SSRF check
runs once on the configured URL but the HTTP client then follows a redirect
elsewhere (e.g. to `169.254.169.254`).

Implemented as an httpx2 response event hook: the hook fires for every response,
including each redirect hop when `follow_redirects=True`, so a bad hop raises
before its body is consumed.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from .ssrf import check_outbound_url

__all__ = ["RedirectRejected", "check_redirect", "make_redirect_hook"]


class RedirectRejected(Exception):
    """A redirect hop is not allowed."""


def _origin(url: str) -> tuple[str, str, Optional[int]]:
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return (parsed.scheme, (parsed.hostname or "").lower(), port)


def check_redirect(original: str, target: str) -> tuple[bool, Optional[str]]:
    """Validate one redirect hop from `original` to `target`.

    Refuses: a scheme/host/port change (origin change), a drop of https, and any
    target that fails the outbound-URL safety check (private/metadata/credentials).
    """
    if not target:
        return True, None
    o_scheme, o_host, o_port = _origin(original)
    t_scheme, t_host, t_port = _origin(target)
    if t_scheme != o_scheme:
        return False, f"redirect changed scheme {o_scheme}→{t_scheme}"
    if t_host != o_host or t_port != o_port:
        return False, f"redirect changed origin to {t_host}:{t_port}"
    if o_scheme == "https" and t_scheme != "https":
        return False, "redirect dropped https"
    # A same-origin hop is already covered by the pre-connect SSRF check on the
    # configured URL; only a cross-origin (already refused) target needs it.
    if (t_scheme, t_host, t_port) != (o_scheme, o_host, o_port):
        safe, reason = check_outbound_url(target)
        if not safe:
            return False, reason or "redirect target is unsafe"
    return True, None


def make_redirect_hook(original_url: str):
    """An httpx2 response hook that rejects an unsafe redirect hop.

    Async because httpx2's async client awaits its event hooks.
    """

    async def _hook(response) -> None:
        request_url = str(getattr(getattr(response, "request", None), "url", "") or "")
        response_url = str(getattr(response, "url", "") or "")
        if not response_url or response_url == request_url:
            # The same request (not a redirect hop); the configured URL was
            # already checked before connecting.
            return
        # A response whose request URL differs from the configured original can
        # be a redirect (httpx re-issues). Validate against the configured URL's
        # origin so a change is caught.
        safe, reason = check_redirect(original_url, response_url)
        if not safe:
            raise RedirectRejected(f"refused redirect from {original_url}: {reason}")

    return _hook
