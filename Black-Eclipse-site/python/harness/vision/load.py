"""Source resolution: turn a `VisionInput` into a decoded image.

Handles path / URL / base64 / raw bytes / clipboard / screenshot. Document and
browser sources are resolved by their owning subsystems (which pass bytes in),
so this module stays free of a browser or PDF dependency.

Every branch fails with a classified `VisionError`; none falls back to a fake
image. Clipboard and screen capture use Pillow's platform grabbers, and report
an honest `UNSUPPORTED_SOURCE` where the platform cannot provide them.
"""

from __future__ import annotations

import io
from typing import Optional

from .config import VisionConfig, vision_config
from .contracts import Region, VisionInput
from .errors import VisionError, VisionErrorClass
from .image import DecodedImage, decode_base64, decode_bytes, read_file


async def resolve_source(
    input: VisionInput,
    *,
    cfg: Optional[VisionConfig] = None,
    raw_bytes: Optional[bytes] = None,
) -> DecodedImage:
    """Resolve `input` into a decoded image.

    `raw_bytes` lets a caller (the browser/document subsystem, or a test) supply
    bytes directly while still declaring the source kind for provenance.
    """
    cfg = cfg or vision_config()
    kind = input.source_kind

    if raw_bytes is not None:
        return decode_bytes(raw_bytes, cfg=cfg, source=input.source or kind, expected_mime=input.options.get("mime"))

    if kind == "path":
        return read_file(input.source, cfg=cfg)
    if kind == "url":
        from .fetch import fetch_url  # noqa: PLC0415

        return await fetch_url(input.source, cfg=cfg)
    if kind == "base64":
        return decode_base64(input.source, cfg=cfg)
    if kind == "bytes":
        # `source` is expected to already be bytes (kept as an escaped payload).
        data = input.source if isinstance(input.source, (bytes, bytearray)) else None
        if data is None:
            raise VisionError(VisionErrorClass.INVALID_INPUT, "bytes source requires raw bytes")
        return decode_bytes(bytes(data), cfg=cfg)
    if kind == "clipboard":
        return _decode_clipboard(cfg)
    if kind == "screenshot":
        return _capture_screen(cfg, input.region)
    if kind in ("browser", "document"):
        raise VisionError(
            VisionErrorClass.UNSUPPORTED_SOURCE,
            f"the {kind!r} source must be resolved by its owning subsystem (pass raw_bytes)",
            source_ref=input.source,
        )
    raise VisionError(VisionErrorClass.INVALID_INPUT, f"unknown source kind: {kind!r}")


def _encode_pil(image: object, cfg: VisionConfig) -> tuple[bytes, str]:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), "image/png"


def _decode_clipboard(cfg: VisionConfig) -> DecodedImage:
    try:
        from PIL import Image, ImageGrab  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise VisionError(
            VisionErrorClass.UNSUPPORTED_SOURCE, "clipboard access requires Pillow", cause=exc
        ) from exc
    try:
        grabbed = ImageGrab.grabclipboard()
    except Exception as exc:  # noqa: BLE001 - headless / no display / unsupported platform
        raise VisionError(
            VisionErrorClass.UNSUPPORTED_SOURCE,
            f"the clipboard image could not be read on this platform: {exc}",
            cause=exc,
        ) from exc
    if grabbed is None:
        raise VisionError(VisionErrorClass.NO_SOURCE, "the clipboard holds no image")
    if isinstance(grabbed, list):
        # A list of file paths was on the clipboard; take the first image file.
        for entry in grabbed:
            if isinstance(entry, str):
                try:
                    return read_file(entry, cfg=cfg)
                except VisionError:
                    continue
        raise VisionError(VisionErrorClass.NO_SOURCE, "the clipboard held no image files")
    if not isinstance(grabbed, Image.Image):
        raise VisionError(VisionErrorClass.NO_SOURCE, "the clipboard does not hold an image")
    data, mime = _encode_pil(grabbed.convert("RGB"), cfg)
    return decode_bytes(data, cfg=cfg, source="clipboard", expected_mime=mime)


def _capture_screen(cfg: VisionConfig, region: Optional[Region]) -> DecodedImage:
    try:
        from PIL import ImageGrab  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise VisionError(
            VisionErrorClass.UNSUPPORTED_SOURCE, "screen capture requires Pillow", cause=exc
        ) from exc
    bbox = None
    if region is not None:
        bbox = (region.x, region.y, region.right, region.bottom)
    try:
        grabbed = ImageGrab.grab(bbox=bbox, all_screens=True)
    except TypeError:
        # Older Pillow without `all_screens`; fall back to the primary display.
        try:
            grabbed = ImageGrab.grab(bbox=bbox)
        except Exception as exc:  # noqa: BLE001
            raise VisionError(
                VisionErrorClass.UNSUPPORTED_SOURCE, f"screen capture failed: {exc}", cause=exc
            ) from exc
    except Exception as exc:  # noqa: BLE001 - headless / no display server
        raise VisionError(
            VisionErrorClass.UNSUPPORTED_SOURCE, f"screen capture is unavailable here: {exc}", cause=exc
        ) from exc
    data, mime = _encode_pil(grabbed.convert("RGB"), cfg)
    return decode_bytes(data, cfg=cfg, source="screenshot", expected_mime=mime)


__all__ = ["resolve_source"]
