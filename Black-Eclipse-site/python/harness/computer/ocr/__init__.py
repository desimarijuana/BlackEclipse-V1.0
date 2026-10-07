"""OCR — a first-class subsystem, usable independently of any vision model.

`engine.py` defines the `OCREngine` contract and the result shapes (text with
word/line boxes and confidence). `tesseract.py` is a real engine when the
`pytesseract` package AND the `tesseract` binary are present; otherwise the null
engine reports `available: false` honestly and the runtime falls back to vision.

Financial extraction (`computer/finance/`) is a consumer of OCR, so OCR is kept
provider-agnostic and offline-capable.
"""

from __future__ import annotations

from .engine import OCRLine, OCRResult, OCRWord, OCREngine
from .tesseract import build_ocr_engine

__all__ = ["OCREngine", "OCRLine", "OCRResult", "OCRWord", "build_ocr_engine"]
