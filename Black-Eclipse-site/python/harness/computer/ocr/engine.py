"""OCR contract + result shapes.

`OCRResult` supports text extraction, coordinates, confidence and line/word
grouping (and a light table-ish grouping via line clustering), so a financial
screen can be turned into structured fields without a vision model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..models import Bounds


@dataclass
class OCRWord:
    text: str
    bounds: Bounds
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "bounds": self.bounds.to_dict(), "confidence": round(self.confidence, 2)}


@dataclass
class OCRLine:
    text: str
    bounds: Bounds
    confidence: float = 0.0
    words: list[OCRWord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text, "bounds": self.bounds.to_dict(),
            "confidence": round(self.confidence, 2),
            "words": [w.to_dict() for w in self.words],
        }


@dataclass
class OCRResult:
    available: bool
    engine: str = "null"
    text: str = ""
    lines: list[OCRLine] = field(default_factory=list)
    words: list[OCRWord] = field(default_factory=list)
    confidence: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available, "engine": self.engine, "text": self.text,
            "confidence": round(self.confidence, 2), "lineCount": len(self.lines),
            "wordCount": len(self.words), "error": self.error,
            "lines": [line.to_dict() for line in self.lines[:200]],
        }

    def find(self, needle: str, *, case_sensitive: bool = False) -> list[OCRWord]:
        target = needle if case_sensitive else needle.lower()
        out: list[OCRWord] = []
        for word in self.words:
            candidate = word.text if case_sensitive else word.text.lower()
            if target in candidate:
                out.append(word)
        return out


class OCREngine:
    """Base OCR engine. `available` is the honest capability flag."""

    id = "null"
    available = False

    def read(self, image: Any, *, bounds: Optional[Bounds] = None) -> OCRResult:
        return OCRResult(available=False, engine=self.id, error="no OCR engine is available")

    def read_path(self, path: str, *, bounds: Optional[Bounds] = None) -> OCRResult:
        return self.read(path, bounds=bounds)

    def describe(self) -> dict[str, Any]:
        return {"engine": self.id, "available": self.available}


__all__ = ["OCREngine", "OCRLine", "OCRResult", "OCRWord"]
