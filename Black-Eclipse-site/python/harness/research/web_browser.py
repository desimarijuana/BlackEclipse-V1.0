"""Browser escalation for web research.

When normal (HTTP) extraction fails or is clearly insufficient, research
escalates to Eclipse's EXISTING Browser Automation Runtime to render the page and
extract the DOM/text. This module never implements a second browser: it resolves
the process-wide `BrowserManager` and uses it.

The escalation decision is deterministic:

    search → extract → IF insufficient → browser → extract → evidence

It escalates when the extracted text is empty/too short, when the fetch reported a
javascript-only or parse failure, or when the caller explicitly asks (dynamic
tables, pagination, expandable sections, login-free interaction).

A missing browser capability is an honest `unavailable`, never a fabrication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .web_security import get_boundary

# Extraction results shorter than this are treated as "probably insufficient".
MIN_USEFUL_CHARS = 400


@dataclass
class EscalationOutcome:
    ok: bool
    url: str
    text: str = ""
    title: Optional[str] = None
    reason: str = ""
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def needs_escalation(*, text: str, fetch_status: str = "OK", fetch_error: Optional[str] = None) -> tuple[bool, str]:
    """Deterministic decision: should this fetch escalate to a browser?"""
    stripped = (text or "").strip()
    if fetch_status != "OK":
        err = (fetch_error or "").lower()
        if "javascript" in err or "js_only" in err or "empty" in err:
            return True, "fetch reported a javascript-only / empty document"
        if "paywall" in err or "subscription" in err or "login" in err or "sign in" in err or "denied access" in err or "access denied" in err:
            return True, "fetch reported a paywall/login wall; a credentialed browser session may reach it"
        if "parse" in err or "unsupported" in err:
            return True, "fetch reported a parse/unsupported-document failure"
        return True, f"fetch did not succeed ({fetch_status})"
    if len(stripped) < MIN_USEFUL_CHARS:
        return True, f"extracted text is too short ({len(stripped)} chars)"
    return False, "extraction looks sufficient"


async def browser_extract(url: str, *, timeout_s: float = 45.0) -> EscalationOutcome:
    """Fetch a page through the existing browser runtime and return its text.

    Resolves the process-wide browser manager. When it is unavailable, returns an
    honest `ok=False` with a reason — never a fabricated page.
    """
    try:
        from ..browser.runtime import get_browser_manager
    except Exception as exc:  # noqa: BLE001 - browser subsystem optional
        return EscalationOutcome(ok=False, url=url, reason=f"browser runtime unavailable: {exc}")

    manager = get_browser_manager()
    if manager is None:
        return EscalationOutcome(ok=False, url=url, reason="browser manager not configured")

    try:
        from .web_security import assert_safe_url

        assert_safe_url(url)
    except Exception as exc:  # noqa: BLE001 - unsafe URLs never reach the browser
        return EscalationOutcome(ok=False, url=url, reason=f"url rejected by safety guard: {exc}")

    import asyncio

    session = None
    diagnostics: list[dict[str, Any]] = []
    try:
        session = await asyncio.wait_for(manager.create_session(url=url), timeout=timeout_s)
        text = ""
        title = None
        try:
            extracted = await asyncio.wait_for(session.extract(), timeout=timeout_s)
            text = str(extracted.get("text") or "")
            title = extracted.get("title")
        except Exception as exc:  # noqa: BLE001
            diagnostics.append({"step": "extract", "error": str(exc)})
        if len(text.strip()) < MIN_USEFUL_CHARS:
            try:
                dom_text = await asyncio.wait_for(session.get_dom(), timeout=timeout_s)
                if len(str(dom_text or "").strip()) > len(text.strip()):
                    text = str(dom_text)
            except Exception as exc:  # noqa: BLE001
                diagnostics.append({"step": "get_dom", "error": str(exc)})
        ok = len(text.strip()) >= MIN_USEFUL_CHARS
        return EscalationOutcome(
            ok=ok,
            url=url,
            text=text,
            title=title,
            reason="browser render succeeded" if ok else "browser render produced too little text",
            diagnostics=diagnostics,
        )
    except Exception as exc:  # noqa: BLE001 - a browser failure is a diagnostic, not a crash
        return EscalationOutcome(ok=False, url=url, reason=f"browser escalation failed: {exc}", diagnostics=diagnostics)
    finally:
        if session is not None:
            try:
                await manager.destroy_session(getattr(session, "id", session))
            except Exception:  # noqa: BLE001
                pass


def wrap_for_model(text: str, *, source: str) -> str:
    """Wrap browser-extracted text as untrusted data (same boundary as HTTP)."""
    return get_boundary().wrap(text, source=source)


__all__ = ["EscalationOutcome", "needs_escalation", "browser_extract", "wrap_for_model", "MIN_USEFUL_CHARS"]
