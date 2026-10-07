"""Vision engine contract.

The Computer Use engine does not care which model performs visual reasoning; it
only cares that the backend can answer a bounded visual question about a frame
and return located elements. A backend that cannot (no model configured, no
image support) reports `available: false` honestly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..models import Bounds


@dataclass
class LocatedElement:
    label: str
    role: str
    bounds: Optional[Bounds] = None
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label, "role": self.role,
            "bounds": self.bounds.to_dict() if self.bounds else None,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class VisionResult:
    available: bool
    backend: str = "none"
    text: str = ""
    elements: list[LocatedElement] = field(default_factory=list)
    confidence: float = 0.0
    local: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available, "backend": self.backend, "text": self.text,
            "elements": [e.to_dict() for e in self.elements],
            "confidence": round(self.confidence, 2), "local": self.local, "error": self.error,
        }


class VisionEngine:
    """Base vision engine. `available` and `local` are honest capability flags."""

    id = "none"
    available = False
    local = True

    async def locate(self, image: Any, query: str, *, bounds: Optional[Bounds] = None) -> VisionResult:
        return VisionResult(available=False, backend=self.id, error="no vision model is configured")

    async def describe(self, image: Any, *, bounds: Optional[Bounds] = None) -> VisionResult:
        return VisionResult(available=False, backend=self.id, error="no vision model is configured")

    def describe_backend(self) -> dict[str, Any]:
        return {"backend": self.id, "available": self.available, "local": self.local}


__all__ = ["LocatedElement", "VisionEngine", "VisionResult"]
