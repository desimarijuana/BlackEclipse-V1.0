"""The honest null accessibility provider."""

from __future__ import annotations

from typing import Any, Optional

from ..models import AXNode
from .base import AXProvider


class NullAXProvider(AXProvider):
    id = "null"
    available = False

    def __init__(self, reason: str = "") -> None:
        self.reason = reason or "no accessibility backend is available on this platform"

    def tree(self, window_id: Optional[str] = None) -> Optional[AXNode]:
        return None

    def describe(self) -> dict[str, Any]:
        return {"provider": "null", "available": False, "reason": self.reason}


__all__ = ["NullAXProvider"]
