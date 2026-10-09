"""Per-tenant physical data isolation — one store per tenant.

The strongest isolation for a shared runtime is physical: each tenant's runs,
sessions, memory and events live in their own SQLite file under a tenant root,
so a query for tenant A can never return tenant B's rows even if a WHERE clause
is forgotten. This module is the ONE resolver from a tenant id to that tenant's
`AgentMemoryStore`.

The default store (`AgentMemoryStore()` at the process default path) remains the
single-tenant / operator store; tenant stores are created lazily on first use.

A tenant id is used in a filesystem path, so it is strictly sanitized (a hostile
id can never traverse out of the root).
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any, Optional

from ..persistence import AgentMemoryStore

_SAFE_TENANT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

TENANT_DB_FILENAME = "agent-memory.db"


class TenantIdError(ValueError):
    """A tenant id that is unsafe to use as a path / store key."""


def normalize_tenant(tenant_id: Optional[str]) -> Optional[str]:
    """Validate and normalize a tenant id, or None when absent.

    Raises `TenantIdError` for an unsafe id (path traversal, separators, or an
    empty/overlong value) — fail closed rather than risk writing outside the root.
    """
    if tenant_id is None:
        return None
    text = str(tenant_id).strip()
    if not text:
        return None
    if not _SAFE_TENANT.match(text):
        raise TenantIdError(f"unsafe tenant id: {tenant_id!r}")
    return text


def default_tenant_root() -> str:
    override = os.environ.get("BLACK_ECLIPSE_TENANT_DB_DIR")
    if override:
        return override
    return str(Path(".black-eclipse") / "tenants")


class TenantStoreRegistry:
    """Resolve (and cache) one `AgentMemoryStore` per tenant.

    Thread-safe; stores are created lazily. `path_for` is pure (no I/O) so the
    isolation contract is testable without opening a database.
    """

    def __init__(self, root: Optional[str] = None) -> None:
        self._root = root or default_tenant_root()
        self._stores: dict[str, AgentMemoryStore] = {}
        self._lock = threading.RLock()

    @property
    def root(self) -> str:
        return self._root

    def path_for(self, tenant_id: str) -> str:
        tenant = normalize_tenant(tenant_id)
        if tenant is None:
            raise TenantIdError("a tenant id is required")
        return str(Path(self._root) / tenant / TENANT_DB_FILENAME)

    def store_for(self, tenant_id: str) -> AgentMemoryStore:
        """The tenant's store, creating it (and its directory) on first use."""
        tenant = normalize_tenant(tenant_id)
        if tenant is None:
            raise TenantIdError("a tenant id is required")
        with self._lock:
            existing = self._stores.get(tenant)
            if existing is not None:
                return existing
            path = self.path_for(tenant)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            store = AgentMemoryStore(path)
            self._stores[tenant] = store
            return store

    def path_for_safe(self, tenant_id: Optional[str]) -> Optional[str]:
        """Non-raising variant: None for an absent/unsafe tenant."""
        try:
            return self.path_for(tenant_id) if tenant_id else None
        except TenantIdError:
            return None

    def known_tenants(self) -> list[str]:
        with self._lock:
            return sorted(self._stores)

    def close(self, tenant_id: str) -> bool:
        with self._lock:
            store = self._stores.pop(normalize_tenant(tenant_id) or "", None)
        if store is None:
            return False
        try:
            store.close()
        except Exception:  # noqa: BLE001
            pass
        return True

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"root": self._root, "tenants": sorted(self._stores)}


__all__ = [
    "TENANT_DB_FILENAME",
    "TenantIdError",
    "TenantStoreRegistry",
    "default_tenant_root",
    "normalize_tenant",
]
