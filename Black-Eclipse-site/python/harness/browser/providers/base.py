"""The BrowserProvider interface and shared provider contracts.

A provider owns HOW a browser is launched/connected; the runtime, session
manager, observation engine and tools all sit ABOVE it and never touch a raw
Playwright object. The interface is adapted to Eclipse's async runtime:

    provider.launch(options)  -> ProviderSession
    provider.connect(options) -> ProviderSession
    provider.close(session)   -> None
    provider.capabilities()   -> BrowserCapabilities

A provider that cannot run in this environment reports an honest
`availability()` reason; it is never faked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..capabilities import BrowserCapabilities, PROVIDER_CAPABILITIES


@dataclass
class LaunchOptions:
    """Everything a provider needs to start a session."""

    headless: bool = True
    browser_type: str = "chromium"
    viewport_width: int = 1280
    viewport_height: int = 800
    user_agent: Optional[str] = None
    locale: Optional[str] = None
    timezone: Optional[str] = None
    proxy: Optional[str] = None
    user_data_dir: Optional[Path] = None
    downloads_dir: Optional[Path] = None
    cdp_endpoint: Optional[str] = None
    args: list[str] = field(default_factory=list)
    record_video: bool = False
    remote: bool = False
    # Opaque per-provider configuration (e.g. Browserbase project/credential ref).
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderSession:
    """A launched/connected browser plus its context and pages.

    The runtime holds this; it is the ONLY place a Playwright object is touched.
    `owns_browser` is False for a CDP attach (the runtime must not close a browser
    it did not start).
    """

    provider_id: str
    capabilities: BrowserCapabilities
    backend: str
    browser: Any = None
    context: Any = None
    pages: list[Any] = field(default_factory=list)
    playwright: Any = None
    owns_browser: bool = True
    cdp_url: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    closed: bool = False

    async def new_page(self) -> Any:
        page = await self.context.new_page()
        self.pages.append(page)
        return page

    def remove_page(self, page: Any) -> None:
        try:
            if page in self.pages:
                self.pages.remove(page)
        except Exception:  # noqa: BLE001
            pass

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        # Close pages, then the context, then the browser — deterministic order,
        # and every step best-effort so one failure never leaks the rest.
        for page in list(self.pages):
            try:
                await page.close()
            except Exception:  # noqa: BLE001
                pass
        self.pages.clear()
        try:
            if self.context is not None:
                await self.context.close()
        except Exception:  # noqa: BLE001
            pass
        if self.owns_browser and self.browser is not None:
            try:
                await self.browser.close()
            except Exception:  # noqa: BLE001
                pass


class BrowserProvider:
    """Base class. Subclasses declare an id, capabilities and availability."""

    id: str = "base"
    label: str = "Base provider"

    def capabilities(self) -> BrowserCapabilities:
        return PROVIDER_CAPABILITIES.get(self.id, BrowserCapabilities())

    def availability(self) -> dict[str, Any]:
        """Whether this provider can run here. `available` + optional `reason`."""
        return {"available": False, "reason": "not implemented"}

    async def launch(self, options: LaunchOptions) -> ProviderSession:  # pragma: no cover - abstract
        raise NotImplementedError

    async def connect(self, options: LaunchOptions) -> ProviderSession:  # pragma: no cover - abstract
        raise NotImplementedError

    async def close(self, session: ProviderSession) -> None:
        await session.close()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "capabilities": self.capabilities().to_dict(),
            "availability": self.availability(),
        }


__all__ = ["BrowserProvider", "LaunchOptions", "ProviderSession"]
