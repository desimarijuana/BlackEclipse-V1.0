"""Accessibility providers — the FIRST rung of the grounding hierarchy.

An accessibility tree gives Eclipse semantic, stable, role+name targets instead
of pixel coordinates. Providers are platform-specific and OPTIONAL: when no AX
backend is present the runtime reports `accessibility: false` and falls back to
OCR/vision honestly.

    base.py     the AXProvider interface + role heuristics
    windows.py  the Windows provider (UI Automation when installed; a Win32
                child-window enumeration as the always-available baseline)
    null.py     the honest unavailable provider
"""

from __future__ import annotations

from .base import AXProvider

__all__ = ["AXProvider"]
