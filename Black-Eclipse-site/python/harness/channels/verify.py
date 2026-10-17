"""Inbound webhook signature verification.

A push provider (Slack, WhatsApp, generic) reaches Eclipse over a public HTTPS
endpoint, so the caller is an EXTERNAL service and cannot present the operator
token. Authenticity is proven by an HMAC over the RAW request body under a
per-channel secret configured by the operator. A missing/mismatched signature is
refused — never treated as an unauthenticated pass.

All comparisons are constant-time. Slack also carries a replay window (a stale
timestamp is refused).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

# Slack refuses requests whose timestamp is > 5 minutes from now.
SLACK_TOLERANCE_S = 300


def _hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_slack(
    signing_secret: str,
    *,
    timestamp: Optional[str],
    body: bytes,
    signature: Optional[str],
    tolerance_s: int = SLACK_TOLERANCE_S,
    now: Optional[float] = None,
) -> bool:
    """Verify a Slack Events API request (`X-Slack-Signature` v0 scheme)."""
    if not signing_secret or not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = now if now is not None else time.time()
    if abs(current - ts) > tolerance_s:
        return False
    base = f"v0:{ts}:".encode("utf-8") + body
    expected = "v0=" + _hmac_hex(signing_secret, base)
    return hmac.compare_digest(expected, signature)


def verify_whatsapp(app_secret: str, *, body: bytes, signature: Optional[str]) -> bool:
    """Verify a Meta WhatsApp webhook (`X-Hub-Signature-256` sha256 scheme)."""
    if not app_secret or not signature:
        return False
    expected = "sha256=" + _hmac_hex(app_secret, body)
    return hmac.compare_digest(expected, signature)


def verify_generic(secret: str, *, body: bytes, signature: Optional[str]) -> bool:
    """Verify a generic webhook (`X-Eclipse-Signature` sha256=<hex>)."""
    if not secret or not signature:
        return False
    provided = signature[7:] if signature.startswith("sha256=") else signature
    expected = _hmac_hex(secret, body)
    return hmac.compare_digest(expected, provided)


__all__ = [
    "SLACK_TOLERANCE_S",
    "verify_generic",
    "verify_slack",
    "verify_whatsapp",
]
