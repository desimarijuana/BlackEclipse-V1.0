"""Process-wide Computer Use runtime singleton.

Mirrors `browser.runtime` / `terminal.runtime` / `execution.runtime`: the service
constructs ONE `ComputerManager` at boot and registers it here, so a tool handler
resolves it without carrying a reference. When no manager is registered (a minimal
install or a unit test), `get_computer_manager()` returns None and the tools
report an honest UNAVAILABLE.
"""

from __future__ import annotations

from typing import Any, Optional


def build_computer_manager(*, agent_store: Any = None, bus: Any = None, vision: Any = None,
                           memory_service: Any = None) -> Any:
    from .manager import ComputerManager  # noqa: PLC0415

    return ComputerManager(agent_store=agent_store, bus=bus, vision=vision, memory_service=memory_service)


_MANAGER: Optional[Any] = None


def set_computer_manager(manager: Optional[Any]) -> None:
    global _MANAGER
    _MANAGER = manager


def get_computer_manager() -> Optional[Any]:
    return _MANAGER


__all__ = ["build_computer_manager", "get_computer_manager", "set_computer_manager"]
