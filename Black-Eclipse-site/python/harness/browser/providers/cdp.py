"""CDP provider — connect to an existing Chrome/Chromium over the DevTools Protocol.

First-class CDP support: connect, discover targets/pages, and drive the browser
through the same Playwright-backed control surface as local Chromium, plus a
controlled CDP command surface (`browser_cdp`). The provider never grants
unrestricted host access: only the Browser/Page/Runtime/Network/Target/DOM
domains are exposed through the tool, and a session may only send commands
through its own CDP session.
"""

from __future__ import annotations

from typing import Any

from ..capabilities import PROVIDER_CAPABILITIES
from ..errors import BrowserCDPError, BrowserLaunchError
from .base import BrowserProvider, LaunchOptions, ProviderSession

# CDP domains Eclipse exposes. A command outside these is refused. This is the
# boundary between "controlled CDP access" and "unrestricted host access".
ALLOWED_CDP_DOMAINS: frozenset[str] = frozenset({
    "Browser", "Page", "Runtime", "Network", "Target", "DOM",
})

# Read-only/metadata methods that are always safe even within an allowed domain.
SAFE_CDP_METHODS: frozenset[str] = frozenset({
    "Page.getNavigationHistory",
    "Page.captureScreenshot",
    "Page.getLayoutMetrics",
    "Runtime.evaluate",
    "Runtime.getProperties",
    "DOM.getDocument",
    "DOM.querySelector",
    "DOM.describeNode",
    "Network.getResponseBody",
    "Network.enable",
    "Network.disable",
    "Target.getTargets",
    "Browser.getVersion",
})


def cdp_domain_of(method: str) -> str:
    return str(method).split(".", 1)[0]


def is_cdp_allowed(method: str) -> bool:
    return cdp_domain_of(method) in ALLOWED_CDP_DOMAINS


class CDPProvider(BrowserProvider):
    id = "cdp"
    label = "Chrome DevTools Protocol (attach)"

    def __init__(self, local: Any = None) -> None:
        # Reuse the local provider's Playwright driver for the attach.
        from .local_chromium import LocalChromiumProvider  # noqa: PLC0415

        self._local = local or LocalChromiumProvider()

    def capabilities(self) -> Any:
        return PROVIDER_CAPABILITIES["cdp"]

    def availability(self) -> dict[str, Any]:
        return self._local.availability()

    async def connect(self, options: LaunchOptions) -> ProviderSession:
        if not options.cdp_endpoint:
            raise BrowserLaunchError(
                "No browser address was given to connect to.", provider=self.id,
            )
        session = await self._local.connect(options)
        session.provider_id = self.id
        session.capabilities = self.capabilities()
        return session

    async def launch(self, options: LaunchOptions) -> ProviderSession:
        # A CDP provider attaches; if asked to launch it starts a browser and
        # exposes its CDP endpoint (so `browser_launch` with provider=cdp works).
        session = await self._local.launch(options)
        session.provider_id = self.id
        return session

    async def send(self, session: ProviderSession, page: Any, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send ONE CDP command through the session's own CDP connection."""
        if not is_cdp_allowed(method):
            raise BrowserCDPError(
                f"Eclipse isn't allowed to send the {method!r} browser command.",
                provider=self.id, action="cdp",
            )
        try:
            cdp = await page.context.new_cdp_session(page)
        except Exception:
            try:
                cdp = await session.context.new_cdp_session(page)
            except Exception as exc:  # noqa: BLE001
                raise BrowserCDPError(
                    "Eclipse couldn't open a debugging connection to the page.",
                    provider=self.id, metadata={"error": str(exc)[:200]},
                ) from exc
        try:
            return await cdp.send(method, params or {})
        except Exception as exc:  # noqa: BLE001
            raise BrowserCDPError(
                f"The browser command {method!r} failed.",
                provider=self.id, action="cdp", metadata={"error": str(exc)[:300]},
            ) from exc


__all__ = ["ALLOWED_CDP_DOMAINS", "CDPProvider", "SAFE_CDP_METHODS", "cdp_domain_of", "is_cdp_allowed"]
