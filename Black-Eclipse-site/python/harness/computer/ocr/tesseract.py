"""The Tesseract OCR engine (optional) and the honest null engine.

Tesseract is present only when BOTH the `pytesseract` package and the `tesseract`
binary are installed. When either is missing the null engine reports
`available: false` — Eclipse never pretends to have read text it did not.
"""

from __future__ import annotations

import shutil
from typing import Any, Optional

from ..models import Bounds
from .engine import OCREngine, OCRLine, OCRResult, OCRWord


class NullOCREngine(OCREngine):
    id = "null"
    available = False

    def __init__(self, reason: str = "") -> None:
        self.reason = reason or "no OCR engine is installed"

    def read(self, image: Any, *, bounds: Optional[Bounds] = None) -> OCRResult:
        return OCRResult(available=False, engine=self.id, error=self.reason)

    def describe(self) -> dict[str, Any]:
        return {"engine": "null", "available": False, "reason": self.reason}


class TesseractOCREngine(OCREngine):
    id = "tesseract"
    available = False

    def __init__(self) -> None:
        try:
            import pytesseract  # noqa: PLC0415

            self._pytesseract = pytesseract
            # Confirm the binary is reachable (pytesseract raises on a missing one).
            pytesseract.get_tesseract_version()
            self.available = True
        except Exception:  # noqa: BLE001 - absent package/binary is honest
            self._pytesseract = None
            self.available = False

    def read(self, image: Any, *, bounds: Optional[Bounds] = None) -> OCRResult:
        if not self.available:
            return OCRResult(available=False, engine=self.id, error="tesseract is not available")
        try:
            from pytesseract import Output  # noqa: PLC0415

            data = self._pytesseract.image_to_data(image, output_type=Output.DICT)
        except Exception as exc:  # noqa: BLE001
            return OCRResult(available=False, engine=self.id, error=str(exc)[:200])
        origin = bounds or Bounds(0, 0, getattr(image, "width", 0), getattr(image, "height", 0))
        words: list[OCRWord] = []
        line_map: dict[tuple[int, int, int], list[OCRWord]] = {}
        n = len(data.get("text", []))
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = 0.0
            if conf < 0:
                continue
            x = origin.x + int(data["left"][i])
            y = origin.y + int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
            word = OCRWord(text=text, bounds=Bounds(x, y, w, h), confidence=conf / 100.0)
            words.append(word)
            key = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
            line_map.setdefault(key, []).append(word)

        lines: list[OCRLine] = []
        for key in sorted(line_map.keys()):
            line_words = sorted(line_map[key], key=lambda w: w.bounds.x)
            if not line_words:
                continue
            xs = [w.bounds.x for w in line_words]
            ys = [w.bounds.y for w in line_words]
            rs = [w.bounds.right for w in line_words]
            bs = [w.bounds.bottom for w in line_words]
            line_bounds = Bounds(min(xs), min(ys), max(rs) - min(xs), max(bs) - min(ys))
            conf = sum(w.confidence for w in line_words) / len(line_words)
            lines.append(OCRLine(
                text=" ".join(w.text for w in line_words), bounds=line_bounds,
                confidence=conf, words=line_words,
            ))
        text = "\n".join(line.text for line in lines)
        confidence = sum(w.confidence for w in words) / len(words) if words else 0.0
        return OCRResult(
            available=True, engine=self.id, text=text, lines=lines, words=words,
            confidence=confidence,
        )

    def describe(self) -> dict[str, Any]:
        return {"engine": "tesseract", "available": self.available}


def build_ocr_engine(backend: str = "auto") -> OCREngine:
    """The best OCR engine available, or the honest null engine."""
    choice = (backend or "auto").strip().lower()
    if choice in ("none", "off", "disabled"):
        return NullOCREngine("OCR was disabled by configuration")
    if choice in ("auto", "tesseract"):
        engine = TesseractOCREngine()
        if engine.available:
            return engine
        return NullOCREngine(
            "Tesseract isn't installed (pip install pytesseract + the tesseract binary)"
            if shutil.which("tesseract") is None else "pytesseract isn't installed"
        )
    return NullOCREngine(f"unknown OCR backend {choice!r}")


__all__ = ["NullOCREngine", "TesseractOCREngine", "build_ocr_engine"]
