"""Optional providers — honest adapters for non-default backends.

Each implements the SAME `BrowserProvider` interface, declares its capabilities,
performs real capability/availability discovery, and returns a clear
UNAVAILABLE reason when its runtime dependency or credentials are missing. None
of these is faked: they do not claim to be operational when the underlying
runtime is absent. They are additive — the default is always Local Chromium.

P1: Browser Use, Browserbase.
P2: Camofox (a stealth Firefox launched by the local provider), Lightpanda,
    agent-browser, Firecrawl.
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Optional

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
        """Launch through Browser Use's Playwright-backed browser, driven by Eclipse.

        Browser Use owns the browser process; Eclipse RETAINS reasoning, sessions,
        policy, observation and tracing — this provider only supplies the browser.
        The adapter is version-tolerant: it tries the known Browser Use entry
        points and, when the installed build exposes none of them, fails HONESTLY
        rather than pretending to launch.
        """
        if not self.availability().get("available"):
            raise BrowserUnavailable(
                "Browser Use isn't available. Eclipse keeps its own browser runtime; "
                "install the `browser-use` package to add it as a backend.",
                provider=self.id,
            )
        try:
            browser, context = await self._start_browser_use(options)
        except BrowserUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - an incompatible build is honest
            raise BrowserUnavailable(
                "Browser Use is installed but this build doesn't expose a browser "
                "Eclipse can drive; Eclipse uses its own runtime instead.",
                provider=self.id, code="BROWSER_PROVIDER_UNAVAILABLE",
                metadata={"error": str(exc)[:200]},
            ) from exc
        pages = []
        try:
            pages = list(context.pages)
        except Exception:  # noqa: BLE001
            pages = []
        if not pages:
            try:
                pages = [await context.new_page()]
            except Exception:  # noqa: BLE001
                pages = []
        return ProviderSession(
            provider_id=self.id, capabilities=self.capabilities(), backend="browser_use",
            browser=browser, context=context, pages=pages, owns_browser=True,
            metadata={"adapter": "browser_use"},
        )

    async def _start_browser_use(self, options: LaunchOptions) -> tuple[Any, Any]:
        """Start a Browser Use browser and return `(browser, playwright_context)`."""
        # Browser Use exposes its Playwright-backed objects under a few shapes
        # across versions. Try the known ones; a miss raises (handled by the caller).
        import browser_use  # noqa: PLC0415

        headless = bool(options.headless)
        # Shape A: `browser_use.Browser` + `.new_context()`.
        browser_cls = getattr(browser_use, "Browser", None)
        if browser_cls is not None:
            browser = browser_cls(headless=headless)
            if hasattr(browser, "new_context"):
                context = await browser.new_context()
                return browser, await self._playwright_context(context)
        # Shape B: a `BrowserSession` with a `get_current_page`.
        session_cls = getattr(browser_use, "BrowserSession", None) or getattr(
            __import__("browser_use.browser.session", fromlist=["BrowserSession"]), "BrowserSession", None
        )
        if session_cls is not None:
            session = session_cls()
            if hasattr(session, "start"):
                await session.start()
            page = None
            if hasattr(session, "get_current_page"):
                page = await session.get_current_page()
            context = getattr(page, "context", None)
            if context is not None:
                return session, context
        raise BrowserUnavailable(
            "This Browser Use build doesn't expose a driveable browser.", provider=self.id,
        )

    async def _playwright_context(self, context: Any) -> Any:
        """Browser Use's context manager may wrap a Playwright context."""
        getter = getattr(context, "get_playwright_context", None)
        if callable(getter):
            result = getter()
            if hasattr(result, "__await__"):
                result = await result
            return result
        return context


class CamofoxProvider(BrowserProvider):
    """Camoufox — a stealth Firefox-based browser, launched by the local provider.

    Camoufox is a Playwright-*firefox* browser (not CDP). This provider resolves a
    Camoufox browser binary — from the installed `camoufox` package's own resolver,
    or a configured path/endpoint — and launches it through Eclipse's local
    provider with `browser_type="firefox"`. When neither is present it reports an
    honest UNAVAILABLE; it never claims to run.
    """

    id = "camofox"
    label = "Camoufox (stealth Firefox)"

    def __init__(self, local: Any = None) -> None:
        from .local_chromium import LocalChromiumProvider  # noqa: PLC0415

        self._local = local or LocalChromiumProvider()

    def capabilities(self) -> Any:
        return PROVIDER_CAPABILITIES["camofox"]

    def _executable(self) -> Optional[str]:
        """A Camoufox browser binary: the package's resolver, or a configured path."""
        from ..config import browser_config  # noqa: PLC0415

        cfg = browser_config()
        configured = cfg.camofox_endpoint
        if configured and os.path.isfile(configured):
            return configured
        # The `camoufox` package ships a binary resolver.
        for attribute in ("camoufox_path", "executable_path"):
            try:
                module = __import__("camoufox", fromlist=[attribute])  # noqa: PLC0415
                resolver = getattr(module, attribute, None)
                if callable(resolver):
                    path = resolver()
                    if path and os.path.isfile(str(path)):
                        return str(path)
            except Exception:  # noqa: BLE001 - a missing resolver is not a binary
                continue
        return None

    def availability(self) -> dict[str, Any]:
        from ..config import browser_config  # noqa: PLC0415

        cfg = browser_config()
        if not cfg.camofox_enabled:
            return {"available": False, "reason": "Camoufox is disabled in configuration."}
        executable = self._executable()
        if executable:
            return {"available": True, "reason": None, "executable": executable}
        if cfg.camofox_endpoint:
            return {"available": True, "reason": None, "endpoint": cfg.camofox_endpoint}
        return {
            "available": False,
            "reason": (
                "Camoufox is enabled but no browser binary was found. Install the "
                "`camoufox` package (and run its `fetch` step), or set "
                "HARNESS_CAMOFOX_ENDPOINT to the binary/endpoint."
            ),
        }

    async def launch(self, options: LaunchOptions) -> ProviderSession:
        availability = self.availability()
        if not availability.get("available"):
            raise BrowserUnavailable(availability.get("reason") or "Camoufox isn't available.", provider=self.id)
        executable = availability.get("executable")
        if not executable:
            # Only an endpoint is configured: attach instead of launching.
            if availability.get("endpoint"):
                return await self.connect(options)
            raise BrowserUnavailable(
                "Camoufox is enabled but no launchable binary or endpoint is configured.",
                provider=self.id, code="BROWSER_PROVIDER_UNAVAILABLE",
            )
        options.browser_type = "firefox"
        options.executable_path = executable
        session = await self._local.launch(options)
        session.provider_id = self.id
        session.capabilities = self.capabilities()
        session.backend = "camofox"
        session.metadata["camoufoxExecutable"] = executable
        return session

    async def connect(self, options: LaunchOptions) -> ProviderSession:
        availability = self.availability()
        if not availability.get("available"):
            raise BrowserUnavailable(availability.get("reason") or "Camoufox isn't available.", provider=self.id)
        endpoint = availability.get("endpoint")
        if not endpoint:
            raise BrowserUnavailable("No Camoufox endpoint is configured.", provider=self.id)
        options.cdp_endpoint = endpoint
        from .cdp import CDPProvider  # noqa: PLC0415

        session = await CDPProvider(self._local).connect(options)
        session.provider_id = self.id
        session.capabilities = self.capabilities()
        return session


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
    EXTRACTION request here and an INTERACTION request elsewhere (`launch` refuses,
    so it can never become an interactive browser).
    """

    id = "firecrawl"
    label = "Firecrawl (extraction)"

    BASE_URL = "https://api.firecrawl.dev"

    def capabilities(self) -> Any:
        return PROVIDER_CAPABILITIES["firecrawl"]

    def _base_url(self) -> str:
        from ..config import browser_config  # noqa: PLC0415

        return (browser_config().firecrawl_endpoint or self.BASE_URL).rstrip("/")

    def availability(self) -> dict[str, Any]:
        from ..config import browser_config  # noqa: PLC0415

        cfg = browser_config()
        if not cfg.firecrawl_enabled:
            return {"available": False, "reason": "Firecrawl is disabled in configuration."}
        # A self-hosted endpoint with the CLI present, OR a cloud API key.
        if cfg.firecrawl_endpoint and shutil.which("firecrawl"):
            return {"available": True, "reason": None, "endpoint": cfg.firecrawl_endpoint}
        if os.environ.get("FIRECRAWL_API_KEY"):
            return {"available": True, "reason": None, "endpoint": self._base_url()}
        return {
            "available": False,
            "reason": "Firecrawl isn't installed or configured (no API key or self-hosted endpoint).",
        }

    async def launch(self, options: LaunchOptions) -> ProviderSession:
        raise BrowserCapabilityError(
            "The Firecrawl backend extracts page content; it isn't an interactive "
            "browser. Eclipse routes extraction here and interaction to a real browser.",
            provider=self.id, action="launch",
        )

    async def extract(self, url: str, *, timeout_s: float = 30.0) -> dict[str, Any]:
        """Extract a page through Firecrawl. Returns a structured result.

        Never fabricates: a non-2xx response or an empty body is an honest
        `ok=False` with the reason. The API key (when cloud) is read from the
        environment, never logged and never returned.
        """
        availability = self.availability()
        if not availability.get("available"):
            return {"ok": False, "url": url, "error": availability.get("reason") or "Firecrawl unavailable"}
        endpoint = availability.get("endpoint") or self._base_url()
        api_key = os.environ.get("FIRECRAWL_API_KEY")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body: dict[str, Any] = {"url": url, "formats": ["markdown", "html"]}
        try:
            import httpx  # noqa: PLC0415

            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.post(f"{endpoint}/v1/scrape", headers=headers, json=body)
        except Exception as exc:  # noqa: BLE001 - a transport error is an honest miss
            return {"ok": False, "url": url, "error": f"Firecrawl request failed: {str(exc)[:200]}"}
        if response.status_code >= 400:
            return {"ok": False, "url": url, "error": f"Firecrawl returned HTTP {response.status_code}"}
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            return {"ok": False, "url": url, "error": "Firecrawl returned a non-JSON response"}
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return {"ok": False, "url": url, "error": "Firecrawl returned no data"}
        markdown = str(data.get("markdown") or "")
        text = markdown or str(data.get("html") or "")
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        return {
            "ok": bool(text.strip()),
            "url": str(metadata.get("sourceURL") or data.get("url") or url),
            "title": metadata.get("title"),
            "text": text,
            "extraction": "firecrawl",
            "status": "OK" if text.strip() else "UNAVAILABLE",
        }


# The optional providers registered alongside P0. Order is the router's tie-break.
OPTIONAL_PROVIDERS = (
    BrowserUseProvider,
    BrowserbaseProvider,
    LightpandaProvider,
    AgentBrowserProvider,
    FirecrawlProvider,
    CamofoxProvider,
)


__all__ = [
    "AgentBrowserProvider",
    "BrowserUseProvider",
    "BrowserbaseProvider",
    "CamofoxProvider",
    "FirecrawlProvider",
    "LightpandaProvider",
    "OPTIONAL_PROVIDERS",
]
