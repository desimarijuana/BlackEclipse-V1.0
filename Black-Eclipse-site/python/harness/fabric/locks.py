"""Distributed (single-store advisory) locks for the Execution Fabric.

Redis is not present in this runtime; the ONE agent-memory SQLite connection is
the coordination point. A lock row carries an owner, a unique token, a TTL and an
expiry. Acquisition is atomic (expired locks are stealable), release is
ownership-checked by token (a lock can never be released by a non-owner), and a
lazy purge reclaims expired rows so no permanent lock can form.

Used to serialise: universe sync, price ingestion per symbol, migrations, plugin
actions and any effect that must not run twice concurrently.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Any, AsyncIterator, Optional

from .store import FabricStore


class LockNotAcquired(RuntimeError):
    """Raised by `acquire_or_raise` when a lock is held by another owner."""


class DistributedLockManager:
    def __init__(self, store: FabricStore, *, default_ttl_ms: int = 30_000) -> None:
        self._store = store
        self._default_ttl_ms = max(1000, int(default_ttl_ms))

    def try_acquire(
        self, name: str, *, owner: str, ttl_ms: Optional[int] = None,
    ) -> Optional[str]:
        """Acquire `name`. Returns the ownership token, or None if already held."""
        token = uuid.uuid4().hex
        ok = self._store.try_acquire_lock(
            name, owner=owner, token=token, ttl_ms=ttl_ms or self._default_ttl_ms,
        )
        return token if ok else None

    def acquire_or_raise(self, name: str, *, owner: str, ttl_ms: Optional[int] = None) -> str:
        token = self.try_acquire(name, owner=owner, ttl_ms=ttl_ms)
        if token is None:
            raise LockNotAcquired(f"lock {name!r} is held")
        return token

    def renew(self, name: str, *, token: str, ttl_ms: Optional[int] = None) -> bool:
        return self._store.renew_lock(name, token=token, ttl_ms=ttl_ms or self._default_ttl_ms)

    def release(self, name: str, *, token: str) -> bool:
        return self._store.release_lock(name, token=token)

    def held(self, name: str) -> Optional[dict[str, Any]]:
        return self._store.get_lock(name)

    def purge_expired(self) -> int:
        return self._store.purge_expired_locks()

    @contextlib.asynccontextmanager
    async def lock(
        self, name: str, *, owner: str, ttl_ms: Optional[int] = None, blocking: bool = True,
        wait_seconds: float = 5.0, poll_seconds: float = 0.05,
    ) -> AsyncIterator[str]:
        """Acquire/release around a block.

        With `blocking=False` a held lock raises `LockNotAcquired` immediately; with
        `blocking=True` it polls up to `wait_seconds` then raises. The lock is always
        released on exit (including on cancellation) so a crashed caller cannot leak
        it — and even a hard crash is bounded by the TTL.
        """
        import asyncio

        deadline = asyncio.get_event_loop().time() + max(0.0, wait_seconds)
        token: Optional[str] = None
        while True:
            token = self.try_acquire(name, owner=owner, ttl_ms=ttl_ms)
            if token is not None:
                break
            if not blocking or asyncio.get_event_loop().time() >= deadline:
                raise LockNotAcquired(f"lock {name!r} is held")
            await asyncio.sleep(max(0.01, poll_seconds))
        try:
            yield token
        finally:
            self.release(name, token=token)


__all__ = ["DistributedLockManager", "LockNotAcquired"]
