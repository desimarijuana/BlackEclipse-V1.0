"""The honest null driver.

On an unsupported platform, or when an operator selects the `null` backend, the
runtime is present but reports every desktop capability as unavailable. This is
the zero-config truth on a platform Eclipse cannot yet drive: agent runs that
need the desktop fail with `COMPUTER_UNAVAILABLE`, never a fake desktop.
"""

from __future__ import annotations

from typing import Any, Optional

from ..models import Capabilities, DriverContract
from .base import ComputerDriver


class NullDriver(ComputerDriver):
    id = "null"
    label = "Unavailable (no desktop driver)"

    def __init__(self, platform: str = "unknown", reason: str = "") -> None:
        self.platform = platform
        self.reason = reason or f"no desktop driver is implemented for {platform}"

    def contract(self) -> DriverContract:
        return DriverContract(platform=self.platform, name="null", capabilities=())

    def capabilities(self) -> Capabilities:
        return Capabilities(
            platform=self.platform,
            background_input=False,
            foreground_input=False,
            accessibility=False,
            screen_capture=False,
            multi_monitor=False,
            window_management=False,
            application_management=False,
            set_value=False,
            ocr=False,
            vision=False,
            finance_cua=False,
            headless_desktop=False,
            notes=[self.reason],
        )

    def health(self) -> dict[str, Any]:
        return {"driver": "null", "healthy": True, "platform": self.platform, "reason": self.reason}


__all__ = ["NullDriver"]
