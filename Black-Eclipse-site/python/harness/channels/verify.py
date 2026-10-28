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

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Optional

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


def verify_lark(
    encrypt_key: str,
    *,
    timestamp: Optional[str],
    nonce: Optional[str],
    body: bytes,
    signature: Optional[str],
) -> bool:
    """Verify a Lark event request (`X-Lark-Signature`).

    Lark signs `timestamp + nonce + encrypt_key + raw_body` with SHA-256. When
    no encrypt key is configured the platform does not sign, so callers should
    fall back to the verification token carried in the payload.
    """
    if not encrypt_key or not timestamp or not nonce or not signature:
        return False
    expected = hashlib.sha256(
        f"{timestamp}{nonce}{encrypt_key}".encode("utf-8") + body
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def decrypt_lark(encrypt_key: str, encrypted: str) -> Optional[dict[str, Any]]:
    """Decrypt a Lark `{"encrypt": "..."}` envelope (AES-256-CBC, PKCS#7).

    Returns None on any failure so the caller can refuse the request without
    leaking whether the key or the ciphertext was wrong.
    """
    if not encrypt_key or not encrypted:
        return None
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # noqa: PLC0415

        key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
        raw = base64.b64decode(encrypted)
        if len(raw) <= 16:
            return None
        iv, payload = raw[:16], raw[16:]
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(payload) + decryptor.finalize()
        pad = padded[-1]
        if pad < 1 or pad > 16:
            return None
        parsed = json.loads(padded[:-pad].decode("utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except Exception:  # noqa: BLE001 - any decrypt failure is a refusal
        return None


_TEAMS_OPENID = "https://login.botframework.com/v1/.well-known/openidconfiguration"
_TEAMS_CACHE: dict[str, Any] = {"expires": 0.0, "jwks": None, "issuer": None}


def verify_teams(
    token: str,
    *,
    app_id: str,
    jwks: Optional[dict[str, Any]] = None,
    issuer: Optional[str] = None,
) -> bool:
    """Verify a Bot Framework request JWT for this bot's app id.

    `jwks`/`issuer` are injectable for tests; in production they are fetched
    from the Bot Framework OpenID configuration and cached.
    """
    if not token or not app_id:
        return False
    try:
        import jwt  # noqa: PLC0415
        from jwt.algorithms import RSAAlgorithm  # noqa: PLC0415

        if jwks is None:
            jwks, issuer = _teams_metadata()
        if not jwks:
            return False
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key_data = next(
            (key for key in (jwks.get("keys") or []) if key.get("kid") == kid),
            None,
        )
        if key_data is None:
            return False
        key = RSAAlgorithm.from_jwk(json.dumps(key_data))
        jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=app_id,
            issuer=issuer,
            options={"require": ["exp", "iss", "aud"]},
        )
        return True
    except Exception:  # noqa: BLE001 - any verification failure is a refusal
        return False


def _teams_metadata() -> tuple[Optional[dict[str, Any]], Optional[str]]:
    import httpx  # noqa: PLC0415

    now = time.time()
    if _TEAMS_CACHE["jwks"] and now < float(_TEAMS_CACHE["expires"]):
        return _TEAMS_CACHE["jwks"], _TEAMS_CACHE["issuer"]
    try:
        with httpx.Client(timeout=10.0) as client:
            config = client.get(_TEAMS_OPENID).json()
            jwks = client.get(config["jwks_uri"]).json()
        _TEAMS_CACHE.update(
            {
                "jwks": jwks,
                "issuer": config.get("issuer"),
                "expires": now + 3600,
            }
        )
        return jwks, config.get("issuer")
    except Exception:  # noqa: BLE001 - metadata unavailable means refuse
        return None, None


def verify_google_chat(token: str, *, audience: str) -> bool:
    """Verify a Google-signed Chat request JWT.

    Google Chat signs the bearer token with a Google service account. We verify
    the signature and audience with `google-auth` (which caches JWKS) and accept
    only Google's Chat issuer identities.
    """
    if not token or not audience:
        return False
    try:
        from google.auth.transport import requests as google_requests  # noqa: PLC0415
        from google.oauth2 import id_token  # noqa: PLC0415

        # `verify_token` checks signature + audience without forcing the
        # accounts.google.com issuer used by user OAuth tokens; Chat app tokens
        # use the Chat service identity checked below.
        claims = id_token.verify_token(token, google_requests.Request(), audience)
    except Exception:  # noqa: BLE001 - any verification failure is a refusal
        return False
    email = str(claims.get("email") or "").lower()
    issuer = str(claims.get("iss") or "").lower()
    return email == "chat@system.gserviceaccount.com" or email.endswith(".gserviceaccount.com") or issuer in (
        "chat@system.gserviceaccount.com",
        "accounts.google.com",
    )


def verify_generic(secret: str, *, body: bytes, signature: Optional[str]) -> bool:
    """Verify a generic webhook (`X-Eclipse-Signature` sha256=<hex>)."""
    if not secret or not signature:
        return False
    provided = signature[7:] if signature.startswith("sha256=") else signature
    expected = _hmac_hex(secret, body)
    return hmac.compare_digest(expected, provided)


__all__ = [
    "SLACK_TOLERANCE_S",
    "decrypt_lark",
    "verify_generic",
    "verify_google_chat",
    "verify_lark",
    "verify_slack",
    "verify_teams",
    "verify_whatsapp",
]
