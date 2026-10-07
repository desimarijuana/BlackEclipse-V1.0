"""Browser providers. The default is `LocalChromiumProvider`; optional backends
implement the same interface and report honest availability."""

from __future__ import annotations

from .base import BrowserProvider, LaunchOptions, ProviderSession
from .cdp import CDPProvider
from .local_chromium import LocalChromiumProvider
from .optional import (
    AgentBrowserProvider,
    BrowserUseProvider,
    BrowserbaseProvider,
    CamofoxProvider,
    FirecrawlProvider,
    LightpandaProvider,
)

__all__ = [
    "AgentBrowserProvider",
    "BrowserProvider",
    "BrowserUseProvider",
    "BrowserbaseProvider",
    "CamofoxProvider",
    "CDPProvider",
    "FirecrawlProvider",
    "LaunchOptions",
    "LightpandaProvider",
    "LocalChromiumProvider",
    "ProviderSession",
]
