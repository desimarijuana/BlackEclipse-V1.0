"""Local Chromium provider — Eclipse-managed, Playwright-backed.

This is the P0 default. It launches an Eclipse-managed Chromium instance with an
isolated or persistent profile and controlled launch arguments; it does NOT touch
the user's personal Chrome. It also supports connecting to an existing
Chrome/Chromium over CDP (used by `CDPProvider`).

Playwright sits BEHIND this provider: the model never sees a raw Playwright
object. A missing Playwright package or an uninstalled browser is an honest
`availability()` reason, never a fake browser.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from ..capabilities import PROVIDER_CAPABILITIES
from ..errors import BrowserLaunchError, BrowserUnavailable
from .base import BrowserProvider, LaunchOptions, ProviderSession

# Controlled launch arguments. Deliberately conservative and deterministic: no
# background networking, no first-run chrome, no extension/automation banner.
# `--no-sandbox` is NOT included by default (it weakens isolation); an operator
# opts in explicitly with HARNESS_BROWSER_NO_SANDBOX.
_BASE_ARGS: tuple[str, ...] = (
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-extensions",
    "--disable-component-update",
    "--no-first-run",
    "--no-default-browser-check",
    "--metrics-recording-only",
    "--mute-audio",
    "--password-store=basic",
    "--use-mock-keychain",
    "--disable-features=Translate,BackForwardCache,AcceptCHFrame,MediaRouter,OptimizationHints",
    "--hide-scrollbars",
)


def _playwright_available() -> tuple[bool, Optional[str]]:
    try:
        import playwright  # noqa: F401, PLC0415
        from playwright.async_api import async_playwright  # noqa: F401, PLC0415
    except Exception as exc:  # noqa: BLE001 - a missing dependency is a supported state
        return False, f"Python Playwright is not installed ({type(exc).__name__})"
    return True, None


def _browser_installed(playwright: Any, browser_type: str) -> bool:
    launcher = getattr(playwright, browser_type, None)
    if launcher is None:
        return False
    try:
        return bool(launcher.executable_path and Path(launcher.executable_path).exists())
    except Exception:  # noqa: BLE001 - a probe failure is "unknown", treat as no
        return False


class LocalChromiumProvider(BrowserProvider):
    id = "local_chromium"
    label = "Eclipse-managed Chromium (local)"

    def __init__(self) -> None:
        self._playwright_manager: Any = None
        self._playwright: Any = None

    def capabilities(self) -> Any:
        return PROVIDER_CAPABILITIES["local_chromium"]

    def availability(self) -> dict[str, Any]:
        ok, reason = _playwright_available()
        if not ok:
            return {"available": False, "reason": reason}
        return {"available": True, "reason": None}

    async def _ensure_playwright(self) -> Any:
        if self._playwright is not None:
            return self._playwright
        try:
            from playwright.async_api import async_playwright  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            raise BrowserUnavailable(
                "The browser automation component isn't installed on this computer. "
                "Run `npm run setup:python` (or `python -m pip install -r python/requirements.txt`).",
                provider=self.id, metadata={"error": str(exc)[:200]},
            ) from exc
        try:
            self._playwright_manager = async_playwright()
            self._playwright = await self._playwright_manager.start()
        except Exception as exc:  # noqa: BLE001
            raise BrowserUnavailable(
                "The browser automation component couldn't start.",
                provider=self.id, metadata={"error": str(exc)[:200]},
            ) from exc
        return self._playwright

    def _launch_args(self) -> list[str]:
        args = list(_BASE_ARGS)
        if os.environ.get("HARNESS_BROWSER_NO_SANDBOX", "").strip().lower() in ("1", "true", "yes"):
            args.append("--no-sandbox")
        return args

    async def launch(self, options: LaunchOptions) -> ProviderSession:
        playwright = await self._ensure_playwright()
        launcher = getattr(playwright, options.browser_type or "chromium", None)
        if launcher is None:
            raise BrowserLaunchError(
                f"Eclipse doesn't know how to start a {options.browser_type} browser.",
                provider=self.id,
            )
        if not _browser_installed(playwright, options.browser_type or "chromium"):
            raise BrowserUnavailable(
                "The browser Eclipse controls isn't installed yet. "
                "Run `python -m playwright install chromium` once to download it.",
                provider=self.id, code="BROWSER_UNINSTALLED",
            )
        launch_kwargs: dict[str, Any] = {
            "headless": options.headless,
            "args": options.args or self._launch_args(),
        }
        if options.proxy:
            launch_kwargs["proxy"] = _proxy_settings(options.proxy)
        if options.downloads_dir is not None:
            try:
                options.downloads_dir.mkdir(parents=True, exist_ok=True)
                launch_kwargs["downloads_path"] = str(options.downloads_dir)
            except OSError:
                pass

        context_kwargs = self._context_kwargs(options)
        try:
            if options.user_data_dir is not None:
                # A persistent profile returns a context directly; closing the
                # context closes the browser.
                options.user_data_dir.mkdir(parents=True, exist_ok=True)
                context = await launcher.launch_persistent_context(
                    user_data_dir=str(options.user_data_dir), **launch_kwargs, **context_kwargs,
                )
                session = ProviderSession(
                    provider_id=self.id, capabilities=self.capabilities(), backend="playwright",
                    browser=None, context=context, playwright=playwright,
                    owns_browser=True,
                    metadata={"persistent": True, "userDataDir": str(options.user_data_dir)},
                )
                session.pages = list(context.pages)
            else:
                browser = await launcher.launch(**launch_kwargs)
                try:
                    context = await browser.new_context(**context_kwargs)
                except Exception:
                    await browser.close()
                    raise
                session = ProviderSession(
                    provider_id=self.id, capabilities=self.capabilities(), backend="playwright",
                    browser=browser, context=context, playwright=playwright,
                    owns_browser=True, metadata={"persistent": False},
                )
                if not context.pages:
                    await context.new_page()
                session.pages = list(context.pages)
        except BrowserUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BrowserLaunchError(
                "The browser couldn't be started.", provider=self.id, retryable=True,
                metadata={"error": str(exc)[:300]},
            ) from exc
        return session

    def _context_kwargs(self, options: LaunchOptions) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "viewport": {"width": options.viewport_width, "height": options.viewport_height},
            "accept_downloads": True,
            "ignore_https_errors": True,
        }
        if options.user_agent:
            kwargs["user_agent"] = options.user_agent
        if options.locale:
            kwargs["locale"] = options.locale
        if options.timezone:
            kwargs["timezone_id"] = options.timezone
        if options.record_video and options.downloads_dir is not None:
            try:
                options.downloads_dir.mkdir(parents=True, exist_ok=True)
                kwargs["record_video_dir"] = str(options.downloads_dir.parent / "videos")
            except OSError:
                pass
        # Keep the default (no) permissions; a session grants only what it needs
        # through `browser_permissions`, so nothing is pre-authorized.
        kwargs["permissions"] = []
        return kwargs

    async def connect(self, options: LaunchOptions) -> ProviderSession:
        endpoint = options.cdp_endpoint
        if not endpoint:
            raise BrowserLaunchError("No browser address was given to connect to.", provider=self.id)
        playwright = await self._ensure_playwright()
        try:
            browser = await playwright.chromium.connect_over_cdp(endpoint)
        except Exception as exc:  # noqa: BLE001
            raise BrowserLaunchError(
                "Eclipse couldn't connect to that browser.", provider=self.id, retryable=True,
                metadata={"error": str(exc)[:300]},
            ) from exc
        contexts = list(browser.contexts)
        if contexts:
            context = contexts[0]
        else:
            context = await browser.new_context(**_default_context())
        session = ProviderSession(
            provider_id=self.id, capabilities=self.capabilities(), backend="cdp",
            browser=browser, context=context, playwright=playwright,
            owns_browser=False, cdp_url=endpoint,
        )
        session.pages = list(context.pages)
        return session

    async def shutdown(self) -> None:
        """Stop the shared Playwright driver (called at process shutdown)."""
        try:
            if self._playwright_manager is not None:
                await self._playwright_manager.stop()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            pass
        self._playwright = None
        self._playwright_manager = None


def _default_context() -> dict[str, Any]:
    return {"viewport": {"width": 1280, "height": 800}, "accept_downloads": True}


def _proxy_settings(proxy: str) -> dict[str, str]:
    """Normalize a proxy string into Playwright's settings object."""
    if "://" in proxy:
        from urllib.parse import urlparse  # noqa: PLC0415

        parsed = urlparse(proxy)
        settings = {"server": f"{parsed.scheme}://{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")}
        if parsed.username:
            settings["username"] = parsed.username
        if parsed.password:
            settings["password"] = parsed.password
        return settings
    return {"server": proxy}


__all__ = ["LocalChromiumProvider"]
