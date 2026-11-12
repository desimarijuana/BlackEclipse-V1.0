"""Effect tokens — bind an authorization decision to the exact effectful call.

Authorization answers *may this be done*. An effect token answers *is this the
exact thing that was authorized*: it is minted at the authorize seam and carries
a digest of the run, tool and arguments it was issued for. The tool executor
verifies it immediately before the handler runs, so a widened or replayed call
(a TOCTOU change between approval and execution, a token from another run, or a
token reused after its TTL) is refused.

Modes (`HARNESS_EFFECT_TOKENS`):
  * `off`     — no minting, no checks;
  * `shadow`  — DEFAULT. Mint and verify when a token is present; a missing or
                invalid token is recorded but does not block. This is the
                migration window, and it is visible, not silent;
  * `enforce` — every non-read call must carry a valid, unconsumed token; a
                missing/invalid token fails closed.

Tokens are HMAC-SHA256 over a compact JSON payload, using
`HARNESS_AUTH_SECRET` when configured. Zero-config still works: without a
secret the broker uses a random per-process key, so tokens are valid only inside
this process (which is exactly the lifetime they need).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

TOKEN_MODE_ENV = "HARNESS_EFFECT_TOKENS"
DEFAULT_TTL_S = 120.0
_MAX_TOKENS = 10_000


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def args_digest(args: dict[str, Any]) -> str:
    """A stable digest of the tool arguments an authorization was bound to."""
    canonical = json.dumps(
        args or {}, sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def token_mode() -> str:
    raw = (os.environ.get(TOKEN_MODE_ENV) or "").strip().lower()
    if raw in ("off", "0", "false", "no", "disabled", "none"):
        return "off"
    if raw in ("enforce", "required", "on", "1", "true", "yes"):
        return "enforce"
    return "shadow"


@dataclass(frozen=True)
class EffectVerdict:
    ok: bool
    reason: str = ""
    mode: str = "shadow"
    token_id: str = ""
    shadow: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "reason": self.reason, "mode": self.mode,
            "tokenId": self.token_id, "shadow": self.shadow,
        }


class EffectTokenBroker:
    """Issue, verify and (in enforce mode) consume single-use effect tokens."""

    def __init__(self, *, secret: Optional[str] = None, ttl_s: float = DEFAULT_TTL_S) -> None:
        self._explicit_secret = secret
        self._ephemeral = os.urandom(32)
        self._ttl_s = max(1.0, float(ttl_s))
        self._used: dict[str, float] = {}
        self._lock = threading.RLock()

    @property
    def key(self) -> bytes:
        secret = self._explicit_secret or (os.environ.get("HARNESS_AUTH_SECRET") or "").strip()
        if secret and len(secret) >= 16 and secret != "change-me-to-a-random-secret":
            return secret.encode("utf-8")
        return self._ephemeral

    def _sign(self, body: str) -> str:
        return _b64url_encode(
            hmac.new(self.key, body.encode("ascii"), hashlib.sha256).digest()
        )

    def issue(
        self,
        *,
        run_id: str,
        tool: str,
        args: dict[str, Any],
        tenant_id: Optional[str] = None,
        ttl_s: Optional[float] = None,
    ) -> str:
        now = time.time()
        ttl = max(1.0, float(ttl_s if ttl_s is not None else self._ttl_s))
        payload = {
            "id": hashlib.sha256(
                f"{run_id}:{tool}:{now}".encode("utf-8")
            ).hexdigest()[:16],
            "run": str(run_id or ""),
            "tool": str(tool or ""),
            "digest": args_digest(args),
            "tenant": str(tenant_id) if tenant_id else "",
            "iat": now,
            "exp": now + ttl,
        }
        body = _b64url_encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        return f"{body}.{self._sign(body)}"

    def verify(
        self,
        token: str,
        *,
        run_id: str,
        tool: str,
        args: dict[str, Any],
        tenant_id: Optional[str] = None,
        consume: bool = False,
    ) -> EffectVerdict:
        mode = token_mode()
        if not token or "." not in str(token):
            return EffectVerdict(False, "no effect token", mode)
        body, _, signature = str(token).partition(".")
        try:
            expected = self._sign(body)
        except Exception:  # noqa: BLE001 - malformed body is a refusal
            return EffectVerdict(False, "malformed effect token", mode)
        if not hmac.compare_digest(expected, signature):
            return EffectVerdict(False, "effect token signature is invalid", mode)
        try:
            payload = json.loads(_b64url_decode(body))
        except Exception:  # noqa: BLE001
            return EffectVerdict(False, "malformed effect token", mode)
        if not isinstance(payload, dict):
            return EffectVerdict(False, "malformed effect token", mode)
        token_id = str(payload.get("id") or "")
        if float(payload.get("exp") or 0) <= time.time():
            return EffectVerdict(False, "effect token expired", mode, token_id)
        if str(payload.get("run") or "") != str(run_id or ""):
            return EffectVerdict(False, "effect token is bound to another run", mode, token_id)
        if str(payload.get("tool") or "") != str(tool or ""):
            return EffectVerdict(False, "effect token is bound to another tool", mode, token_id)
        if str(payload.get("digest") or "") != args_digest(args):
            return EffectVerdict(False, "effect token does not match these arguments", mode, token_id)
        if str(payload.get("tenant") or "") != (str(tenant_id) if tenant_id else ""):
            return EffectVerdict(False, "effect token is bound to another tenant", mode, token_id)
        if consume:
            with self._lock:
                if token_id in self._used:
                    return EffectVerdict(False, "effect token already used", mode, token_id)
                self._used[token_id] = time.time()
                if len(self._used) > _MAX_TOKENS:
                    for stale in sorted(self._used, key=self._used.get)[: len(self._used) - _MAX_TOKENS]:
                        self._used.pop(stale, None)
        return EffectVerdict(True, "authorized by effect token", mode, token_id)

    def consume_all(self) -> None:
        with self._lock:
            self._used.clear()


_BROKER: Optional[EffectTokenBroker] = None
_BROKER_LOCK = threading.RLock()


def get_broker() -> EffectTokenBroker:
    global _BROKER
    with _BROKER_LOCK:
        if _BROKER is None:
            _BROKER = EffectTokenBroker()
        return _BROKER


def reset_broker(broker: Optional[EffectTokenBroker] = None) -> None:
    """Test seam: replace (or clear) the process broker."""
    global _BROKER
    with _BROKER_LOCK:
        _BROKER = broker


def issue_for_call(
    *, run_id: str, tool: str, args: dict[str, Any], tenant_id: Optional[str] = None,
) -> Optional[str]:
    """Mint a token for an authorized call, or None when token mode is off."""
    if token_mode() == "off":
        return None
    try:
        return get_broker().issue(
            run_id=run_id, tool=tool, args=args, tenant_id=tenant_id,
        )
    except Exception:  # noqa: BLE001 - minting must never break authorization
        return None


def attach_token(ctx: Any, *, run_id: str, tool: str, args: dict[str, Any],
                 tenant_id: Optional[str] = None) -> str:
    """Mint a token and attach it to the run context for the executor."""
    token = issue_for_call(run_id=run_id, tool=tool, args=args, tenant_id=tenant_id) or ""
    try:
        setattr(ctx, "effect_token", token)
    except Exception:  # noqa: BLE001 - a frozen/foreign ctx simply carries no token
        pass
    return token


def enforce_call(ctx: Any, tool: str, args: dict[str, Any]) -> EffectVerdict:
    """Verify the effect token for THIS call. Shadow mode records, never blocks."""
    mode = token_mode()
    if mode == "off":
        return EffectVerdict(True, "effect tokens are off", mode)
    token = getattr(ctx, "effect_token", None)
    verdict = get_broker().verify(
        str(token or ""),
        run_id=str(getattr(ctx, "run_id", "") or ""),
        tool=tool,
        args=args,
        tenant_id=getattr(ctx, "tenant_id", None),
        consume=mode == "enforce",
    )
    try:
        setattr(ctx, "effect_token_reason", verdict.reason)
    except Exception:  # noqa: BLE001
        pass
    if mode == "shadow" and not verdict.ok:
        return EffectVerdict(True, verdict.reason, mode, verdict.token_id, shadow=True)
    return verdict


__all__ = [
    "DEFAULT_TTL_S",
    "TOKEN_MODE_ENV",
    "EffectTokenBroker",
    "EffectVerdict",
    "args_digest",
    "attach_token",
    "enforce_call",
    "get_broker",
    "issue_for_call",
    "reset_broker",
    "token_mode",
]
