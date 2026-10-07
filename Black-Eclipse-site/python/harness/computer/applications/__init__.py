"""Application management and the ApplicationAdapter framework.

    manager.py    list/launch/close/restart/is_running/get_info over the driver
    adapters/     the ApplicationAdapter base + per-application adapters
                  (excel, vscode, terminal, pdf, chrome, edge, tradingview,
                  mt5, ibkr, bloomberg, generic)
    registry.py   selects the adapter for a detected application

An adapter declares an application's identity, window detection, known controls,
keyboard shortcuts, state detection, verification strategies, safe actions and
known failure modes. Adapters are DATA + small helpers, never a second engine.
"""

from __future__ import annotations

from .manager import ApplicationManager
from .registry import AdapterRegistry, build_adapter_registry

__all__ = ["AdapterRegistry", "ApplicationManager", "build_adapter_registry"]
