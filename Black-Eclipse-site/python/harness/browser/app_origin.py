"""App-origin resolution + navigation error classification (QA Round 1, Q4a/b).

The app runs behind ONE canonical origin (`BE_CANONICAL_HOST`) served by the
local proxy, while the runtime itself knows `HARNESS_CALLBACK_URL` (loopback).
A Playwright page navigation can therefore land on an origin that is not
reachable from that browser context, and the old error text hid the reason
("Eclipse couldn't open <url>"). This module:

  * classifies the transport failure into a plain cause;
  * probes the known app origins and returns the first REACHABLE one, with the
    full probe list for an honest refusal;
  * rewrites an app URL onto a reachable origin while preserving path/query.

It never fetches a non-app host and never follows a redirect: this is local
diagnosis, not a general HTTP client.
"""

from __future__ import annotations

import os
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

PROBE_TIMEOUT_S = 1.5


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def classify_navigation_error(exc: BaseException) -> tuple[str, str]:
    """Map a Playwright transport error to (short cause, plain next hint)."""
    raw = str(exc)
    low = raw.lower()
    if "err_name_not_resolved" in low or "name or service not known" in low or "getaddrinfo" in low:
        return (
            "the host name could not be resolved",
            "the local alias host may not be set up on this machine",
        )
    if "err_connection_refused" in low or "connection refused" in low:
        return (
            "the connection was refused",
            "nothing is listening at that address — is the app running?",
        )
    if "err_timed_out" in low or "timed out" in low or "timeout" in low:
        return ("the page timed out", "the app did not respond in time")
    if "err_too_many_redirects" in low or "redirect" in low:
        return ("the redirect could not be followed", "the app may be looping between origins")
    if "err_aborted" in low or "aborted" in low:
        return ("the navigation was aborted", "the page load was interrupted")
    return ("the browser could not reach the page", "check that the app is running")


def app_origins() -> list[str]:
    """Known app origins, most specific first, de-duplicated."""
    candidates: list[str] = []
    explicit = (os.environ.get("HARNESS_BROWSER_APP_ORIGIN") or "").strip()
    if explicit:
        candidates.append(explicit.rstrip("/"))
    callback = (os.environ.get("HARNESS_CALLBACK_URL") or "http://127.0.0.1:3000").strip()
    if callback:
        candidates.append(callback.rstrip("/"))
    canonical = (os.environ.get("BE_CANONICAL_HOST") or "").strip()
    if canonical:
        host = canonical.split("://")[-1].rstrip("/")
        candidates.extend([f"https://{host}", f"http://{host}"])
    seen: set[str] = set()
    out: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def is_app_url(url: str) -> bool:
    """True when the URL targets the app's own loopback or canonical origin."""
    host = _host(url)
    if not host:
        return False
    if host in {"127.0.0.1", "localhost", "::1"}:
        return True
    return any(host == _host(origin) for origin in app_origins() if _host(origin))


def probe_origin(origin: str, timeout: float = PROBE_TIMEOUT_S) -> bool:
    """A bounded GET / probe. Any HTTP answer below 500 counts as reachable."""
    try:
        request = Request(  # noqa: S310 - caller-controlled app origin only
            f"{origin.rstrip('/')}/",
            method="GET",
            headers={"Accept": "*/*", "User-Agent": "eclipse-browser-probe"},
        )
        with build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            return int(getattr(response, "status", 200) or 200) < 500
    except Exception:  # noqa: BLE001 - a probe failure is just "not reachable"
        return False


def resolve_app_origin(preferred: Optional[str] = None) -> tuple[Optional[str], list[dict[str, Any]]]:
    """Return the first reachable app origin plus the probe trail."""
    tried: list[dict[str, Any]] = []
    seen: set[str] = set()
    ordered = ([preferred.rstrip("/")] if preferred else []) + app_origins()
    for origin in ordered:
        if not origin or origin in seen:
            continue
        seen.add(origin)
        reachable = probe_origin(origin)
        tried.append({"origin": origin, "reachable": reachable})
        if reachable:
            return origin, tried
    return None, tried


def retarget(url: str, origin: str) -> str:
    """Move an app URL onto a different app origin, preserving path/query."""
    parts = urlsplit(url)
    target = urlsplit(origin)
    return urlunsplit((target.scheme, target.netloc, parts.path or "/", parts.query, parts.fragment))
