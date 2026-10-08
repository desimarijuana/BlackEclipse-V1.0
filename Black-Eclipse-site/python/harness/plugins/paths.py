"""Filesystem layout for the plugin platform.

Installed plugins and their data live under `.black-eclipse/plugins/` beneath
the application root (the same root that owns the other `.black-eclipse/*`
artifacts). Built-in reference plugins ship inside this package under
`bundled/`. Nothing here writes to `jdds.db` or `eclipse-memory.db`; plugin
binaries and per-plugin data are the only files touched, and only beneath the
plugin root.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..persistence import _harness_root


def app_root() -> Path:
    override = os.environ.get("BLACK_ECLIPSE_PLUGIN_ROOT")
    if override:
        return Path(override).resolve()
    return Path(_harness_root())


def plugins_root() -> Path:
    """Where installed plugins live (one directory per plugin id)."""
    return app_root() / ".black-eclipse" / "plugins"


def data_root() -> Path:
    """Per-plugin private data (files, sqlite)."""
    return plugins_root() / "data"


def bundled_root() -> Path:
    """Reference plugins that ship with the runtime."""
    return Path(__file__).resolve().parent / "bundled"


def secret_key_path() -> Path:
    override = os.environ.get("BLACK_ECLIPSE_PLUGIN_SECRET_KEY")
    if override:
        return Path(override).resolve()
    return app_root() / ".black-eclipse" / "plugins" / "secret.key"


def plugin_data_dir(plugin_id: str, *, create: bool = False) -> Path:
    safe = _safe_component(plugin_id)
    path = data_root() / safe
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_component(value: str) -> str:
    """A filesystem-safe component derived from a plugin id (no traversal)."""
    cleaned = "".join(c if (c.isalnum() or c in "._-") else "_" for c in value or "")
    cleaned = cleaned.lstrip(".") or "plugin"
    return cleaned[:120]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


__all__ = [
    "app_root",
    "plugins_root",
    "data_root",
    "bundled_root",
    "secret_key_path",
    "plugin_data_dir",
    "ensure_dir",
    "_safe_component",
]
