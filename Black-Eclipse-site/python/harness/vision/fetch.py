"""Safe URL image fetching (SSRF-guarded).

If image URLs are supported they must not become a way to reach the private
network. This module reuses the authoritative SSRF guard
(`harness.mcp.ssrf.check_outbound_url`, which resolves DNS and rejects private
addresses) and applies it to EVERY hop of a manually-followed redirect chain,
with a bounded redirect count and a byte ceiling enforced while streaming.

The download lands in memory only after the SSRF guard passes; the final bytes
still flow through `image.decode_bytes`, so a mislabelled or bomb payload is
rejected there too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import VisionConfig, vision_config
from .errors import VisionError, VisionErrorClass
from .image import DecodedImage, decode_bytes


@dataclass
class FetchResult:
    data: bytes
    content_type: str
    final_url: str
    redirects: int


def _check_url(url: str, cfg: VisionConfig, *, schemes: Optional[list[str]] = None) -> None:
    from ..mcp.ssrf import check_outbound_url  # noqa: PLC0415

    allowed = schemes or cfg.allowed_schemes
    scheme = url.split("://", 1)[0].lower() if "://" in url else ""
    if scheme and scheme not in allowed:
        raise VisionError(
            VisionErrorClass.SECURITY_BLOCKED, f"blocked URL scheme: {scheme or '(none)'}",
            source_ref=url,
        )
    safe, reason = check_outbound_url(url)
    if not safe:
        raise VisionError(
            VisionErrorClass.SECURITY_BLOCKED, f"URL refused by the network guard: {reason}",
            source_ref=url,
        )


async def fetch_url(
    url: str,
    *,
    cfg: Optional[VisionConfig] = None,
    expected_mime: Optional[str] = None,
) -> DecodedImage:
    """Fetch an image URL safely and decode it.

    Raises `SECURITY_BLOCKED` for a refused URL/hop, `NO_SOURCE` for a network
    or HTTP failure, `OVERSIZED` when the body exceeds the byte ceiling, and the
    decode errors from `decode_bytes`.
    """
    cfg = cfg or vision_config()
    if not cfg.allow_url_fetch:
        raise VisionError(VisionErrorClass.SECURITY_BLOCKED, "URL image fetching is disabled", source_ref=url)
    if not url:
        raise VisionError(VisionErrorClass.INVALID_INPUT, "no URL was provided")

    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise VisionError(
            VisionErrorClass.PROVIDER_UNAVAILABLE, "the HTTP client is unavailable", source_ref=url, cause=exc
        ) from exc

    result = await _fetch_bytes(url, cfg=cfg)
    mime = (result.content_type or "").split(";")[0].strip().lower()
    if mime and not mime.startswith("image/"):
        raise VisionError(
            VisionErrorClass.UNSUPPORTED_FORMAT,
            f"the URL did not return an image (content-type {mime!r})",
            source_ref=result.final_url,
        )
    return decode_bytes(
        result.data, cfg=cfg, source=result.final_url,
        expected_mime=expected_mime or (mime or None),
    )


async def _fetch_bytes(url: str, *, cfg: VisionConfig) -> FetchResult:
    import httpx  # noqa: PLC0415

    hops = 0
    current = url
    headers = {"User-Agent": "Eclipse-Vision/1.0", "Accept": "image/*"}
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=cfg.url_timeout_seconds,
    ) as client:
        while True:
            _check_url(current, cfg)
            try:
                response = await client.get(current, headers=headers)
            except httpx.HTTPError as exc:
                raise VisionError(
                    VisionErrorClass.NO_SOURCE, f"the image URL could not be fetched: {exc}",
                    source_ref=current, cause=exc,
                ) from exc
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise VisionError(
                        VisionErrorClass.NO_SOURCE, "a redirect response had no Location header", source_ref=current
                    )
                hops += 1
                if hops > cfg.max_redirects:
                    raise VisionError(
                        VisionErrorClass.SECURITY_BLOCKED,
                        f"too many redirects (over {cfg.max_redirects})", source_ref=url,
                    )
                current = httpx.URL(current).join(location).__str__()
                continue
            if response.status_code >= 400:
                raise VisionError(
                    VisionErrorClass.NO_SOURCE,
                    f"the image URL returned HTTP {response.status_code}", source_ref=current,
                )
            content_length = response.headers.get("content-length")
            if content_length and content_length.isdigit() and int(content_length) > cfg.max_image_bytes:
                raise VisionError(
                    VisionErrorClass.OVERSIZED,
                    f"the image is {content_length} bytes, over the {cfg.max_image_bytes}-byte limit",
                    source_ref=current,
                )
            data = response.content
            if len(data) > cfg.max_image_bytes:
                raise VisionError(
                    VisionErrorClass.OVERSIZED,
                    f"the image is {len(data)} bytes, over the {cfg.max_image_bytes}-byte limit",
                    source_ref=current,
                )
            return FetchResult(
                data=data,
                content_type=response.headers.get("content-type", ""),
                final_url=current,
                redirects=hops,
            )


__all__ = ["fetch_url", "FetchResult"]
