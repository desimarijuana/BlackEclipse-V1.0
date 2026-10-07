"""Process-wide browser runtime singleton.

Mirrors `termin.runtime` / `execution.runtime` / `git.service`: the service
constructs ONE `BrowserManager` at boot and registers it here, so a tool handler
resolves it without carrying a reference. When no manager is registered (a
minimal install or a unit test), `get_browser_manager()` returns None and the
tools report an honest UNAVAILABLE.
"""

from __future__ import annotations

from typing import Any, Optional


def build_browser_manager(*, agent_store: Any = None, secret_resolver: Any = None, bus: Any = None) -> Any:
    from .manager import BrowserManager  # noqa: PLC0415

    return BrowserManager(agent_store=agent_store, resolver=secret_resolver, bus=bus)


_MANAGER: Optional[Any] = None


def set_browser_manager(manager: Optional[Any]) -> None:
    global _MANAGER
    _MANAGER = manager


def get_browser_manager() -> Optional[Any]:
    return _MANAGER


__all__ = ["build_browser_manager", "get_browser_manager", "set_browser_manager"]
