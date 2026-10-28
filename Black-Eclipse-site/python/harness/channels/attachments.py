"""Outbound attachment loading and size/SSRF guards.

A channel may send a file the operator supplied as bytes (`contentBase64`) or
as an HTTPS URL. We never fetch arbitrary schemes, never follow a redirect to a
different scheme, and never read more than `MAX_ATTACHMENT_BYTES`.
"""

from __future__ import annotations

import base64
import binascii
from typing import Optional
from urllib.parse import urlparse

import httpx

from .model import Attachment

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)


def sanitize_filename(name: str, fallback: str = "attachment") -> str:
    raw = str(name or "").replace("\\", "/").split("/")[-1].strip()
    return raw[:180] or fallback


def attachment_from_api(
    *,
    name: str = "",
    mime_type: str = "",
    url: str = "",
    content_base64: str = "",
) -> Attachment:
    """Build an Attachment from the operator API without trusting its size."""
    data: Optional[bytes] = None
    if content_base64:
        try:
            data = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError):
            data = None
    if data is not None and len(data) > MAX_ATTACHMENT_BYTES:
        data = None
    return Attachment(
        name=sanitize_filename(name),
        mime_type=str(mime_type or "").strip(),
        url=str(url or "").strip(),
        size=len(data) if data is not None else None,
        data=data,
    )


async def read_attachment(attachment: Attachment) -> Optional[bytes]:
    """Return attachment bytes from memory or a bounded HTTPS fetch."""
    if attachment.data is not None:
        return attachment.data if len(attachment.data) <= MAX_ATTACHMENT_BYTES else None
    url = str(attachment.url or "").strip()
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    return None
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > MAX_ATTACHMENT_BYTES:
                    return None
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_ATTACHMENT_BYTES:
                        return None
                    chunks.append(chunk)
                return b"".join(chunks) or None
    except Exception:  # noqa: BLE001 - a fetch failure is a reported send failure
        return None


__all__ = [
    "MAX_ATTACHMENT_BYTES",
    "attachment_from_api",
    "read_attachment",
    "sanitize_filename",
]
