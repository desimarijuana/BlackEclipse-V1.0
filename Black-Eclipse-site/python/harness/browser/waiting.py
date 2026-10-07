"""Waiting operations for a BrowserSession, extracted to keep `session.py` small.

Each function takes the session and delegates to Playwright's own wait primitives,
so the session object stays a thin facade. The exceptions are the SAME structured
`BrowserTimeoutError` the rest of the browser uses.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from .errors import BrowserElementNotFoundError, BrowserTimeoutError
from .resolver import Target

_DEFAULT_WAIT_MS = 30_000.0


async def wait(session: Any, *, ms: int = 1000) -> dict[str, Any]:
    await asyncio.sleep(max(0, min(ms, 60_000)) / 1000)
    return {"waited": ms}


async def wait_for_selector(session: Any, raw_target: Any, *, state: str = "visible", timeout: Optional[float] = None) -> dict[str, Any]:
    # Build the locator WITHOUT requiring the element to already exist — the point
    # is to WAIT for it to appear/attach.
    target = Target.parse(raw_target)
    found = session.resolver._locator_for(session.page(), target)  # noqa: SLF001 - shared resolution
    if found is None:
        raise BrowserElementNotFoundError(
            f"Eclipse needs a way to find that element ({target.describe()}).",
            session_id=session.id, action="wait_for_element",
        )
    try:
        await found[0].first.wait_for(state=state, timeout=session._timeout(timeout) or _DEFAULT_WAIT_MS)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        raise BrowserTimeoutError(
            "The element Eclipse was waiting for didn't appear in time.", session_id=session.id,
            action="wait_for_element", metadata={"error": str(exc)[:200]},
        ) from exc
    return {"found": True, "state": state}


async def wait_for_text(session: Any, text: str, *, timeout: Optional[float] = None) -> dict[str, Any]:
    try:
        await session.page().get_by_text(text, exact=False).first.wait_for(timeout=session._timeout(timeout) or _DEFAULT_WAIT_MS)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        raise BrowserTimeoutError(
            "That text didn't appear on the page in time.", session_id=session.id,
            action="wait_for_text", metadata={"error": str(exc)[:200]},
        ) from exc
    return {"found": True, "text": text}


async def wait_for_url(session: Any, pattern: str, *, timeout: Optional[float] = None) -> dict[str, Any]:
    try:
        await session.page().wait_for_url(pattern, timeout=session._timeout(timeout) or _DEFAULT_WAIT_MS)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        raise BrowserTimeoutError(
            "The page didn't reach the expected address in time.", session_id=session.id,
            action="wait_for_url", metadata={"error": str(exc)[:200]},
        ) from exc
    return {"url": session.current_url()}


async def wait_for_load_state(session: Any, state: str = "load", *, timeout: Optional[float] = None) -> dict[str, Any]:
    try:
        await session.page().wait_for_load_state(state, timeout=session._timeout(timeout) or _DEFAULT_WAIT_MS)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        raise BrowserTimeoutError(
            "The page didn't finish loading in time.", session_id=session.id,
            action="wait_for_load_state", metadata={"error": str(exc)[:200]},
        ) from exc
    return {"state": state}


async def wait_for_navigation(session: Any, *, timeout: Optional[float] = None) -> dict[str, Any]:
    return await wait_for_load_state(session, "domcontentloaded", timeout=timeout)


async def wait_for_network(session: Any, *, idle_ms: int = 500, timeout: Optional[float] = None) -> dict[str, Any]:
    try:
        await session.page().wait_for_load_state("networkidle", timeout=session._timeout(timeout) or _DEFAULT_WAIT_MS)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        raise BrowserTimeoutError(
            "The page's network didn't settle in time.", session_id=session.id, action="wait_for_network",
            metadata={"error": str(exc)[:200]},
        ) from exc
    return {"idle": True}


async def wait_for_popup(session: Any, *, timeout: Optional[float] = None) -> dict[str, Any]:
    deadline = time.monotonic() + (session._timeout(timeout) or _DEFAULT_WAIT_MS) / 1000  # noqa: SLF001
    before = set(session.tabs.keys())
    while time.monotonic() < deadline:
        if set(session.tabs.keys()) - before:
            return {"opened": True, "tabId": (set(session.tabs.keys()) - before).pop()}
        await asyncio.sleep(0.1)
    raise BrowserTimeoutError("No new window opened in time.", session_id=session.id, action="wait_for_popup")


async def wait_for_download(session: Any, *, timeout: Optional[float] = None) -> dict[str, Any]:
    deadline = time.monotonic() + (session._timeout(timeout) or _DEFAULT_WAIT_MS) / 1000  # noqa: SLF001
    while time.monotonic() < deadline:
        if session._last_download is not None:  # noqa: SLF001
            return await session.finalize_download(session._last_download)  # noqa: SLF001
        await asyncio.sleep(0.1)
    raise BrowserTimeoutError("No download started in time.", session_id=session.id, action="wait_for_download")


__all__ = [
    "wait",
    "wait_for_download",
    "wait_for_load_state",
    "wait_for_navigation",
    "wait_for_network",
    "wait_for_popup",
    "wait_for_selector",
    "wait_for_text",
    "wait_for_url",
]
