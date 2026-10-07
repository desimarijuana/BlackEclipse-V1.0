"""Process-wide application runtime singleton (mirrors `execution/runtime.py`).

The `AgenticService` builds ONE `ApplicationRuntimeManager` at boot and installs
it here, so the agent tools and the HTTP surface resolve the SAME engine — the
same registry, the same runtime table, the same event stream. No second runtime.
"""

from __future__ import annotations

from typing import Optional


_MANAGER: Optional[object] = None


def set_application_runtime(manager: Optional[object]) -> None:
    global _MANAGER
    _MANAGER = manager


def get_application_runtime() -> Optional[object]:
    return _MANAGER


__all__ = ["get_application_runtime", "set_application_runtime"]
