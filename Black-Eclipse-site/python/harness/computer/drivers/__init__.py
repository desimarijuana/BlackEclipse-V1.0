"""Platform driver factory.

`build_driver(backend)` selects a `ComputerDriver` for the current platform. The
core never imports a platform module directly — it asks this factory. An
unsupported platform returns the honest `NullDriver` rather than pretending.
"""

from __future__ import annotations

import sys
from typing import Optional

from .base import ComputerDriver, InputResult, ScreenFrame
from .null import NullDriver


def available_backend() -> str:
    """The driver id Eclipse would select automatically on this platform."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"      # not yet implemented → null until it is
    if sys.platform.startswith("linux"):
        return "linux"      # not yet implemented → null until it is
    return "null"


def build_driver(backend: Optional[str] = None) -> ComputerDriver:
    """Build a driver. `auto` (or None) picks the platform's best backend."""
    choice = (backend or "auto").strip().lower()
    if choice in ("", "auto"):
        choice = available_backend()

    if choice == "windows":
        if sys.platform == "win32":
            from .windows import WindowsDriver  # noqa: PLC0415

            return WindowsDriver()
        return NullDriver(sys.platform, "the windows driver is only available on Windows")

    if choice in ("macos", "linux"):
        return NullDriver(sys.platform, f"the {choice} driver is not yet implemented")

    if choice == "null":
        return NullDriver(sys.platform, "the null driver was explicitly selected")

    return NullDriver(sys.platform, f"unknown driver backend {choice!r}")


__all__ = ["ComputerDriver", "InputResult", "NullDriver", "ScreenFrame", "available_backend", "build_driver"]
