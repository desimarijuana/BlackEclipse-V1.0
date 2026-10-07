"""A bounded, invalidated discovery cache.

A full `discover_application` walks manifests, a compose file and env files. It is
safe to cache for a short window, but it MUST be invalidated when a file that
changes the answer changes (a manifest, lockfile, compose file or `.env`). This is
a small mtime-keyed cache: a hit requires every watched file's size+mtime to match
the snapshot taken when it was filled.

It never caches a secret's VALUE (it caches the descriptor, which masks secrets)
and it never caches across a root change. Thread-safe; bounded to a small table.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

#: The files whose change invalidates a cached descriptor. A new manifest/lockfile
#: appearing is covered because the snapshot records the WHOLE set the cache saw:
#: the key includes each watched name's presence, size and mtime.
WATCHED_NAMES: tuple[str, ...] = (
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock",
    "tsconfig.json", "requirements.txt", "requirements-dev.txt", "pyproject.toml", "uv.lock",
    "poetry.lock", "Pipfile", "Pipfile.lock", "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
    "pom.xml", "build.gradle", "build.gradle.kts",
    "Dockerfile", "compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml",
    ".env", ".env.local", ".env.development", ".env.production", ".env.example",
)

DEFAULT_TTL_S = 5.0


@dataclass
class _Entry:
    descriptor: Any
    signature: tuple
    at: float


class DiscoveryCache:
    """An mtime-keyed descriptor cache, bounded and thread-safe."""

    def __init__(self, *, ttl_s: float = DEFAULT_TTL_S, max_entries: int = 32) -> None:
        self._ttl = max(0.0, float(ttl_s))
        self._max = max(1, int(max_entries))
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.RLock()

    def _signature(self, root: Path) -> tuple:
        items: list[tuple] = []
        for name in WATCHED_NAMES:
            path = root / name
            try:
                stat = path.stat()
                items.append((name, stat.st_size, int(stat.st_mtime_ns)))
            except OSError:
                items.append((name, -1, -1))
        # A bounded, presence-aware snapshot; a new file flips its tuple.
        return tuple(items)

    def get(self, root: Path) -> Optional[Any]:
        key = str(Path(root).resolve())
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._ttl and (time.monotonic() - entry.at) > self._ttl:
                self._entries.pop(key, None)
                return None
            if entry.signature != self._signature(Path(root)):
                self._entries.pop(key, None)
                return None
            return entry.descriptor

    def put(self, root: Path, descriptor: Any) -> None:
        key = str(Path(root).resolve())
        with self._lock:
            if len(self._entries) >= self._max and key not in self._entries:
                # Evict the oldest entry (small table; a linear scan is fine).
                oldest = min(self._entries, key=lambda k: self._entries[k].at)
                self._entries.pop(oldest, None)
            self._entries[key] = _Entry(descriptor=descriptor, signature=self._signature(Path(root)),
                                        at=time.monotonic())

    def get_or_compute(self, root: Path, compute: Callable[[], Any]) -> Any:
        cached = self.get(root)
        if cached is not None:
            return cached
        descriptor = compute()
        self.put(root, descriptor)
        return descriptor

    def invalidate(self, root: Optional[Path] = None) -> None:
        with self._lock:
            if root is None:
                self._entries.clear()
            else:
                self._entries.pop(str(Path(root).resolve()), None)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"entries": len(self._entries), "ttlS": self._ttl, "maxEntries": self._max}


__all__ = ["DEFAULT_TTL_S", "DiscoveryCache", "WATCHED_NAMES"]
