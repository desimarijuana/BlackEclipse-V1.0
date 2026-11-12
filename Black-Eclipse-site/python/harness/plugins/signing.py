"""Plugin manifest signing + install review gate (C6).

A plugin install is a supply-chain event. C6 adds two operator controls on top of
the existing checksum + trust level:

  * **Signature** — a `plugin.sig` sidecar (or an explicit signature argument)
    holding `hmac-sha256:<hex>` over the canonical manifest and the package
    content digest. `plugin.sig` is excluded from that digest, so signing is a
    stable second pass. `HARNESS_PLUGIN_REQUIRE_SIGNATURE=1` makes a missing or
    invalid signature a refusal (fail closed); without the flag a valid signature
    is recorded as `verification="signature"`.
  * **Review** — `HARNESS_PLUGIN_REQUIRE_REVIEW=1` requires the install call to
    carry `operator=True` (the operator's review acknowledgment). It does not
    pretend to be a human UI; it makes the existing operator decision mandatory.

The signing key is `HARNESS_PLUGIN_SIGNING_KEY`. With the requirement on and no
key configured, installation is refused — never silently downgraded to a checksum.
This is an operator/shared-secret scheme (publisher CI and host hold the same
key); public-key publisher signatures remain a follow-up.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Optional

SIGNATURE_FILE = "plugin.sig"
SIGNING_KEY_ENV = "HARNESS_PLUGIN_SIGNING_KEY"
TRUSTED_KEYS_ENV = "HARNESS_PLUGIN_TRUSTED_KEYS"
REQUIRE_SIGNATURE_ENV = "HARNESS_PLUGIN_REQUIRE_SIGNATURE"
REQUIRE_REVIEW_ENV = "HARNESS_PLUGIN_REQUIRE_REVIEW"
_PLACEHOLDER = "change-me-to-a-random-secret"
ED25519_PREFIX = "ed25519:"
HMAC_PREFIX = "hmac-sha256:"


def _flag(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on", "required")


def signature_required() -> bool:
    return _flag(os.environ.get(REQUIRE_SIGNATURE_ENV))


def review_required() -> bool:
    return _flag(os.environ.get(REQUIRE_REVIEW_ENV))


def signing_key() -> Optional[str]:
    value = (os.environ.get(SIGNING_KEY_ENV) or "").strip()
    if not value or value == _PLACEHOLDER or len(value) < 16:
        return None
    return value


def canonical_payload(manifest: Any, digest: str) -> bytes:
    """The exact bytes a signature covers (stable across platforms)."""
    data = {
        "id": str(getattr(manifest, "id", "") or ""),
        "version": str(getattr(manifest, "version", "") or ""),
        "publisher": str(getattr(manifest, "publisher_id", "") or ""),
        "permissions": sorted(str(p) for p in (getattr(manifest, "permissions", []) or [])),
        "digest": str(digest or ""),
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_manifest(manifest: Any, digest: str, *, key: Optional[str] = None) -> str:
    """Publisher-side helper: produce the HMAC `plugin.sig` value."""
    secret = key or signing_key()
    if not secret:
        raise ValueError(f"{SIGNING_KEY_ENV} must be set (>=16 chars) to sign a plugin")
    mac = hmac.new(secret.encode("utf-8"), canonical_payload(manifest, digest), hashlib.sha256)
    return f"{HMAC_PREFIX}{mac.hexdigest()}"


def trusted_public_keys() -> list[bytes]:
    """The operator's trusted Ed25519 public keys (hex, comma-separated)."""
    raw = (os.environ.get(TRUSTED_KEYS_ENV) or "").strip()
    keys: list[bytes] = []
    for item in raw.split(","):
        value = item.strip().split("=")[-1].strip()
        if not value:
            continue
        try:
            key = bytes.fromhex(value)
        except ValueError:
            continue
        if len(key) == 32:
            keys.append(key)
    return keys


def sign_manifest_ed25519(manifest: Any, digest: str, *, seed_hex: str) -> str:
    """Publisher-side helper: produce a public-key `plugin.sig` value."""
    from .ed25519 import sign  # noqa: PLC0415

    try:
        seed = bytes.fromhex(str(seed_hex or "").strip())
    except ValueError as exc:
        raise ValueError("the Ed25519 seed must be hex") from exc
    return ED25519_PREFIX + sign(seed, canonical_payload(manifest, digest)).hex()


def signature_scheme(signature: Optional[str]) -> str:
    value = str(signature or "").strip().lower()
    if value.startswith(ED25519_PREFIX):
        return "ed25519"
    if value.startswith(HMAC_PREFIX):
        return "hmac"
    return "unknown"


def verify_signature(
    manifest: Any, digest: str, signature: str, *, key: Optional[str] = None,
) -> bool:
    value = str(signature or "").strip()
    if not value:
        return False
    if signature_scheme(value) == "ed25519":
        from .ed25519 import verify  # noqa: PLC0415

        try:
            raw = bytes.fromhex(value[len(ED25519_PREFIX):])
        except ValueError:
            return False
        return any(verify(pub, canonical_payload(manifest, digest), raw)
                   for pub in trusted_public_keys())
    secret = key or signing_key()
    if not secret:
        return False
    try:
        expected = sign_manifest(manifest, digest, key=secret)
    except ValueError:
        return False
    return hmac.compare_digest(expected, value)


def read_signature(directory: Optional[Path]) -> Optional[str]:
    if directory is None:
        return None
    path = Path(directory) / SIGNATURE_FILE
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except (OSError, ValueError):
        return None


def check_install(
    manifest: Any,
    digest: str,
    *,
    operator: bool,
    directory: Optional[Path] = None,
    signature: Optional[str] = None,
) -> dict[str, Any]:
    """Evaluate the signature/review gate. Raises on a required-but-unsatisfied gate."""
    from .errors import PluginError  # noqa: PLC0415 - avoid an import cycle

    sig = (signature or read_signature(directory) or "").strip()
    scheme = signature_scheme(sig)
    signed = verify_signature(manifest, digest, sig)
    if signature_required() and not signed:
        has_material = (
            bool(trusted_public_keys()) if scheme == "ed25519"
            else signing_key() is not None
        )
        if not has_material:
            requirement = (
                f"{TRUSTED_KEYS_ENV} has no trusted Ed25519 key"
                if scheme == "ed25519"
                else f"{SIGNING_KEY_ENV} is not configured"
            )
            raise PluginError(
                "PLUGIN_SIGNING_UNAVAILABLE",
                f"{REQUIRE_SIGNATURE_ENV}=1 but {requirement}",
            )
        raise PluginError(
            "PLUGIN_SIGNATURE_INVALID",
            f"plugin {getattr(manifest, 'id', '')!r} has no valid signature",
        )
    if review_required() and not operator:
        raise PluginError(
            "PLUGIN_REVIEW_REQUIRED",
            f"plugin {getattr(manifest, 'id', '')!r} is unreviewed; "
            "install requires an explicit operator review",
        )
    return {
        "verification": "signature" if signed else "checksum",
        "signed": signed,
        "scheme": scheme if signed else None,
        "reviewed": bool(operator),
        "signatureRequired": signature_required(),
        "reviewRequired": review_required(),
    }


__all__ = [
    "REQUIRE_REVIEW_ENV",
    "REQUIRE_SIGNATURE_ENV",
    "SIGNATURE_FILE",
    "SIGNING_KEY_ENV",
    "TRUSTED_KEYS_ENV",
    "canonical_payload",
    "check_install",
    "read_signature",
    "review_required",
    "sign_manifest",
    "sign_manifest_ed25519",
    "signature_required",
    "signature_scheme",
    "signing_key",
    "trusted_public_keys",
    "verify_signature",
]
