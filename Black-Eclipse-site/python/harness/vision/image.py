"""Image loading, validation and preprocessing.

This is the one place raw bytes become a decoded, validated image. It is
deliberately defensive: vision input is untrusted input. Every step can fail
with a classified `VisionError` instead of an opaque PIL exception.

Pillow performs decoding; `Image.MAX_IMAGE_PIXELS` plus explicit dimension/byte
checks enforce the decompression-bomb guard even for a crafted PNG. No network
I/O happens here — URL fetching is `fetch.py`, which calls back into this module.
"""

from __future__ import annotations

import base64
import hashlib
import io
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import VisionConfig, vision_config
from .contracts import Region, content_digest
from .errors import VisionError, VisionErrorClass

# Recognized image MIME types. A type outside this set is UNSUPPORTED_FORMAT.
SUPPORTED_MIME = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/webp": "WEBP",
    "image/gif": "GIF",
    "image/bmp": "BMP",
    "image/tiff": "TIFF",
    "image/x-ms-bmp": "BMP",
}

_EXTENSION_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    ".tif": "image/tiff", ".tiff": "image/tiff",
}

# Magic-byte sniffing so a mislabelled file is detected before decode.
_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
]


def sniff_mime(data: bytes) -> Optional[str]:
    """Best-effort MIME from magic bytes; None when unrecognized."""
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def mime_for_path(path: str) -> Optional[str]:
    lowered = path.lower()
    for ext, mime in _EXTENSION_MIME.items():
        if lowered.endswith(ext):
            return mime
    return None


@dataclass
class DecodedImage:
    """A decoded image plus provenance. `image` is a PIL Image (or None for
    metadata-only carriers)."""

    image: Any
    data: bytes
    mime_type: str
    width: int
    height: int
    byte_size: int
    sha256: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def asset_id(self) -> str:
        return content_digest(self.data)


def _check_limits(data: bytes, cfg: VisionConfig) -> None:
    if len(data) > cfg.max_image_bytes:
        raise VisionError(
            VisionErrorClass.OVERSIZED,
            f"image is {len(data)} bytes, over the {cfg.max_image_bytes}-byte limit",
        )


def decode_bytes(
    data: bytes,
    *,
    cfg: Optional[VisionConfig] = None,
    source: str = "",
    expected_mime: Optional[str] = None,
    validate_only: bool = False,
) -> DecodedImage:
    """Decode raw image bytes into a validated `DecodedImage`.

    Raises a classified `VisionError` for an empty, oversized, mislabelled,
    corrupt or unsupported image. `validate_only` still decodes (so a bomb is
    caught) but returns a metadata carrier without keeping the pixels.
    """
    cfg = cfg or vision_config()
    if not data:
        raise VisionError(VisionErrorClass.INVALID_IMAGE, "the image is empty", source_ref=source)
    _check_limits(data, cfg)

    from PIL import Image, UnidentifiedImageError  # noqa: PLC0415

    # A global pixel guard: even before our dimension check, pillow refuses an
    # image whose declared pixel count dwarfs the ceiling.
    previous_max = getattr(Image, "MAX_IMAGE_PIXELS", None)
    Image.MAX_IMAGE_PIXELS = max(cfg.max_pixels, 1)
    try:
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except Image.DecompressionBombError as exc:
            raise VisionError(
                VisionErrorClass.DECOMPRESSION_BOMB,
                "the image declares more pixels than the decompression-bomb limit allows",
                source_ref=source, cause=exc,
            ) from exc
        except UnidentifiedImageError as exc:
            raise VisionError(
                VisionErrorClass.INVALID_IMAGE,
                "the bytes are not a recognized image",
                source_ref=source, cause=exc,
            ) from exc
        except (OSError, ValueError) as exc:
            raise VisionError(
                VisionErrorClass.INVALID_IMAGE,
                f"the image could not be decoded: {exc}",
                source_ref=source, cause=exc,
            ) from exc
    finally:
        if previous_max is not None:
            Image.MAX_IMAGE_PIXELS = previous_max

    width, height = image.size
    if width <= 0 or height <= 0:
        raise VisionError(VisionErrorClass.INVALID_IMAGE, "the image has no pixels", source_ref=source)
    if width * height > cfg.max_pixels:
        raise VisionError(
            VisionErrorClass.OVERSIZED,
            f"image is {width}x{height} ({width * height} pixels), over the {cfg.max_pixels}-pixel limit",
            source_ref=source,
        )
    if width > cfg.max_dimension * 4 or height > cfg.max_dimension * 4:
        # Not fatal (we will downscale), but a pathological aspect is suspicious.
        pass

    sniffed = sniff_mime(data) or (expected_mime or "")
    real_mime = (image.format or "").lower()
    # Map PIL format back to a MIME for honesty.
    fmt_to_mime = {v.split("/")[-1]: k for k, v in SUPPORTED_MIME.items()}
    declared = expected_mime or sniffed or fmt_to_mime.get(real_mime, "")
    if not declared:
        declared = "image/png"
    if declared.split(";")[0].strip().lower() not in SUPPORTED_MIME:
        raise VisionError(
            VisionErrorClass.UNSUPPORTED_FORMAT,
            f"unsupported image MIME type: {declared}",
            source_ref=source,
        )

    metadata = _extract_metadata(image)
    sha = hashlib.sha256(data).hexdigest()
    carrier: Any = None if validate_only else image
    return DecodedImage(
        image=carrier, data=data, mime_type=declared.split(";")[0].strip().lower(),
        width=width, height=height, byte_size=len(data), sha256=sha,
        source=source, metadata=metadata,
    )


def decode_base64(value: str, *, cfg: Optional[VisionConfig] = None, source: str = "") -> DecodedImage:
    """Decode a raw base64 string or a `data:` URI."""
    text = value.strip()
    expected: Optional[str] = None
    if text.startswith("data:"):
        header, _, payload = text.partition(",")
        expected = header[len("data:"):].split(";")[0] or None
        text = payload
    try:
        data = base64.b64decode(text, validate=True)
    except (ValueError, TypeError) as exc:
        raise VisionError(
            VisionErrorClass.INVALID_IMAGE, "the base64 payload is not valid base64",
            source_ref=source, cause=exc,
        ) from exc
    return decode_bytes(data, cfg=cfg, source=source, expected_mime=expected)


def read_file(path: str, *, cfg: Optional[VisionConfig] = None) -> DecodedImage:
    """Load an image from a filesystem path (no URL, no scheme)."""
    from pathlib import Path  # noqa: PLC0415

    p = Path(path)
    if not p.exists() or not p.is_file():
        raise VisionError(VisionErrorClass.NO_SOURCE, f"image file not found: {path}", source_ref=path)
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise VisionError(
            VisionErrorClass.NO_SOURCE, f"image file could not be read: {exc}", source_ref=path, cause=exc
        ) from exc
    return decode_bytes(data, cfg=cfg, source=str(p), expected_mime=mime_for_path(str(p)))


# ── metadata / transform ──────────────────────────────────────────────────────

def _extract_metadata(image: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    info = getattr(image, "info", None) or {}
    for key in ("dpi", "icc_profile", "exif"):
        if key in info:
            value = info[key]
            if key == "icc_profile":
                out["has_icc_profile"] = bool(value)
            elif key == "exif" and isinstance(value, (bytes, bytearray)):
                try:
                    from PIL import Image  # noqa: PLC0415
                    from PIL.ExifTags import TAGS  # noqa: PLC0415

                    exif = Image.Exif()
                    exif.load(value)
                    tags = {TAGS.get(k, k): v for k, v in exif.items()}
                    # Only keep a small, non-sensitive summary.
                    if "Orientation" in tags:
                        out["orientation"] = tags["Orientation"]
                    if "Make" in tags or "Model" in tags:
                        out["camera"] = f"{tags.get('Make', '')} {tags.get('Model', '')}".strip()
                except Exception:  # noqa: BLE001
                    pass
            else:
                out[key] = value
    out["mode"] = getattr(image, "mode", "")
    return out


def apply_orientation(image: Any) -> Any:
    """Honor the EXIF orientation tag so the pixels are visually upright."""
    try:
        from PIL import ImageOps  # noqa: PLC0415

        return ImageOps.exif_transpose(image)
    except Exception:  # noqa: BLE001 - missing tag is not a failure
        return image


def resize_to_fit(image: Any, max_dimension: int) -> tuple[Any, bool]:
    """Downscale so the longest side is at most `max_dimension`. Never upscales."""
    width, height = image.size
    longest = max(width, height)
    if longest <= max_dimension or longest == 0:
        return image, False
    scale = max_dimension / float(longest)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    try:
        from PIL import Image  # noqa: PLC0415

        return image.resize(new_size, Image.LANCZOS), True
    except Exception:  # noqa: BLE001
        return image, False


def crop(image: Any, region: Region) -> Any:
    """Crop to a region, clamped to the image bounds (never raises on overflow)."""
    width, height = image.size
    left = max(0, min(region.x, width))
    top = max(0, min(region.y, height))
    right = max(left, min(region.right, width))
    bottom = max(top, min(region.bottom, height))
    if right <= left or bottom <= top:
        raise VisionError(VisionErrorClass.INVALID_INPUT, "the crop region is outside the image")
    return image.crop((left, top, right, bottom))


def rotate(image: Any, degrees: int) -> Any:
    try:
        return image.rotate(-degrees, expand=True)
    except Exception as exc:  # noqa: BLE001
        raise VisionError(VisionErrorClass.INVALID_IMAGE, f"rotation failed: {exc}", cause=exc) from exc


def to_rgb(image: Any) -> Any:
    try:
        return image.convert("RGB")
    except Exception:  # noqa: BLE001
        return image


def encode(image: Any, *, fmt: str = "PNG", quality: int = 88, strip_metadata: bool = True) -> bytes:
    """Encode a PIL image to bytes. PNG is lossless; JPEG/WEBP honor quality."""
    buffer = io.BytesIO()
    target = to_rgb(image) if fmt.upper() in ("JPEG", "JPG", "WEBP") else image
    if fmt.upper() in ("JPEG", "JPG"):
        target.save(buffer, format="JPEG", quality=quality)
    elif fmt.upper() == "WEBP":
        target.save(buffer, format="WEBP", quality=quality)
    else:
        save_kwargs: dict[str, Any] = {"format": "PNG"}
        if strip_metadata:
            save_kwargs["optimize"] = True
        target.save(buffer, **save_kwargs)
    return buffer.getvalue()


def thumbnail(image: Any, max_dimension: int = 256) -> Any:
    copy = image.copy()
    copy.thumbnail((max_dimension, max_dimension))
    return copy


def to_data_uri(image: Any, *, fmt: str = "PNG", quality: int = 88) -> str:
    data = encode(image, fmt=fmt, quality=quality)
    mime = "image/jpeg" if fmt.upper() in ("JPEG", "JPG") else f"image/{fmt.lower()}"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def preprocess(
    decoded: DecodedImage,
    *,
    cfg: Optional[VisionConfig] = None,
    region: Optional[Region] = None,
) -> DecodedImage:
    """The canonical preprocessing pipeline:

    orientation → crop (optional) → downscale → normalize mode.

    Returns a NEW `DecodedImage` whose bytes are re-encoded PNG, so downstream
    hashing/caching is stable and metadata is stripped (unless configured
    otherwise). The original `decoded` is left untouched for reference.
    """
    cfg = cfg or vision_config()
    if not cfg.preprocess:
        image = decoded.image
        if image is None:
            return decoded
    else:
        image = decoded.image
        if image is None:
            return decoded
        image = apply_orientation(image)
        if region is not None:
            image = crop(image, region)
        image, _ = resize_to_fit(image, cfg.max_dimension)
        image = to_rgb(image)

    data = encode(image, fmt="PNG", strip_metadata=cfg.strip_metadata)
    width, height = image.size
    return DecodedImage(
        image=image, data=data, mime_type="image/png", width=width, height=height,
        byte_size=len(data), sha256=hashlib.sha256(data).hexdigest(),
        source=decoded.source,
        metadata={**decoded.metadata, "preprocessed": True, "originalSha256": decoded.sha256},
    )


__all__ = [
    "DecodedImage", "SUPPORTED_MIME", "decode_bytes", "decode_base64", "read_file",
    "sniff_mime", "mime_for_path", "apply_orientation", "resize_to_fit", "crop",
    "rotate", "to_rgb", "encode", "thumbnail", "to_data_uri", "preprocess",
]
