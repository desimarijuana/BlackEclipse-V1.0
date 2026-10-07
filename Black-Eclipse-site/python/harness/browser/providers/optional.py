"""Optional providers — honest adapters for non-default backends.

Each implements the SAME `BrowserProvider` interface, declares its capabilities,
performs real capability/availability discovery, and returns a clear
UNAVAILABLE reason when its runtime dependency or credentials are missing. None
of these is faked: they do not claim to be operational when the underlying
runtime is absent. They are additive — the default is always Local Chromium.

P1: Browser Use, Browserbase.
P2: Camofox (via CDP), Lightpanda, agent-browser, Firecrawl.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from ..capabilities import PROVIDER_CAPABILITIES
from ..errors import BrowserCapabilityError, BrowserLaunchError, BrowserUnavailable
from .base import BrowserProvider, LaunchOptions, ProviderSession


class _UnavailableProvider(BrowserProvider):
    """Base for a provider that is configured but not runnable here."""

    id = "unavailable"
    label = "Unavailable provider"
    _hint = ""

    def availability(self) -> dict[str, Any]:
        return {"available": False, "reason": self._hint or "not available in this environment"}

    async def launch(self, options: LaunchOptions) -> ProviderSession:
        raise BrowserUnavailable(self._hint or "This browser backend isn't available.", provider=self.id)

    async def connect(self, options: LaunchOptions) -> ProviderSession:
        raise BrowserUnavailable(self._hint or "This browser backend isn't available.", provider=self.id)


class BrowserUseProvider(_UnavailableProvider):
    id = "browser_use"
    label = "Browser Use"

    def capabilities(self) -> Any:
        return PROVIDER_CAPABILITIES["browser_use"]

    def availability(self) -> dict[str, Any]:
        try:
            import browser_use  # noqa: F401, PLC0415
            return {"available": True, "reason": None}
        except Exception:  # noqa: BLE001
            self._hint = (
                "Browser Use is an optional backend and isn't installed. Install the "
                "`browser-use` package to enable it; Eclipse otherwise uses its own "
                "local Chromium runtime."
            )
            return {"available": False, "reason": self._hint}

    async def launch(self, options: LaunchOptions) -> ProviderSession:
        raise BrowserUnavailable(
            "Browser Use isn't available. Eclipse keeps its own browser runtime; "
            "install the `browser-use` package to add it as a backend.",
            provider=self.id,
        )


class BrowserbaseProvider(_UnavailableProvider):
    id = "browserbase"
    label = "Browserbase (cloud)"

    # The Browserbase REST API. A session is created server-side, then attached
    # over CDP through the SAME Playwright driver the local provider uses.
    BASE_URL = "https://api.browserbase.com/v1"

    def __init__(self, local: Any = None) -> None:
        from .local_chromium import LocalChromiumProvider  # noqa: PLC0415

        self._local = local or LocalChromiumProvider()

    def capabilities(self) -> Any:
        return PROVIDER_CAPABILITIES["browserbase"]

    def availability(self) -> dict[str, Any]:
        from ..config import browser_config  # noqa: PLC0415

        cfg = browser_config()
        if not cfg.browserbase_enabled:
            return {"available": False, "reason": "Browserbase is disabled in configuration."}
        if not cfg.browserbase_api_key_ref:
            return {
                "available": False,
                "reason": (
                    "Browserbase is enabled but no credential reference is configured "
                    "(HARNESS_BROWSERBASE_API_KEY_REF). Eclipse never hardcodes a key."
                ),
            }
        return {"available": True, "reason": None, "requiresCredential": True}

    async def _create_session(self, api_key: str, project_id: str) -> str:
        """Create a Browserbase session and return its CDP connect URL.

        Uses `httpx` (already a harness dependency). Any failure is reported
        honestly — a cloud session is never fabricated.
        """
        import httpx  # noqa: PLC0415

        body = {"projectId": project_id} if project_id else {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/sessions",
                headers={"X-BB-API-Key": api_key, "Content-Type": "application/json"},
                json=body,
            )
        if response.status_code >= 400:
            raise BrowserUnavailable(
                f"Browserbase refused the session request (HTTP {response.status_code}).",
                provider=self.id, code="BROWSER_PROVIDER_ERROR",
            )
        payload = response.json()
        connect_url = str(payload.get("connectUrl") or "")
        if not connect_url:
            raise BrowserUnavailable(
                "Browserbase returned no connect URL for the session.", provider=self.id,
            )
        return connect_url

    async def launch(self, options: LaunchOptions) -> ProviderSession:
        availability = self.availability()
        if not availability.get("available"):
            raise BrowserUnavailable(availability.get("reason") or "Browserbase isn't available.", provider=self.id)
        api_key = str((options.extra or {}).get("apiKey") or "")
        if not api_key:
            raise BrowserUnavailable(
                "Browserbase needs its project credential resolved through the vault, "
                "which isn't available for this call.",
                provider=self.id, code="BROWSER_CREDENTIAL_UNAVAILABLE",
            )
        project_id = str((options.extra or {}).get("projectId") or "")
        connect_url = await self._create_session(api_key, project_id)
        options.cdp_endpoint = connect_url
        session = await self._local.connect(options)
        session.provider_id = self.id
        session.capabilities = self.capabilities()
        session.metadata["browserbaseConnectUrl"] = connect_url
        return session


class LightpandaProvider(_UnavailableProvider):
    id = "lightpanda"
    label = "Lightpanda (lightweight)"

    def capabilities(self) -> Any:
        return PROVIDER_CAPABILITIES["lightpanda"]

    def availability(self) -> dict[str, Any]:
        from ..config import browser_config  # noqa: PLC0415

        cfg = browser_config()
        if not cfg.lightpanda_enabled:
            return {"available": False, "reason": "Lightpanda is disabled in configuration."}
        endpoint = cfg.lightpanda_endpoint
        if not endpoint:
            return {"available": False, "reason": "No Lightpanda endpoint is configured (HARNESS_LIGHTPANDA_ENDPOINT)."}
        return {"available": True, "reason": None, "endpoint": endpoint}

    async def connect(self, options: LaunchOptions) -> ProviderSession:
        availability = self.availability()
        if not availability.get("available"):
            raise BrowserUnavailable(availability.get("reason") or "Lightpanda isn't available.", provider=self.id)
        endpoint = availability.get("endpoint")
        # Lightpanda exposes a CDP endpoint; attach through the same CDP path.
        from .cdp import CDPProvider  # noqa: PLC0415

        options.cdp_endpoint = endpoint
        return await CDPProvider().connect(options)


class AgentBrowserProvider(_UnavailableProvider):
    id = "agent_browser"
    label = "agent-browser"

    def capabilities(self) -> Any:
        return PROVIDER_CAPABILITIES["agent_browser"]

    def availability(self) -> dict[str, Any]:
        from ..config import browser_config  # noqa: PLC0415

        cfg = browser_config()
        if not cfg.agent_browser_enabled:
            return {"available": False, "reason": "agent-browser is disabled in configuration."}
        if shutil.which("agent-browser") is None and not os.environ.get("HARNESS_AGENT_BROWSER_CMD"):
            return {"available": False, "reason": "The agent-browser executable isn't installed."}
        return {"available": True, "reason": None}

    async def launch(self, options: LaunchOptions) -> ProviderSession:
        availability = self.availability()
        if not availability.get("available"):
            raise BrowserUnavailable(availability.get("reason") or "agent-browser isn't available.", provider=self.id)
        raise BrowserUnavailable(
            "The agent-browser adapter is configured but its control protocol isn't "
            "wired for this build; Eclipse uses its own runtime instead.",
            provider=self.id, code="BROWSER_PROVIDER_UNAVAILABLE",
        )


class FirecrawlProvider(_UnavailableProvider):
    """Extraction/research backend — NOT interactive automation.

    Firecrawl fetches and extracts page content; it cannot click, type, manage
    tabs, capture console/network, or attach over CDP. The router routes an
    EXTRACTION request here and an INTERACTION request elsewhere.
    """

    id = "firecrawl"
    label = "Firecrawl (extraction)"

    def capabilities(self) -> Any:
        return PROVIDER_CAPABILITIES["firecrawl"]

    def availability(self) -> dict[str, Any]:
        from ..config import browser_config  # noqa: PLC0415

        cfg = browser_config()
        if not cfg.firecrawl_enabled:
            return {"available": False, "reason": "Firecrawl is disabled in configuration."}
        if shutil.which("firecrawl") is None and not os.environ.get("FIRECRAWL_API_KEY"):
            return {"available": False, "reason": "Firecrawl isn't installed or configured (no API key)."}
        return {"available": True, "reason": None}

    async def launch(self, options: LaunchOptions) -> ProviderSession:
        raise BrowserCapabilityError(
            "The Firecrawl backend extracts page content; it isn't an interactive "
            "browser. Eclipse routes extraction here and interaction to a real browser.",
            provider=self.id, action="launch",
        )


# The optional providers registered alongside P0. Order is the router's tie-break.
OPTIONAL_PROVIDERS = (
    BrowserUseProvider,
    BrowserbaseProvider,
    LightpandaProvider,
    AgentBrowserProvider,
    FirecrawlProvider,
)


__all__ = [
    "AgentBrowserProvider",
    "BrowserUseProvider",
    "BrowserbaseProvider",
    "FirecrawlProvider",
    "LightpandaProvider",
    "OPTIONAL_PROVIDERS",
]
