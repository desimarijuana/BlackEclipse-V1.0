"""Isolated, namespaced plugin storage: key/value, files and optional SQLite.

Every plugin gets its OWN storage boundary. A key/value namespace is always
available and scoped by plugin id, so one plugin can never read or write another
plugin's keys. File storage is confined to the plugin's own data directory (a
path that escapes that directory is refused), and an optional per-plugin SQLite
database lives there too.

Permissions are enforced here: file writes need `filesystem.write`, file reads
need `filesystem.read`, and the per-plugin SQLite database needs `database`.
The declarations in the manifest's `storage` block gate whether each surface is
available at all.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional

from .errors import PluginError
from .manifest import PluginManifest
from .paths import ensure_dir, plugin_data_dir
from .permissions import GrantedPermissions


class StorageError(PluginError):
    def __init__(self, code: str, message: str, **kwargs: Any) -> None:
        super().__init__(code, message, **kwargs)


class PluginStorage:
    def __init__(self, store: Any, manifest: PluginManifest, permissions: GrantedPermissions) -> None:
        self._store = store
        self._manifest = manifest
        self._permissions = permissions
        self._plugin_id = manifest.id
        self._sqlite_conns: dict[str, sqlite3.Connection] = {}

    # ── key/value ────────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None, *, namespace: str = "default") -> Any:
        value = self._store.kv_get(self._plugin_id, namespace, key)
        return default if value is None else value

    def set(self, key: str, value: Any, *, namespace: str = "default") -> None:
        self._store.kv_set(self._plugin_id, namespace, key, value)

    def delete(self, key: str, *, namespace: str = "default") -> None:
        self._store.kv_delete(self._plugin_id, namespace, key)

    def keys(self, *, namespace: str = "default") -> list[str]:
        return list(self._store.kv_list(self._plugin_id, namespace).keys())

    def all(self, *, namespace: str = "default") -> dict[str, Any]:
        return self._store.kv_list(self._plugin_id, namespace)

    # ── files ────────────────────────────────────────────────────────────────

    def _file_dir(self) -> Path:
        if not self._manifest.storage.files:
            raise StorageError("PLUGIN_STORAGE_UNAVAILABLE", "file storage is not declared by this plugin")
        return ensure_dir(plugin_data_dir(self._plugin_id, create=True) / "files")

    def _resolve(self, name: str) -> Path:
        base = self._file_dir().resolve()
        target = (base / name).resolve()
        if base != target and base not in target.parents:
            raise StorageError("PLUGIN_STORAGE_PATH_ESCAPE", f"path escapes plugin storage: {name!r}")
        return target

    def list_files(self) -> list[str]:
        if not self._manifest.storage.files:
            return []
        self._permissions.require("filesystem.read", "storage.list_files")
        base = self._file_dir()
        return sorted(
            str(p.relative_to(base)).replace("\\", "/")
            for p in base.rglob("*") if p.is_file()
        )

    def read_file(self, name: str) -> bytes:
        self._permissions.require("filesystem.read", "storage.read_file")
        path = self._resolve(name)
        if not path.exists():
            raise StorageError("PLUGIN_STORAGE_NOT_FOUND", f"no such file: {name!r}")
        return path.read_bytes()

    def write_file(self, name: str, data: bytes) -> str:
        self._permissions.require("filesystem.write", "storage.write_file")
        path = self._resolve(name)
        ensure_dir(path.parent)
        path.write_bytes(data if isinstance(data, (bytes, bytearray)) else str(data).encode("utf-8"))
        return str(path.relative_to(self._file_dir().resolve())).replace("\\", "/")

    def delete_file(self, name: str) -> bool:
        self._permissions.require("filesystem.write", "storage.delete_file")
        path = self._resolve(name)
        if path.exists() and path.is_file():
            path.unlink()
            return True
        return False

    # ── per-plugin sqlite ────────────────────────────────────────────────────

    def sqlite(self) -> sqlite3.Connection:
        self._permissions.require("database", "storage.sqlite")
        if not self._manifest.storage.sqlite:
            raise StorageError("PLUGIN_STORAGE_UNAVAILABLE", "sqlite storage is not declared by this plugin")
        key = "primary"
        if key not in self._sqlite_conns:
            path = plugin_data_dir(self._plugin_id, create=True) / "storage.db"
            conn = sqlite3.connect(str(path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._sqlite_conns[key] = conn
        return self._sqlite_conns[key]

    def close(self) -> None:
        for conn in self._sqlite_conns.values():
            try:
                conn.close()
            except Exception:  # noqa: BLE001 - shutdown must never raise
                pass
        self._sqlite_conns.clear()

    @property
    def data_dir(self) -> Optional[Path]:
        return plugin_data_dir(self._plugin_id, create=True)


__all__ = ["PluginStorage", "StorageError"]
