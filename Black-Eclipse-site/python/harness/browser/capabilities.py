"""The provider capability registry.

Every provider DECLARES what it can do. The router uses these capabilities to
choose a provider, and a request for an unsupported action on the selected
provider is refused with `BROWSER_CAPABILITY_UNSUPPORTED` — never attempted and
silently degraded.

Capabilities are DATA (a frozen dataclass), so adding a backend is filling in a
record, not editing routing logic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BrowserCapabilities:
    """What a provider can do. Defaults are the common interactive set."""

    navigate: bool = True
    snapshots: bool = True
    screenshots: bool = True
    vision: bool = True
    downloads: bool = True
    uploads: bool = True
    cdp: bool = True
    console: bool = True
    network_inspection: bool = True
    evaluate_js: bool = True
    cookies: bool = True
    storage: bool = True
    persistent_profiles: bool = True
    isolated_sessions: bool = True
    multiple_tabs: bool = True
    iframes: bool = True
    dialogs: bool = True
    mobile_emulation: bool = True
    video_recording: bool = False
    tracing: bool = True
    request_interception: bool = True
    device_emulation: bool = True
    interactive: bool = True
    # A read-only extraction backend (Firecrawl) sets this False: it can fetch
    # and extract but cannot drive an interactive session.
    headless_only: bool = False
    # Remote/cloud: content leaves the machine. The router refuses to send a
    # private/local target to a provider that declares `remote=True` unless a
    # policy explicitly authorizes it.
    remote: bool = False

    def supports(self, capability: str) -> bool:
        return bool(getattr(self, capability, False))

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


# The declared capabilities per built-in provider id. Kept here (data) so a
# provider module imports its own record rather than re-declaring booleans.
PROVIDER_CAPABILITIES: dict[str, BrowserCapabilities] = {
    "local_chromium": BrowserCapabilities(),
    "cdp": BrowserCapabilities(persistent_profiles=False, isolated_sessions=False, video_recording=False),
    "browser_use": BrowserCapabilities(remote=False),
    "browserbase": BrowserCapabilities(remote=True, persistent_profiles=True),
    # Firecrawl is an extraction/research backend, not interactive automation.
    "firecrawl": BrowserCapabilities(
        interactive=False, evaluate_js=False, downloads=False, uploads=False,
        multiple_tabs=False, iframes=False, dialogs=False, cdp=False,
        console=False, network_inspection=False, cookies=False, storage=False,
        request_interception=False, device_emulation=False, remote=True,
        headless_only=True,
    ),
    "lightpanda": BrowserCapabilities(
        screenshots=False, vision=False, video_recording=False, mobile_emulation=False,
        device_emulation=False, downloads=False, uploads=False, request_interception=False,
        tracing=False, headless_only=True,
    ),
    "agent_browser": BrowserCapabilities(),
}


__all__ = ["BrowserCapabilities", "PROVIDER_CAPABILITIES"]
