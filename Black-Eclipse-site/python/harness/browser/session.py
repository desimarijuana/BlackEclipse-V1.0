"""One BrowserSession — the first-class browser object.

Tracks identity (session_id, agent_id, task_id, profile_id, provider, backend,
browser_type, context_id, tabs, active_tab, timestamps, status, permissions) and
owns the deterministic lifecycle (create → ready → busy → paused → … → terminated)
plus every operation the tools and `browser_exec` expose.

A session holds the ONLY reference to a Playwright object in the system
(`ProviderSession`). It re-resolves stale elements, records console/network/errors
and dialogs, and tracks downloads. It never fabricates: every failure is a
structured `BrowserError`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ..persistence import now_iso
from .errors import (
    BrowserDialogError,
    BrowserDownloadError,
    BrowserElementNotFoundError,
    BrowserHumanInterventionRequired,
    BrowserNavigationError,
    BrowserPermissionError,
    BrowserSessionError,
    BrowserTimeoutError,
    BrowserUploadError,
)
from .observation import SnapshotEngine
from .policy import BrowserPolicy
from .resolver import Resolver, Target
from .trace import BrowserTrace
from .verification import Verifier
from .vision import VisionEngine

# Bounds — every one a truncation/refusal, never a silent partial.
MAX_CONSOLE_ENTRIES = 500
MAX_NETWORK_ENTRIES = 1_000
MAX_ERROR_ENTRIES = 200
MAX_LINKS = 500
MAX_FORMS = 100
MAX_IMAGES = 500
MAX_DOM_CHARS = 200_000


class SessionState(str, Enum):
    CREATING = "CREATING"
    READY = "READY"
    NAVIGATING = "NAVIGATING"
    ACTING = "ACTING"
    OBSERVING = "OBSERVING"
    BUSY = "BUSY"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    DISCONNECTED = "DISCONNECTED"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"

    @property
    def terminal(self) -> bool:
        return self in (SessionState.FAILED, SessionState.DISCONNECTED, SessionState.TERMINATED)


# Allowed transitions. An invalid transition is refused, never silently applied.
_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.CREATING: {SessionState.READY, SessionState.FAILED, SessionState.TERMINATING},
    SessionState.READY: {
        SessionState.NAVIGATING, SessionState.ACTING, SessionState.OBSERVING,
        SessionState.BUSY, SessionState.PAUSED, SessionState.HUMAN_REQUIRED,
        SessionState.TERMINATING, SessionState.FAILED, SessionState.DISCONNECTED,
    },
    SessionState.NAVIGATING: {SessionState.READY, SessionState.FAILED, SessionState.HUMAN_REQUIRED, SessionState.TERMINATING},
    SessionState.ACTING: {SessionState.READY, SessionState.FAILED, SessionState.HUMAN_REQUIRED, SessionState.TERMINATING},
    SessionState.OBSERVING: {SessionState.READY, SessionState.FAILED, SessionState.TERMINATING},
    SessionState.BUSY: {SessionState.READY, SessionState.FAILED, SessionState.TERMINATING},
    SessionState.PAUSED: {SessionState.READY, SessionState.HUMAN_REQUIRED, SessionState.TERMINATING, SessionState.FAILED},
    SessionState.HUMAN_REQUIRED: {SessionState.READY, SessionState.PAUSED, SessionState.TERMINATING, SessionState.FAILED},
    SessionState.FAILED: {SessionState.TERMINATING},
    SessionState.DISCONNECTED: {SessionState.TERMINATING, SessionState.READY},
    SessionState.TERMINATING: {SessionState.TERMINATED},
    SessionState.TERMINATED: set(),
}


@dataclass
class TabInfo:
    id: str
    page: Any
    url: str = ""
    title: str = ""
    created_at: float = field(default_factory=time.time)
    opener_id: Optional[str] = None

    def to_dict(self, active_id: Optional[str] = None) -> dict[str, Any]:
        return {
            "id": self.id, "url": self.url, "title": self.title,
            "active": self.id == active_id, "openerId": self.opener_id,
        }


class BrowserSession:
    """A live, isolated browser session."""

    def __init__(
        self,
        *,
        session_id: str,
        provider: Any,
        provider_session: Any,
        config: Any,
        policy: BrowserPolicy,
        store: Any = None,
        trace: Optional[BrowserTrace] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> None:
        self.id = session_id
        self.provider = provider
        self._ps = provider_session
        self._config = config
        self.policy = policy
        self.store = store
        self.trace = trace
        self.agent_id = agent_id
        self.task_id = task_id
        self.run_id = run_id
        self.profile_id = profile_id
        self.state = SessionState.CREATING
        self.created_at = time.time()
        self.last_activity = time.time()
        self.backend = getattr(provider_session, "backend", "playwright")
        self.browser_type = config.browser_type
        self.permissions_granted: list[str] = []

        # The observation/resolution/verification stack for THIS session.
        self.snapshots = SnapshotEngine(
            session_id=session_id, snapshots_dir=config.snapshots_dir, max_chars=config.snapshot_max_chars,
        )
        self.vision = VisionEngine(session_id=session_id, screenshots_dir=config.screenshots_dir)
        self.resolver = Resolver(self.snapshots)
        self.verifier = Verifier()

        self.tabs: dict[str, TabInfo] = {}
        self._tab_counter = 0
        self.active_tab: Optional[str] = None

        self.console: list[dict[str, Any]] = []
        self.network: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.pending_dialog: Optional[Any] = None
        self.pending_dialog_info: Optional[dict[str, Any]] = None
        self.downloads: list[dict[str, Any]] = []
        self._last_download: Optional[dict[str, Any]] = None

        self._attach_existing_pages()

    # ── state machine ────────────────────────────────────────────────────────

    def _transition(self, target: SessionState) -> None:
        if target == self.state:
            return
        allowed = _TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise BrowserSessionError(
                f"Eclipse's browser can't go from {self.state.value} to {target.value}.",
                session_id=self.id, provider=self.provider.id,
            )
        self.state = target
        self._persist()

    def _persist(self) -> None:
        if self.store is None:
            return
        try:
            self.store.save_session({
                "id": self.id, "agentId": self.agent_id, "taskId": self.task_id,
                "runId": self.run_id, "profileId": self.profile_id,
                "provider": self.provider.id, "backend": self.backend,
                "browserType": self.browser_type, "contextId": self.id,
                "status": self.state.value, "state": self.state.value,
                "createdAt": _iso(self.created_at), "lastActivity": now_iso(),
                "terminatedAt": now_iso() if self.state.terminal else None,
                "tabCount": len(self.tabs),
                "metadata": {"url": self.current_url(), "title": self.current_title()},
            })
        except Exception:  # noqa: BLE001 - persistence must never break a session
            pass

    def touch(self) -> None:
        self.last_activity = time.time()

    def health_check(self) -> dict[str, Any]:
        alive = True
        reason = None
        try:
            if self._ps.closed:
                alive = False
                reason = "the browser was closed"
            elif self._ps.context is not None:
                _ = self._ps.context.pages
        except Exception as exc:  # noqa: BLE001
            alive = False
            reason = str(exc)[:200]
        return {
            "sessionId": self.id, "state": self.state.value, "alive": alive,
            "reason": reason, "tabCount": len(self.tabs), "provider": self.provider.id,
        }

    # ── tabs & pages ─────────────────────────────────────────────────────────

    def _attach_existing_pages(self) -> None:
        for page in list(getattr(self._ps, "pages", []) or []):
            self._register_page(page)

    def _register_page(self, page: Any, *, opener_id: Optional[str] = None) -> str:
        self._tab_counter += 1
        tab_id = f"tab{self._tab_counter}"
        info = TabInfo(id=tab_id, page=page, opener_id=opener_id)
        self.tabs[tab_id] = info
        if self.active_tab is None:
            self.active_tab = tab_id
        self._attach_listeners(page, tab_id)
        try:
            info.url = page.url
        except Exception:  # noqa: BLE001
            pass
        return tab_id

    def _attach_listeners(self, page: Any, tab_id: str) -> None:
        try:
            page.on("console", lambda msg: self._on_console(msg, tab_id))
            page.on("pageerror", lambda exc: self._on_pageerror(exc, tab_id))
            page.on("dialog", lambda dialog: self._on_dialog(dialog, tab_id))
            page.on("download", lambda download: self._on_download(download, tab_id))
            page.on("request", lambda request: self._on_request(request, tab_id))
            page.on("response", lambda response: self._on_response(response, tab_id))
            page.on("requestfailed", lambda request: self._on_request_failed(request, tab_id))
            page.on("popup", lambda popup: self._on_popup(popup, tab_id))
            page.on("close", lambda: self._on_page_close(tab_id))
        except Exception:  # noqa: BLE001 - a listener failure must not break the page
            pass

    def _on_console(self, msg: Any, tab_id: str) -> None:
        try:
            self.console.append({
                "type": getattr(msg, "type", "log"), "text": (msg.text or "")[:2000],
                "location": getattr(msg, "location", {}), "tabId": tab_id, "at": now_iso(),
            })
            if len(self.console) > MAX_CONSOLE_ENTRIES:
                del self.console[0]
        except Exception:  # noqa: BLE001
            pass

    def _on_pageerror(self, exc: Any, tab_id: str) -> None:
        try:
            self.errors.append({"kind": "pageerror", "message": str(exc)[:2000], "tabId": tab_id, "at": now_iso()})
            if len(self.errors) > MAX_ERROR_ENTRIES:
                del self.errors[0]
        except Exception:  # noqa: BLE001
            pass

    def _on_dialog(self, dialog: Any, tab_id: str) -> None:
        # Store the dialog and do NOT auto-handle: `browser_dialog` decides. The
        # page's own JS blocks until the dialog is handled, which is the honest
        # browser behaviour the agent should observe.
        self.pending_dialog = dialog
        self.pending_dialog_info = {
            "type": getattr(dialog, "type", "alert"),
            "message": getattr(dialog, "message", ""),
            "defaultValue": getattr(dialog, "default_value", ""),
            "tabId": tab_id, "at": now_iso(),
        }
        self.trace and self.trace  # no-op; the tool records the resolution

    def _on_download(self, download: Any, tab_id: str) -> None:
        import uuid  # noqa: PLC0415

        record = {
            "id": uuid.uuid4().hex, "sessionId": self.id,
            "filename": download.suggested_filename, "sourceUrl": getattr(download, "url", ""),
            "mimeType": None, "size": None, "path": None,
            "startedAt": now_iso(), "completedAt": None, "checksum": None, "status": "started",
            "tabId": tab_id, "download": download,
        }
        self.downloads.append(record)
        self._last_download = record

    def _on_request(self, request: Any, tab_id: str) -> None:
        try:
            self.network.append({
                "kind": "request", "method": request.method, "url": request.url,
                "resourceType": getattr(request, "resource_type", ""), "tabId": tab_id,
                "at": now_iso(),
            })
            if len(self.network) > MAX_NETWORK_ENTRIES:
                del self.network[0]
        except Exception:  # noqa: BLE001
            pass

    def _on_response(self, response: Any, tab_id: str) -> None:
        try:
            self.network.append({
                "kind": "response", "status": response.status, "url": response.url,
                "resourceType": getattr(response.request, "resource_type", ""),
                "tabId": tab_id, "at": now_iso(),
            })
            if len(self.network) > MAX_NETWORK_ENTRIES:
                del self.network[0]
        except Exception:  # noqa: BLE001
            pass

    def _on_request_failed(self, request: Any, tab_id: str) -> None:
        try:
            failure = getattr(request, "failure", None)
            self.network.append({
                "kind": "failed", "url": request.url, "method": request.method,
                "error": failure if isinstance(failure, str) else str(failure),
                "tabId": tab_id, "at": now_iso(),
            })
        except Exception:  # noqa: BLE001
            pass

    def _on_popup(self, popup: Any, tab_id: str) -> None:
        try:
            new_id = self._register_page(popup, opener_id=tab_id)
            self.active_tab = new_id
        except Exception:  # noqa: BLE001
            pass

    def _on_page_close(self, tab_id: str) -> None:
        self.tabs.pop(tab_id, None)
        if self.active_tab == tab_id:
            self.active_tab = next(iter(self.tabs), None)

    @property
    def ps_context(self) -> Any:
        """The provider session's Playwright context (device/UA/locale config)."""
        return self._ps.context

    def page(self) -> Any:
        """The active page (opens one if the session has none)."""
        if self.active_tab and self.active_tab in self.tabs:
            return self.tabs[self.active_tab].page
        if self.tabs:
            self.active_tab = next(iter(self.tabs))
            return self.tabs[self.active_tab].page
        raise BrowserSessionError(
            "Eclipse's browser has no open page.", session_id=self.id, provider=self.provider.id,
        )

    def current_url(self) -> str:
        try:
            return self.page().url
        except Exception:  # noqa: BLE001
            return ""

    def current_title(self) -> str:
        try:
            info = self.tabs.get(self.active_tab or "")
            return info.title if info else ""
        except Exception:  # noqa: BLE001
            return ""

    def tabs_list(self) -> list[dict[str, Any]]:
        for tab_id, info in self.tabs.items():
            try:
                info.url = info.page.url
            except Exception:  # noqa: BLE001
                pass
        return [info.to_dict(self.active_tab) for info in self.tabs.values()]

    async def new_tab(self, url: Optional[str] = None) -> dict[str, Any]:
        context = self._ps.context
        page = await context.new_page()
        tab_id = self._register_page(page)
        self.active_tab = tab_id
        if url:
            await page.goto(url, wait_until="domcontentloaded", timeout=self._timeout())
        self._persist()
        return {"id": tab_id, "url": page.url}

    async def switch_tab(self, tab_id: str) -> dict[str, Any]:
        if tab_id not in self.tabs:
            raise BrowserSessionError(
                f"There's no browser tab {tab_id!r}.", session_id=self.id, action="switch_tab",
            )
        self.active_tab = tab_id
        try:
            await self.tabs[tab_id].page.bring_to_front()
        except Exception:  # noqa: BLE001
            pass
        return {"activeTab": tab_id}

    async def close_tab(self, tab_id: Optional[str] = None) -> dict[str, Any]:
        target = tab_id or self.active_tab
        info = self.tabs.get(target or "")
        if info is None:
            raise BrowserSessionError("There's no such tab to close.", session_id=self.id)
        try:
            await info.page.close()
        finally:
            self._on_page_close(str(target))
        return {"closed": target, "activeTab": self.active_tab}

    # ── navigation ───────────────────────────────────────────────────────────

    def _timeout(self, override: Optional[float] = None) -> float:
        if override:
            return float(override)
        return 30_000.0

    async def navigate(self, url: str, *, wait_until: str = "domcontentloaded", timeout: Optional[float] = None) -> dict[str, Any]:
        self._transition(SessionState.NAVIGATING)
        page = self.page()
        try:
            response = await page.goto(url, wait_until=wait_until or "domcontentloaded", timeout=self._timeout(timeout))
        except Exception as exc:  # noqa: BLE001
            self._transition(SessionState.READY)
            raise BrowserNavigationError(
                f"Eclipse couldn't open {url}.",
                session_id=self.id, provider=self.provider.id, action="navigate",
                retryable=True, metadata={"error": str(exc)[:300]},
            ) from exc
        self._transition(SessionState.READY)
        self.touch()
        return {
            "url": page.url,
            "status": response.status if response else None,
            "title": await self._safe_title(page),
        }

    async def go_back(self, *, timeout: Optional[float] = None) -> dict[str, Any]:
        page = self.page()
        try:
            await page.go_back(wait_until="domcontentloaded", timeout=self._timeout(timeout))
        except Exception as exc:  # noqa: BLE001
            raise BrowserNavigationError("Eclipse couldn't go back a page.", session_id=self.id, retryable=True, metadata={"error": str(exc)[:200]}) from exc
        return {"url": page.url}

    async def go_forward(self, *, timeout: Optional[float] = None) -> dict[str, Any]:
        page = self.page()
        try:
            await page.go_forward(wait_until="domcontentloaded", timeout=self._timeout(timeout))
        except Exception as exc:  # noqa: BLE001
            raise BrowserNavigationError("Eclipse couldn't go forward a page.", session_id=self.id, retryable=True, metadata={"error": str(exc)[:200]}) from exc
        return {"url": page.url}

    async def reload(self, *, timeout: Optional[float] = None) -> dict[str, Any]:
        page = self.page()
        try:
            await page.reload(wait_until="domcontentloaded", timeout=self._timeout(timeout))
        except Exception as exc:  # noqa: BLE001
            raise BrowserNavigationError("Eclipse couldn't refresh the page.", session_id=self.id, retryable=True, metadata={"error": str(exc)[:200]}) from exc
        return {"url": page.url}

    async def stop(self) -> dict[str, Any]:
        try:
            await self.page().evaluate("window.stop()")
        except Exception:  # noqa: BLE001
            pass
        return {"stopped": True, "url": self.current_url()}

    async def _safe_title(self, page: Any) -> str:
        try:
            return await page.title()
        except Exception:  # noqa: BLE001
            return ""

    # ── observation ──────────────────────────────────────────────────────────

    async def snapshot(self, *, persist: bool = True) -> Any:
        self._transition(SessionState.OBSERVING)
        result = await self.snapshots.build(self.page(), persist_on_truncate=persist)
        self._transition(SessionState.READY)
        self.touch()
        return result

    async def extract(self) -> dict[str, Any]:
        """Structured page extraction: title, url, headings, links, forms, text."""
        page = self.page()
        data: dict[str, Any] = {"url": page.url, "title": await self._safe_title(page)}
        try:
            data["headings"] = await page.evaluate(
                "() => Array.from(document.querySelectorAll('h1,h2,h3,h4')).slice(0,50)"
                ".map(h => ({level: h.tagName.toLowerCase(), text: (h.innerText||'').trim().slice(0,200)}))"
            )
            data["text"] = (await page.evaluate("() => (document.body && document.body.innerText) || ''"))[:20_000]
        except Exception:  # noqa: BLE001
            data["headings"] = []
            data["text"] = ""
        return data

    async def get_text(self) -> str:
        try:
            return (await self.page().evaluate("() => (document.body && document.body.innerText) || ''"))[:50_000]
        except Exception:  # noqa: BLE001
            return ""

    async def get_links(self) -> list[dict[str, str]]:
        try:
            return await self.page().evaluate(
                "() => Array.from(document.querySelectorAll('a[href]')).slice(0,%d)"
                ".map(a => ({text: (a.innerText||'').trim().slice(0,200), href: a.href}))" % MAX_LINKS
            )
        except Exception:  # noqa: BLE001
            return []

    async def get_images(self) -> list[dict[str, str]]:
        try:
            return await self.page().evaluate(
                "() => Array.from(document.querySelectorAll('img')).slice(0,%d)"
                ".map(i => ({src: i.currentSrc||i.src, alt: i.alt||''}))" % MAX_IMAGES
            )
        except Exception:  # noqa: BLE001
            return []

    async def get_forms(self) -> list[dict[str, Any]]:
        try:
            return await self.page().evaluate(
                "() => Array.from(document.querySelectorAll('form')).slice(0,%d).map(f => ({"
                "  action: f.action||'', method: (f.method||'get').toLowerCase(),"
                "  fields: Array.from(f.querySelectorAll('input,select,textarea')).slice(0,50).map(el => ({"
                "    name: el.name||'', type: el.type||el.tagName.toLowerCase(),"
                "    label: (el.labels && el.labels[0] && el.labels[0].innerText) || el.placeholder || ''}))"
                "}))" % MAX_FORMS
            )
        except Exception:  # noqa: BLE001
            return []

    async def get_dom(self, *, selector: Optional[str] = None) -> str:
        page = self.page()
        try:
            if selector:
                html = await page.evaluate(
                    "(sel) => { const el = document.querySelector(sel); return el ? el.outerHTML : ''; }", selector
                )
            else:
                html = await page.content()
        except Exception:  # noqa: BLE001
            return ""
        return str(html)[:MAX_DOM_CHARS]

    async def get_accessibility_tree(self) -> str:
        try:
            return await self.page().locator("body").aria_snapshot()
        except Exception:  # noqa: BLE001
            return ""

    async def find(self, raw_target: Any, *, max_results: int = 20) -> list[dict[str, Any]]:
        """Find elements matching a locator and describe them (no interaction)."""
        from . import inspection  # noqa: PLC0415

        return await inspection.find(self, raw_target, max_results=max_results)

    async def highlight(self, raw_target: Any) -> dict[str, Any]:
        """Briefly outline an element (a transient visual aid), without clicking."""
        from . import inspection  # noqa: PLC0415

        return await inspection.highlight(self, raw_target)

    async def screenshot(self, *, full_page: bool = False) -> str:
        return await self.vision.screenshot(self.page(), full_page=full_page)

    async def visual_map(self, *, screenshot: Optional[str] = None) -> Any:
        return await self.vision.visual_map(self.page(), self.snapshots, screenshot=screenshot)

    async def visual_locate(self, text: str, *, query: Optional[str] = None, model_settings: Any = None) -> dict[str, Any]:
        """Locate a target by fusing the DOM locator with a visual match."""
        from .vision import locate  # noqa: PLC0415

        return await locate(self, text, query=query, model_settings=model_settings)

    # ── resolution helpers ───────────────────────────────────────────────────

    async def resolve(self, raw_target: Any) -> Any:
        target = Target.parse(raw_target)
        page = self.page()

        async def refresh() -> Any:
            return await self.snapshot(persist=False)

        return await self.resolver.resolve_verified(page, target, refresh_snapshot=refresh)

    async def _scroll_into_view(self, locator: Any) -> None:
        try:
            await locator.scroll_into_view_if_needed(timeout=3_000)
        except Exception:  # noqa: BLE001
            pass

    # ── interaction (action → observe → verify) ──────────────────────────────

    async def click(
        self, raw_target: Any, *, expect: Optional[dict[str, Any]] = None,
        button: str = "left", click_count: int = 1, timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        self._transition(SessionState.ACTING)
        before = await self.verifier.capture(self.page(), self.snapshots, dialog_pending=self.pending_dialog is not None)
        try:
            resolution = await self.resolve(raw_target)
            locator = resolution.locator.first
            await self._scroll_into_view(locator)
            # A plain click. A download triggered by the click is captured by the
            # page's `download` listener (`browser_wait_for_download` finalizes it);
            # wrapping every click in `expect_download` would add a fixed delay.
            await locator.click(button=button, click_count=click_count, timeout=self._timeout(timeout))
        except BrowserElementNotFoundError:
            self._transition(SessionState.READY)
            raise
        except Exception as exc:  # noqa: BLE001
            self._transition(SessionState.READY)
            raise BrowserSessionError(
                "Eclipse couldn't click that element.", session_id=self.id,
                action="click", retryable=True, metadata={"error": str(exc)[:300]},
            ) from exc
        self._maybe_detect_challenge()
        verification = await self.verifier.verify(
            self.page(), before, action="click", expect=expect, snapshot_engine=self.snapshots,
            dialog_pending=self.pending_dialog is not None,
        )
        self._transition(SessionState.READY)
        self.touch()
        return {
            "success": True, "action": "click", "url": self.current_url(),
            "resolution": resolution.to_dict(), "verification": verification.to_dict(),
            "state_changed": verification.state_changed,
        }

    async def type_text(
        self, raw_target: Any, text: str, *, submit: bool = False,
        clear: bool = True, expect: Optional[dict[str, Any]] = None, timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        self._transition(SessionState.ACTING)
        before = await self.verifier.capture(self.page(), self.snapshots, dialog_pending=self.pending_dialog is not None)
        try:
            resolution = await self.resolve(raw_target)
            locator = resolution.locator.first
            await self._scroll_into_view(locator)
            if clear:
                try:
                    await locator.fill("", timeout=self._timeout(timeout))
                except Exception:  # noqa: BLE001
                    pass
            await locator.type(text, timeout=self._timeout(timeout))
            if submit:
                await locator.press("Enter", timeout=self._timeout(timeout))
                try:
                    await self.page().wait_for_load_state("domcontentloaded", timeout=5_000)
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            self._transition(SessionState.READY)
            if isinstance(exc, (BrowserElementNotFoundError,)):
                raise
            raise BrowserSessionError(
                "Eclipse couldn't type into that element.", session_id=self.id,
                action="type", retryable=True, metadata={"error": str(exc)[:300]},
            ) from exc
        self._maybe_detect_challenge()
        verification = await self.verifier.verify(
            self.page(), before, action="type", expect=expect, snapshot_engine=self.snapshots,
            dialog_pending=self.pending_dialog is not None,
        )
        self._transition(SessionState.READY)
        self.touch()
        # The typed text is NOT echoed back (it may be a credential).
        return {
            "success": True, "action": "type", "chars": len(text),
            "resolution": resolution.to_dict(), "verification": verification.to_dict(),
            "state_changed": verification.state_changed,
        }

    async def fill(self, raw_target: Any, text: str, **kwargs: Any) -> dict[str, Any]:
        return await self.type_text(raw_target, text, **kwargs)

    async def select(self, raw_target: Any, value: Any, *, timeout: Optional[float] = None) -> dict[str, Any]:
        self._transition(SessionState.ACTING)
        try:
            resolution = await self.resolve(raw_target)
            selected = await resolution.locator.first.select_option(value, timeout=self._timeout(timeout))
        except Exception as exc:  # noqa: BLE001
            self._transition(SessionState.READY)
            raise BrowserSessionError(
                "Eclipse couldn't choose that option.", session_id=self.id, action="select",
                metadata={"error": str(exc)[:200]},
            ) from exc
        self._transition(SessionState.READY)
        self.touch()
        return {"success": True, "action": "select", "selected": selected, "resolution": resolution.to_dict()}

    async def check(self, raw_target: Any, *, checked: bool = True, timeout: Optional[float] = None) -> dict[str, Any]:
        self._transition(SessionState.ACTING)
        try:
            resolution = await self.resolve(raw_target)
            locator = resolution.locator.first
            if checked:
                await locator.check(timeout=self._timeout(timeout))
            else:
                await locator.uncheck(timeout=self._timeout(timeout))
        except Exception as exc:  # noqa: BLE001
            self._transition(SessionState.READY)
            raise BrowserSessionError(
                "Eclipse couldn't change that checkbox.", session_id=self.id, action="check",
                metadata={"error": str(exc)[:200]},
            ) from exc
        self._transition(SessionState.READY)
        self.touch()
        return {"success": True, "action": "check", "checked": checked, "resolution": resolution.to_dict()}

    async def press(self, key: str, raw_target: Any = None, *, timeout: Optional[float] = None) -> dict[str, Any]:
        self._transition(SessionState.ACTING)
        try:
            if raw_target:
                resolution = await self.resolve(raw_target)
                await resolution.locator.first.press(key, timeout=self._timeout(timeout))
            else:
                await self.page().keyboard.press(key)
        except Exception as exc:  # noqa: BLE001
            self._transition(SessionState.READY)
            raise BrowserSessionError(
                "Eclipse couldn't send that key.", session_id=self.id, action="press",
                metadata={"error": str(exc)[:200]},
            ) from exc
        self._transition(SessionState.READY)
        self.touch()
        return {"success": True, "action": "press", "key": key}

    async def hover(self, raw_target: Any, *, timeout: Optional[float] = None) -> dict[str, Any]:
        self._transition(SessionState.ACTING)
        try:
            resolution = await self.resolve(raw_target)
            await self._scroll_into_view(resolution.locator.first)
            await resolution.locator.first.hover(timeout=self._timeout(timeout))
        except Exception as exc:  # noqa: BLE001
            self._transition(SessionState.READY)
            raise BrowserSessionError(
                "Eclipse couldn't hover over that element.", session_id=self.id, action="hover",
                metadata={"error": str(exc)[:200]},
            ) from exc
        self._transition(SessionState.READY)
        self.touch()
        return {"success": True, "action": "hover", "resolution": resolution.to_dict()}

    async def scroll(self, *, dy: int = 600, dx: int = 0, selector: Optional[str] = None, timeout: Optional[float] = None) -> dict[str, Any]:
        try:
            if selector:
                await self.page().locator(selector).first.scroll_into_view_if_needed(timeout=self._timeout(timeout))
            else:
                await self.page().mouse.wheel(dx, dy)
        except Exception as exc:  # noqa: BLE001
            raise BrowserSessionError(
                "Eclipse couldn't scroll the page.", session_id=self.id, action="scroll",
                metadata={"error": str(exc)[:200]},
            ) from exc
        self.touch()
        return {"success": True, "action": "scroll", "dy": dy, "dx": dx}

    async def drag(self, source: Any, target: Any, *, timeout: Optional[float] = None) -> dict[str, Any]:
        self._transition(SessionState.ACTING)
        try:
            src = await self.resolve(source)
            dst = await self.resolve(target)
            await src.locator.first.drag_to(dst.locator.first, timeout=self._timeout(timeout))
        except Exception as exc:  # noqa: BLE001
            self._transition(SessionState.READY)
            raise BrowserSessionError(
                "Eclipse couldn't drag that element.", session_id=self.id, action="drag",
                metadata={"error": str(exc)[:200]},
            ) from exc
        self._transition(SessionState.READY)
        self.touch()
        return {"success": True, "action": "drag"}

    # ── waiting ──────────────────────────────────────────────────────────────

    async def wait(self, *, ms: int = 1000) -> dict[str, Any]:
        from . import waiting  # noqa: PLC0415

        return await waiting.wait(self, ms=ms)

    async def wait_for_selector(self, raw_target: Any, *, state: str = "visible", timeout: Optional[float] = None) -> dict[str, Any]:
        from . import waiting  # noqa: PLC0415

        return await waiting.wait_for_selector(self, raw_target, state=state, timeout=timeout)

    async def wait_for_text(self, text: str, *, timeout: Optional[float] = None) -> dict[str, Any]:
        from . import waiting  # noqa: PLC0415

        return await waiting.wait_for_text(self, text, timeout=timeout)

    async def wait_for_url(self, pattern: str, *, timeout: Optional[float] = None) -> dict[str, Any]:
        from . import waiting  # noqa: PLC0415

        return await waiting.wait_for_url(self, pattern, timeout=timeout)

    async def wait_for_load_state(self, state: str = "load", *, timeout: Optional[float] = None) -> dict[str, Any]:
        from . import waiting  # noqa: PLC0415

        return await waiting.wait_for_load_state(self, state, timeout=timeout)

    async def wait_for_navigation(self, *, timeout: Optional[float] = None) -> dict[str, Any]:
        from . import waiting  # noqa: PLC0415

        return await waiting.wait_for_navigation(self, timeout=timeout)

    async def wait_for_network(self, *, idle_ms: int = 500, timeout: Optional[float] = None) -> dict[str, Any]:
        from . import waiting  # noqa: PLC0415

        return await waiting.wait_for_network(self, idle_ms=idle_ms, timeout=timeout)

    async def wait_for_popup(self, *, timeout: Optional[float] = None) -> dict[str, Any]:
        from . import waiting  # noqa: PLC0415

        return await waiting.wait_for_popup(self, timeout=timeout)

    async def wait_for_download(self, *, timeout: Optional[float] = None) -> dict[str, Any]:
        from . import waiting  # noqa: PLC0415

        return await waiting.wait_for_download(self, timeout=timeout)

    # ── files ────────────────────────────────────────────────────────────────

    async def _finalize_download(self) -> None:
        if self._last_download is not None and self._last_download.get("status") == "started":
            await self.finalize_download(self._last_download)

    async def finalize_download(self, record: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        record = record or self._last_download
        if record is None:
            raise BrowserDownloadError("No download is in progress.", session_id=self.id, action="download")
        download = record.get("download")
        try:
            path = await download.path()
        except Exception as exc:  # noqa: BLE001
            record["status"] = "failed"
            raise BrowserDownloadError(
                "The download couldn't be saved.", session_id=self.id, action="download",
                metadata={"error": str(exc)[:200]},
            ) from exc
        import hashlib  # noqa: PLC0415

        dest = Path(path) if path else None
        checksum = None
        size = None
        if dest is not None and dest.exists():
            size = dest.stat().st_size
            try:
                checksum = hashlib.sha256(dest.read_bytes()).hexdigest()[:32]
            except OSError:
                checksum = None
        record.update({
            "path": str(dest) if dest else None, "size": size, "checksum": checksum,
            "completedAt": now_iso(), "status": "completed",
            "mimeType": await self._safe_content_type(download),
        })
        if self.store is not None:
            try:
                self.store.save_download({k: v for k, v in record.items() if k not in ("download", "tabId")})
            except Exception:  # noqa: BLE001
                pass
        return {k: v for k, v in record.items() if k not in ("download",)}

    async def _safe_content_type(self, download: Any) -> Optional[str]:
        try:
            return await download.failure() or None
        except Exception:  # noqa: BLE001
            return None

    async def download(self, raw_target: Any, *, timeout: Optional[float] = None) -> dict[str, Any]:
        self._transition(SessionState.ACTING)
        try:
            resolution = await self.resolve(raw_target)
            async with self.page().expect_download(timeout=self._timeout(timeout) or 30_000.0) as download_info:
                await resolution.locator.first.click(timeout=self._timeout(timeout))
            download = await download_info.value
            record = {
                "id": __import__("uuid").uuid4().hex, "sessionId": self.id,
                "filename": download.suggested_filename, "sourceUrl": getattr(download, "url", ""),
                "startedAt": now_iso(), "status": "started", "download": download,
            }
            result = await self.finalize_download(record)
        except Exception as exc:  # noqa: BLE001
            self._transition(SessionState.READY)
            if isinstance(exc, (BrowserDownloadError, BrowserElementNotFoundError)):
                raise
            raise BrowserDownloadError(
                "Eclipse couldn't download from that element.", session_id=self.id, action="download",
                metadata={"error": str(exc)[:200]},
            ) from exc
        self._transition(SessionState.READY)
        self.touch()
        return result

    async def upload(self, raw_target: Any, files: list[str], *, timeout: Optional[float] = None) -> dict[str, Any]:
        self._transition(SessionState.ACTING)
        try:
            resolution = await self.resolve(raw_target)
            await resolution.locator.first.set_input_files(files, timeout=self._timeout(timeout))
        except Exception as exc:  # noqa: BLE001
            self._transition(SessionState.READY)
            if isinstance(exc, BrowserElementNotFoundError):
                raise
            raise BrowserUploadError(
                "Eclipse couldn't upload to that field.", session_id=self.id, action="upload",
                metadata={"error": str(exc)[:200]},
            ) from exc
        self._transition(SessionState.READY)
        self.touch()
        return {"success": True, "action": "upload", "count": len(files)}

    # ── debugging ────────────────────────────────────────────────────────────

    async def evaluate(self, expression: str, *, arg: Any = None) -> Any:
        try:
            if arg is None:
                return await self.page().evaluate(expression)
            return await self.page().evaluate(expression, arg)
        except Exception as exc:  # noqa: BLE001
            raise BrowserSessionError(
                "Eclipse couldn't run that script on the page.", session_id=self.id,
                action="evaluate", metadata={"error": str(exc)[:200]},
            ) from exc

    async def cdp(self, method: str, params: Optional[dict[str, Any]] = None) -> Any:
        from .providers.cdp import CDPProvider, is_cdp_allowed  # noqa: PLC0415

        if not is_cdp_allowed(method):
            from .errors import BrowserCDPError  # noqa: PLC0415

            raise BrowserCDPError(
                f"Eclipse isn't allowed to send the {method!r} browser command.",
                session_id=self.id, action="cdp",
            )
        return await CDPProvider(self.provider).send(self._ps, self.page(), method, params)

    def console_log(self, *, level: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
        entries = self.console
        if level:
            entries = [e for e in entries if e.get("type") == level]
        return entries[-limit:]

    def network_log(self, *, kind: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
        entries = self.network
        if kind:
            entries = [e for e in entries if e.get("kind") == kind]
        return entries[-limit:]

    def error_log(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.errors[-limit:]

    # ── storage / permissions ────────────────────────────────────────────────

    async def cookies(self, urls: Optional[list[str]] = None) -> list[dict[str, Any]]:
        try:
            return await self._ps.context.cookies(urls or None)
        except Exception as exc:  # noqa: BLE001
            raise BrowserSessionError("Eclipse couldn't read the site's cookies.", session_id=self.id, action="cookies", metadata={"error": str(exc)[:200]}) from exc

    async def set_cookie(self, cookie: dict[str, Any]) -> None:
        try:
            await self._ps.context.add_cookies([cookie])
        except Exception as exc:  # noqa: BLE001
            raise BrowserSessionError("Eclipse couldn't set that cookie.", session_id=self.id, action="set_cookie", metadata={"error": str(exc)[:200]}) from exc

    async def clear_cookies(self, urls: Optional[list[str]] = None) -> None:
        try:
            await self._ps.context.clear_cookies()
        except Exception:  # noqa: BLE001
            pass

    async def storage(self) -> dict[str, Any]:
        try:
            return await self.page().evaluate(
                "() => ({local: Object.assign({}, window.localStorage), "
                "session: Object.assign({}, window.sessionStorage)})"
            )
        except Exception:  # noqa: BLE001
            return {"local": {}, "session": {}}

    async def permissions(self, *, grant: Optional[list[str]] = None, revoke: Optional[list[str]] = None) -> dict[str, Any]:
        context = self._ps.context
        try:
            if grant:
                await context.grant_permissions(grant)
                self.permissions_granted = sorted(set(self.permissions_granted) | set(grant))
            if revoke:
                await context.clear_permissions()
                self.permissions_granted = []
        except Exception as exc:  # noqa: BLE001
            raise BrowserSessionError("Eclipse couldn't change the page's permissions.", session_id=self.id, action="permissions", metadata={"error": str(exc)[:200]}) from exc
        return {"granted": self.permissions_granted}

    # ── device emulation ─────────────────────────────────────────────────────

    async def set_viewport(self, width: int, height: int) -> dict[str, Any]:
        try:
            await self.page().set_viewport_size({"width": int(width), "height": int(height)})
        except Exception as exc:  # noqa: BLE001
            raise BrowserSessionError("Eclipse couldn't resize the window.", session_id=self.id, action="set_viewport", metadata={"error": str(exc)[:200]}) from exc
        return {"width": width, "height": height}

    async def emulate_device(self, device: str) -> dict[str, Any]:
        from playwright.async_api import devices  # noqa: PLC0415

        if device not in devices:
            raise BrowserSessionError(f"Eclipse doesn't know the device {device!r}.", session_id=self.id, action="emulate")
        descriptor = devices[device]
        context = self._ps.context
        try:
            page = await context.new_page()
            await page.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            await context.set_extra_http_headers(descriptor.get("user_agent") and {"User-Agent": descriptor["user_agent"]} or {})
            if descriptor.get("viewport"):
                await self.page().set_viewport_size(descriptor["viewport"])
        except Exception:  # noqa: BLE001
            pass
        return {"device": device, "applied": True}

    # ── dialogs ──────────────────────────────────────────────────────────────

    async def dialog(self, action: str, *, text: Optional[str] = None) -> dict[str, Any]:
        dialog = self.pending_dialog
        if dialog is None:
            return {"pending": False, "handled": False}
        try:
            if action == "accept":
                await dialog.accept(text) if text is not None else await dialog.accept()
            elif action == "dismiss":
                await dialog.dismiss()
            else:
                raise BrowserDialogError(
                    "Eclipse can only accept or dismiss a page dialog.", session_id=self.id, action="dialog",
                )
        except BrowserDialogError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BrowserDialogError("Eclipse couldn't handle the page dialog.", session_id=self.id, action="dialog", metadata={"error": str(exc)[:200]}) from exc
        info = self.pending_dialog_info
        self.pending_dialog = None
        self.pending_dialog_info = None
        return {"pending": False, "handled": True, "action": action, "info": info}

    def pending_dialog_dict(self) -> Optional[dict[str, Any]]:
        return self.pending_dialog_info

    # ── human-in-the-loop / CAPTCHA ──────────────────────────────────────────

    CHALLENGE_MARKERS = (
        "captcha", "recaptcha", "hcaptcha", "verify you are human",
        "are you a robot", "cf-challenge", "cloudflare", "checking your browser",
        "two-factor", "two factor", "one-time code", "verification code",
        "multi-factor", "mfa", "security check", "unusual activity",
    )

    def _maybe_detect_challenge(self) -> None:
        try:
            text = (self.current_title() or "").lower()
        except Exception:  # noqa: BLE001
            text = ""
        # A full check requires the page body; done lazily by the tool via
        # `detect_challenge`. This is only a cheap title hint.
        if any(marker in text for marker in self.CHALLENGE_MARKERS):
            self.state = SessionState.HUMAN_REQUIRED

    async def detect_challenge(self) -> Optional[str]:
        """Detect a CAPTCHA/MFA/security challenge, or None.

        Detection only — never a bypass. On a hit the session moves to
        HUMAN_REQUIRED and automation pauses.
        """
        try:
            text = ((await self.page().title()) + " " + (await self.get_text())[:5000]).lower()
        except Exception:  # noqa: BLE001
            text = ""
        for marker in self.CHALLENGE_MARKERS:
            if marker in text:
                self.state = SessionState.HUMAN_REQUIRED
                self._persist()
                return marker
        return None

    def request_human(self, reason: str) -> dict[str, Any]:
        self.state = SessionState.HUMAN_REQUIRED
        self._persist()
        return {"sessionId": self.id, "state": self.state.value, "reason": reason}

    def pause(self) -> dict[str, Any]:
        self._transition(SessionState.PAUSED)
        return {"sessionId": self.id, "state": self.state.value}

    def resume(self) -> dict[str, Any]:
        if self.state == SessionState.HUMAN_REQUIRED:
            self.state = SessionState.READY
            self._persist()
        else:
            self._transition(SessionState.READY)
        return {"sessionId": self.id, "state": self.state.value}

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def close(self) -> None:
        if self.state == SessionState.TERMINATED:
            return
        self._transition(SessionState.TERMINATING)
        try:
            await self._ps.close()
        except Exception:  # noqa: BLE001
            pass
        self.tabs.clear()
        self.active_tab = None
        self._transition(SessionState.TERMINATED)
        if self.trace is not None:
            self.trace.close("terminated")
            self.trace.persist()

    def snapshot_summary(self) -> dict[str, Any]:
        return {
            "sessionId": self.id,
            "provider": self.provider.id,
            "backend": self.backend,
            "browserType": self.browser_type,
            "state": self.state.value,
            "url": self.current_url(),
            "title": self.current_title(),
            "tabs": self.tabs_list(),
            "activeTab": self.active_tab,
            "createdAt": _iso(self.created_at),
            "lastActivity": _iso(self.last_activity),
            "permissionsGranted": self.permissions_granted,
            "pendingDialog": self.pending_dialog_info,
            "downloads": len(self.downloads),
            "consoleEntries": len(self.console),
            "networkEntries": len(self.network),
            "errors": len(self.errors),
            "profileId": self.profile_id,
            "agentId": self.agent_id,
            "taskId": self.task_id,
            "policy": self.policy.to_dict(),
        }


def _iso(epoch: float) -> str:
    from datetime import datetime, timezone  # noqa: PLC0415

    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


__all__ = ["BrowserSession", "SessionState", "TabInfo"]
