"""Minimal, dependency-free Ed25519 verify + sign (RFC 8032).

The plugin platform needs a *public-key* publisher signature: the host holds only
a public key, so a stolen install directory cannot mint new signatures. No
cryptography package is required — this module implements the standard Edwards25519
group and the RFC 8032 signing/verification equations directly.

Correctness is pinned by the RFC 8032 test vector in `test_c6_plugin_signing.py`.
This module is used for plugin manifests only; it is not a general-purpose crypto
library.
"""

from __future__ import annotations

import hashlib

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P

_BX = 15112221349535400772501151409588531511454012693041857206046113283949847762202
_BY = 46316835694926478169428394003475163141307993866256225615783033603165251855960
_B = (_BX, _BY)


def _inv(x: int) -> int:
    return pow(x % _P, _P - 2, _P)


def _add(p: tuple[int, int] | None, q: tuple[int, int] | None) -> tuple[int, int] | None:
    if p is None:
        return q
    if q is None:
        return p
    x1, y1 = p
    x2, y2 = q
    denom = (_D * x1 * x2 * y1 * y2) % _P
    x3 = ((x1 * y2 + x2 * y1) * _inv(1 + denom)) % _P
    y3 = ((y1 * y2 + x1 * x2) * _inv(1 - denom)) % _P
    return (x3, y3)


def _mul(point: tuple[int, int] | None, scalar: int) -> tuple[int, int] | None:
    result: tuple[int, int] | None = None
    addend = point
    value = max(0, int(scalar))
    while value:
        if value & 1:
            result = _add(result, addend)
        addend = _add(addend, addend)
        value >>= 1
    return result


def encode_point(point: tuple[int, int]) -> bytes:
    x, y = point
    raw = bytearray(int(y).to_bytes(32, "little"))
    raw[31] |= (x & 1) << 7
    return bytes(raw)


def decode_point(raw: bytes) -> tuple[int, int] | None:
    if len(raw) != 32:
        return None
    value = int.from_bytes(raw, "little")
    sign = value >> 255
    y = value & ((1 << 255) - 1)
    if y >= _P:
        return None
    x2 = ((y * y - 1) * _inv(_D * y * y + 1)) % _P
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = (x * pow(2, (_P - 1) // 4, _P)) % _P
    if (x * x - x2) % _P != 0:
        return None
    if x == 0 and sign:
        return None
    if (x & 1) != sign:
        x = _P - x
    return (x, y)


def public_key(seed: bytes) -> bytes:
    """Derive the 32-byte public key from a 32-byte Ed25519 seed."""
    if len(seed) != 32:
        raise ValueError("an Ed25519 seed is 32 bytes")
    digest = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    point = _mul(_B, scalar)
    assert point is not None
    return encode_point(point)


def sign(seed: bytes, message: bytes) -> bytes:
    """Sign `message` with a 32-byte seed; returns the 64-byte signature."""
    if len(seed) != 32:
        raise ValueError("an Ed25519 seed is 32 bytes")
    digest = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    prefix = digest[32:]
    public = public_key(seed)
    nonce = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _L
    r_point = _mul(_B, nonce)
    assert r_point is not None
    r_encoded = encode_point(r_point)
    challenge = int.from_bytes(
        hashlib.sha512(r_encoded + public + message).digest(), "little"
    ) % _L
    s = (nonce + challenge * scalar) % _L
    return r_encoded + s.to_bytes(32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """Verify a 64-byte Ed25519 signature against a 32-byte public key."""
    if len(public) != 32 or len(signature) != 64:
        return False
    try:
        a_point = decode_point(public)
        r_point = decode_point(signature[:32])
    except Exception:  # noqa: BLE001 - malformed encodings are simply invalid
        return False
    if a_point is None or r_point is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    challenge = int.from_bytes(
        hashlib.sha512(signature[:32] + public + message).digest(), "little"
    ) % _L
    left = _mul(_B, s)
    right = _add(r_point, _mul(a_point, challenge))
    return left == right


__all__ = ["decode_point", "encode_point", "public_key", "sign", "verify"]
