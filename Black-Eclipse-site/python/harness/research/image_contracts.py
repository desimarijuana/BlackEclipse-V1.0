"""Normalized internet-image-search result contract + run collector.

This is the Python half of the shared, versioned `ImageSearchResult` contract
(the TypeScript half lives in `src/lib/image-search.ts`). It is deliberately
small and dependency-free: the image-search providers and the SSRF-hardened
transport live in the front door (TypeScript); this module only validates and
bounds what crosses the bridge, and collects a run-level blob the chat renders.

Invariants:
    * An image results ONLY when it has a safe, direct, http(s) image URL. A
      source page is not an image and is never presented as one.
    * Optional fields are omitted/None — never a fabricated placeholder.
    * Source attribution (source page, domain, creator/license) is preserved.
    * Retrieved content is untrusted data; nothing here executes or trusts it.
"""

from __future__ import annotations

import ipaddress
from typing import Any, Optional
from urllib.parse import urlparse

IMAGE_RESULT_SCHEMA_VERSION = "1.0"

MAX_IMAGES = 24
MAX_TITLE_CHARS = 300
MAX_ALT_CHARS = 500
MAX_ATTRIBUTION_CHARS = 500

_ALLOWED_VALIDATION = {"unvalidated", "metadata_ok", "verified", "rejected"}

_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost")
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"}


def _is_private_literal(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


def _safe_image_url(url: str) -> bool:
    """Offline URL guard for an image: http(s) only, no credentials, no private
    or loopback destinations. DNS/rebinding is the transport's job (the front
    door's `safeGet`); this rejects the obvious literal cases before a result is
    ever accepted."""
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if parsed.username or parsed.password:
        return False
    if host in _LOOPBACK_HOSTS or host.endswith(_BLOCKED_SUFFIXES):
        return False
    if _is_private_literal(host):
        return False
    return True


def _str(value: Any, limit: int) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text[:limit]


def _dim(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return None


def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:  # noqa: BLE001
        return ""


def normalize_image(raw: Any, *, provider: str = "") -> Optional[dict[str, Any]]:
    """Validate and bound ONE candidate into the normalized contract.

    Returns None when the candidate has no safe direct image URL — an unusable
    candidate is dropped, never repaired into a fake image.
    """
    if not isinstance(raw, dict):
        return None
    image_url = _str(raw.get("imageUrl") or raw.get("image_url") or raw.get("src"), 2048)
    if not image_url:
        return None
    if not _safe_image_url(image_url):
        return None

    thumbnail = _str(raw.get("thumbnailUrl") or raw.get("thumbnail_url"), 2048)
    if thumbnail:
        if not _safe_image_url(thumbnail):
            thumbnail = None

    source_url = _str(raw.get("sourceUrl") or raw.get("source_url") or raw.get("sourcePage"), 2048)
    if source_url and not _safe_image_url(source_url):
        source_url = None

    result_provider = _str(raw.get("provider"), 64) or provider or "unknown"
    validation = _str(raw.get("validationStatus") or raw.get("validation_status"), 32)
    if validation not in _ALLOWED_VALIDATION:
        validation = "metadata_ok"

    return {
        "id": _str(raw.get("id"), 128) or f"{result_provider}:{hash(image_url)}",
        "imageUrl": image_url,
        "thumbnailUrl": thumbnail,
        "sourceUrl": source_url,
        "title": _str(raw.get("title"), MAX_TITLE_CHARS) or _domain(image_url) or "Image",
        "altText": _str(raw.get("altText") or raw.get("alt_text") or raw.get("alt"), MAX_ALT_CHARS),
        "sourceDomain": _str(raw.get("sourceDomain") or raw.get("source_domain"), 255) or _domain(source_url or image_url),
        "width": _dim(raw.get("width")),
        "height": _dim(raw.get("height")),
        "mimeType": _str(raw.get("mimeType") or raw.get("mime_type"), 64),
        "provider": result_provider,
        "retrievedAt": _str(raw.get("retrievedAt") or raw.get("retrieved_at"), 64) or _now(),
        "attribution": _str(raw.get("attribution"), MAX_ATTRIBUTION_CHARS),
        "validationStatus": validation,
    }


def normalize_images(raw_list: Any, *, provider: str = "") -> list[dict[str, Any]]:
    """Normalize a list of candidates, deduplicating by direct image URL."""
    if not isinstance(raw_list, (list, tuple)):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_list:
        normalized = normalize_image(raw, provider=provider)
        if normalized is None:
            continue
        key = normalized["imageUrl"].lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
        if len(out) >= MAX_IMAGES:
            break
    return out


def validate_image_result(raw: Any) -> dict[str, Any]:
    """Offline validation of image metadata before a result is shown.

    Network reachability is intentionally NOT asserted here (that would be a
    fabricated claim): the UI's `<img>` load + broken-image fallback handles the
    live transport. This function validates URL safety, dimensions and MIME
    consistency, and rejects a result it cannot vouch for.
    """
    normalized = normalize_image(raw)
    if normalized is None:
        return {
            "ok": False,
            "status": "rejected",
            "reason": "no safe direct image URL",
        }
    reasons: list[str] = []
    width, height = normalized["width"], normalized["height"]
    if (width is None) != (height is None):
        reasons.append("incomplete dimensions")
    mime = normalized["mimeType"]
    if mime and not mime.startswith("image/"):
        reasons.append(f"non-image mime type {mime!r}")
    normalized["validationStatus"] = "metadata_ok" if not reasons else "rejected"
    return {
        "ok": not reasons,
        "status": normalized["validationStatus"],
        "result": normalized,
        "reasons": reasons,
    }


class ImageCollector:
    """Run-level collection of validated image results.

    Mirrors `vision.collector.VisionCollector`: a derived read model over the
    image results a run actually produced. It never fabricates a result, and an
    empty run carries no blob.
    """

    def __init__(self) -> None:
        self._results: list[dict[str, Any]] = []
        self._seen: set[str] = set()
        self._failures: list[dict[str, Any]] = []

    def add(self, payload: Any) -> None:
        """Record one result or a list of them (best-effort)."""
        try:
            if isinstance(payload, (list, tuple)):
                for item in payload:
                    self._add_one(item)
            elif isinstance(payload, dict) and isinstance(payload.get("images"), list):
                for item in payload["images"]:
                    self._add_one(item)
            else:
                self._add_one(payload)
        except Exception:  # noqa: BLE001 - collection must never break a run
            return

    def _add_one(self, item: Any) -> None:
        if isinstance(item, dict) and item.get("ok") is False and item.get("status") == "rejected":
            if len(self._failures) < MAX_IMAGES:
                self._failures.append({"reason": item.get("reason") or "rejected"})
            return
        normalized = normalize_image(item)
        if normalized is None:
            return
        key = normalized["imageUrl"].lower().rstrip("/")
        if key in self._seen:
            return
        if len(self._results) >= MAX_IMAGES:
            return
        self._seen.add(key)
        self._results.append(normalized)

    def has_content(self) -> bool:
        return bool(self._results)

    def to_blob(self) -> Optional[dict[str, Any]]:
        if not self.has_content():
            return None
        return {
            "type": "images",
            "schemaVersion": IMAGE_RESULT_SCHEMA_VERSION,
            "status": "collected",
            "count": len(self._results),
            "results": self._results,
            "failures": self._failures or None,
        }


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def hash(value: str) -> str:
    import hashlib

    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


__all__ = [
    "IMAGE_RESULT_SCHEMA_VERSION",
    "MAX_IMAGES",
    "ImageCollector",
    "normalize_image",
    "normalize_images",
    "validate_image_result",
]
