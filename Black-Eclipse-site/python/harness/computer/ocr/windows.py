"""The Windows-native OCR engine.

Uses the operating system's own OCR (`Windows.Media.Ocr`) through the optional
`winsdk` package — no external binary, no download, and no cloud. When the
package (or a recognizer language) is missing, the engine reports
`available: false` with a fix, exactly like the Tesseract/null engines. Eclipse
never pretends to have read text it did not.

The WinRT OCR API is async; because the observation engine calls `read()`
synchronously, each call is driven to completion on a short-lived worker thread
with its own event loop. That keeps the async observation loop unblocked from
the WinRT scheduler's perspective while preserving the synchronous contract.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Optional

from ..models import Bounds
from .engine import OCREngine, OCRLine, OCRResult, OCRWord


def _winsdk_available() -> tuple[bool, str]:
    try:
        import winsdk  # noqa: F401, PLC0415

        return True, ""
    except Exception:  # noqa: BLE001
        return False, "the Windows OCR engine needs the 'winsdk' package (pip install winsdk)"


class WindowsOCREngine(OCREngine):
    id = "winocr"

    def __init__(self) -> None:
        ok, reason = _winsdk_available()
        self.available = False
        self.reason = reason
        if not ok:
            return
        try:
            from winsdk.windows.media.ocr import OcrEngine  # noqa: PLC0415

            if not OcrEngine.get_available_recognizer_languages():
                self.reason = "Windows has no OCR language pack installed"
                return
            self.available = True
        except Exception as exc:  # noqa: BLE001
            self.reason = f"the Windows OCR engine couldn't initialise ({str(exc)[:120]})"

    def read(self, image: Any, *, bounds: Optional[Bounds] = None) -> OCRResult:
        if not self.available:
            return OCRResult(available=False, engine=self.id, error=self.reason)
        if image is None:
            return OCRResult(available=False, engine=self.id, error="no frame to read")
        origin = bounds or Bounds(0, 0, getattr(image, "width", 0), getattr(image, "height", 0))
        try:
            lines = _run_blocking(self._recognize(image))
        except Exception as exc:  # noqa: BLE001 - an OCR miss is honest data
            return OCRResult(available=False, engine=self.id, error=str(exc)[:200])
        return _result_from_lines(lines, origin)

    async def _recognize(self, image: Any) -> list[OCRLine]:
        from winsdk.windows.globalization import Language  # noqa: PLC0415
        from winsdk.windows.media.ocr import OcrEngine  # noqa: PLC0415
        from winsdk.windows.graphics.imaging import (  # noqa: PLC0415
            SoftwareBitmap,
            BitmapPixelFormat,
            BitmapAlphaMode,
        )

        width, height = image.width, image.height
        rgba = image.convert("RGBA").tobytes()
        bitmap = SoftwareBitmap.create_copy_from_buffer(
            _to_buffer(rgba), BitmapPixelFormat.RGBA8, width, height, BitmapAlphaMode.STRAIGHT,
        )
        engine = OcrEngine.try_create_from_language(Language("en-US")) or OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            return []
        result = await engine.recognize_async(bitmap)
        lines: list[OCRLine] = []
        for line in result.lines:
            words: list[OCRWord] = []
            for word in line.words:
                rect = word.bounding_rect
                words.append(OCRWord(
                    text=str(word.text),
                    bounds=Bounds(int(rect.x), int(rect.y), int(rect.width), int(rect.height)),
                    confidence=0.8,  # WinRT OCR does not report per-word confidence
                ))
            if not words:
                continue
            xs = [w.bounds.x for w in words]
            ys = [w.bounds.y for w in words]
            rs = [w.bounds.right for w in words]
            bs = [w.bounds.bottom for w in words]
            lines.append(OCRLine(
                text=str(line.text), bounds=Bounds(min(xs), min(ys), max(rs) - min(xs), max(bs) - min(ys)),
                confidence=sum(w.confidence for w in words) / len(words), words=words,
            ))
        return lines

    def describe(self) -> dict[str, Any]:
        return {"engine": "winocr", "available": self.available,
                **({} if self.available else {"reason": self.reason})}


def _to_buffer(raw: bytes) -> Any:
    """Wrap raw bytes in a WinRT IBuffer via the .NET-compatible helper."""
    import winsdk.windows.security.cryptography as crypto  # noqa: PLC0415

    return crypto.CryptographicBuffer.create_from_byte_array(bytes(raw))


def _result_from_lines(lines: list[OCRLine], origin: Bounds) -> OCRResult:
    words = [w for line in lines for w in line.words]
    for word in words:
        word.bounds = Bounds(origin.x + word.bounds.x, origin.y + word.bounds.y,
                             word.bounds.width, word.bounds.height)
    for line in lines:
        line.bounds = Bounds(origin.x + line.bounds.x, origin.y + line.bounds.y,
                             line.bounds.width, line.bounds.height)
    text = "\n".join(line.text for line in lines)
    confidence = sum(w.confidence for w in words) / len(words) if words else 0.0
    return OCRResult(available=True, engine="winocr", text=text, lines=lines, words=words,
                     confidence=confidence,
                     error=None)


def _run_blocking(coro: Any, *, timeout: float = 20.0) -> Any:
    """Run a coroutine on a worker thread with its OWN event loop and block.

    The observation path is synchronous, so the WinRT async OCR is driven here
    on a separate thread — this avoids an `asyncio.run` clash with the running
    server loop while honouring the synchronous `OCREngine.read` contract.
    """
    box: dict[str, Any] = {}

    def _worker() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001
            box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError("Windows OCR timed out")
    if "error" in box:
        raise box["error"]
    return box.get("value")


__all__ = ["WindowsOCREngine"]
