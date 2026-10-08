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
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
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

    if choice == "linux":
        if sys.platform.startswith("linux"):
            from .linux import LinuxX11Driver  # noqa: PLC0415

            return LinuxX11Driver()
        return NullDriver(sys.platform, "the linux driver is only available on Linux")

    if choice == "macos":
        if sys.platform == "darwin":
            from .macos import MacOSDriver  # noqa: PLC0415

            return MacOSDriver()
        return NullDriver(sys.platform, "the macos driver is only available on macOS")

    if choice == "wayland":
        if sys.platform.startswith("linux"):
            from .wayland import WaylandDriver  # noqa: PLC0415

            return WaylandDriver()
        return NullDriver(sys.platform, "the wayland driver is only available on Linux")

    if choice == "window":
        # The contained-window driver needs a base driver + a window id; a bare
        # selection is an honest null (the provisioner builds it correctly).
        return NullDriver(sys.platform, "the window driver is built by a desktop provisioner")

    if choice == "null":
        return NullDriver(sys.platform, "the null driver was explicitly selected")

    return NullDriver(sys.platform, f"unknown driver backend {choice!r}")


__all__ = ["ComputerDriver", "InputResult", "NullDriver", "ScreenFrame", "available_backend", "build_driver"]
