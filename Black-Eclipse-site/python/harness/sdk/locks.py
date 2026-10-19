"""Passphrase locks for user-owned resources.

A lock is a real gate, not a UI hint: the UI Engineering and Portfolio services
call `assert_allowed` before every mutation, so the SDK, the HTTP routes and
agent tools all obey it. Unlocking is a short-lived HMAC token carried in the
`X-Eclipse-Unlock` header (the HTTP middleware places it in a contextvar).
Tool runs have no request header, so a locked resource is read-only to agents
until the user unlocks it through this surface.

Passphrases are never stored: PBKDF2-HMAC-SHA256 with a per-lock salt. Tokens
are stateless and bound to the lock id + expiry; deleting the lock invalidates
every token because verification re-reads the lock row.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .model import SdkCreateLockInput, SdkLockView
from .store import SdkStore

UNLOCK_HEADER = "x-eclipse-unlock"
DEFAULT_TTL_SECONDS = 900
MIN_ITERATIONS = 200_000

unlock_token_var: ContextVar[Optional[str]] = ContextVar("eclipse_sdk_unlock_token", default=None)

_SECRET_KEY = "lock_token_secret"


class LockError(Exception):
    """A locked resource was mutated without a valid unlock token."""

    code = "SDK_LOCKED"
    status_code = 423

    def __init__(
        self,
        message: str,
        *,
        lock_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        hint: Optional[str] = None,
        code: Optional[str] = None,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.lock_id = lock_id
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.hint = hint
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class LockService:
    def __init__(self, store: SdkStore) -> None:
        self._store = store
        self._ttl = max(60, int(os.environ.get("HARNESS_SDK_UNLOCK_TTL", DEFAULT_TTL_SECONDS)))

    # ── create / read ────────────────────────────────────────────────────────

    def create(self, input_model: SdkCreateLockInput, *, actor: Optional[str] = None) -> SdkLockView:
        # Re-locking an already-locked resource requires unlocking it first;
        # otherwise anyone could replace the passphrase and defeat the gate.
        if self._store.get_lock_by_resource(input_model.resource_type, input_model.resource_id):
            self.assert_allowed(input_model.resource_type, input_model.resource_id, "write")
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", input_model.passphrase.encode("utf-8"), salt, MIN_ITERATIONS
        )
        row = self._store.create_lock(
            resource_type=input_model.resource_type,
            resource_id=input_model.resource_id,
            passphrase_hash=_b64(digest),
            salt=_b64(salt),
            iterations=MIN_ITERATIONS,
            label=input_model.label,
            hint=input_model.hint,
            created_by=actor,
        )
        return self._view(row)

    def list(self, *, resource_type: Optional[str] = None, resource_id: Optional[str] = None) -> list[SdkLockView]:
        return [self._view(row) for row in self._store.list_locks(resource_type=resource_type, resource_id=resource_id)]

    def get(self, lock_id: str) -> Optional[SdkLockView]:
        row = self._store.get_lock(lock_id)
        return self._view(row) if row else None

    def is_locked(self, resource_type: str, resource_id: str) -> bool:
        return self._store.get_lock_by_resource(resource_type, resource_id) is not None

    # ── unlock / remove ──────────────────────────────────────────────────────

    def unlock(self, lock_id: str, passphrase: str) -> dict[str, Any]:
        row = self._store.get_lock(lock_id)
        if row is None:
            raise LockError("lock not found", code="SDK_LOCK_NOT_FOUND", status_code=404)
        if not self._passphrase_matches(row, passphrase):
            raise LockError(
                "the passphrase is incorrect",
                lock_id=lock_id,
                resource_type=row["resourceType"],
                resource_id=row["resourceId"],
                hint=row.get("hint"),
                code="SDK_UNLOCK_DENIED",
                status_code=403,
            )
        token, expires_at = self._issue(row["id"])
        return {"success": True, "token": token, "expiresAt": expires_at, "lock": self._view(row).model_dump(by_alias=True)}

    def remove(self, lock_id: str, *, passphrase: Optional[str] = None, actor: Optional[str] = None) -> bool:
        row = self._store.get_lock(lock_id)
        if row is None:
            raise LockError("lock not found", code="SDK_LOCK_NOT_FOUND", status_code=404)
        token = unlock_token_var.get()
        authorized = bool(token and self._verify_token(lock_id, token) == lock_id)
        if not authorized and passphrase is not None:
            authorized = self._passphrase_matches(row, passphrase)
        if not authorized:
            raise LockError(
                "unlock the resource before removing its lock",
                lock_id=lock_id,
                resource_type=row["resourceType"],
                resource_id=row["resourceId"],
                hint=row.get("hint"),
            )
        return self._store.delete_lock(lock_id)

    # ── enforcement ──────────────────────────────────────────────────────────

    def assert_allowed(
        self,
        resource_type: str,
        resource_id: str,
        action: str = "write",
        *,
        token: Optional[str] = None,
    ) -> Optional[SdkLockView]:
        """Raise `LockError` when a lock exists and the caller has no valid token."""
        row = self._store.get_lock_by_resource(resource_type, resource_id)
        if row is None:
            return None
        supplied = token if token is not None else unlock_token_var.get()
        if supplied and self._verify_token(row["id"], supplied) == row["id"]:
            return self._view(row)
        raise LockError(
            f'"{resource_id}" is locked ({action}); unlock it first',
            lock_id=row["id"],
            resource_type=resource_type,
            resource_id=resource_id,
            hint=row.get("hint"),
        )

    # ── token plumbing ───────────────────────────────────────────────────────

    def _secret(self) -> bytes:
        raw = self._store.get_meta(_SECRET_KEY)
        if not raw:
            raw = secrets.token_hex(32)
            self._store.set_meta(_SECRET_KEY, raw)
        return raw.encode("ascii")

    def _issue(self, lock_id: str) -> tuple[str, str]:
        expires = datetime.now(timezone.utc) + timedelta(seconds=self._ttl)
        payload = _b64(json.dumps({"lockId": lock_id, "exp": int(expires.timestamp())}, separators=(",", ":")).encode("utf-8"))
        signature = _b64(hmac.new(self._secret(), payload.encode("ascii"), hashlib.sha256).digest())
        return f"{payload}.{signature}", expires.isoformat()

    def _verify_token(self, lock_id: str, token: str) -> Optional[str]:
        try:
            payload, signature = token.split(".", 1)
        except ValueError:
            return None
        expected = _b64(hmac.new(self._secret(), payload.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            data = json.loads(_unb64(payload))
        except (ValueError, json.JSONDecodeError):
            return None
        if data.get("lockId") != lock_id:
            return None
        try:
            expires = int(data.get("exp", 0))
        except (TypeError, ValueError):
            return None
        if expires < int(datetime.now(timezone.utc).timestamp()):
            return None
        return lock_id

    def _passphrase_matches(self, row: dict[str, Any], passphrase: str) -> bool:
        try:
            salt = _unb64(row["salt"])
            expected = _unb64(row["passphraseHash"])
            iterations = int(row.get("iterations") or MIN_ITERATIONS)
        except (KeyError, ValueError):
            return False
        digest = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(digest, expected)

    @staticmethod
    def _view(row: dict[str, Any]) -> SdkLockView:
        return SdkLockView(
            id=row["id"],
            resource_type=row["resourceType"],
            resource_id=row["resourceId"],
            label=row.get("label"),
            hint=row.get("hint"),
            created_by=row.get("createdBy"),
            created_at=row["createdAt"],
            updated_at=row["updatedAt"],
        )


_SINGLETON: Optional[LockService] = None


def get_lock_service() -> Optional[LockService]:
    return _SINGLETON


def set_lock_service(service: Optional[LockService]) -> None:
    global _SINGLETON
    _SINGLETON = service


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "LockError",
    "LockService",
    "UNLOCK_HEADER",
    "get_lock_service",
    "set_lock_service",
    "unlock_token_var",
]
