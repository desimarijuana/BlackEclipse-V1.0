"""A marketplace index over installed + bundled plugins.

This is a real, local-first index: it lists what is installed and what ships with
the runtime (the reference plugins), and supports text/category search over
validated manifest metadata. It is the seam a hosted registry would plug into —
the query/result shape is stable — but it never fabricates a remote catalog: an
entry is only listed when a real manifest exists on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .loader import checksum, read_manifest
from .manifest import PluginManifest
from .model import TrustLevel


def _entry(manifest: PluginManifest, *, source: str, path: str, installed: bool,
           record: Any = None) -> dict[str, Any]:
    return {
        "id": manifest.id,
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "publisher": manifest.publisher_id,
        "category": manifest.category,
        "tags": list(manifest.tags),
        "permissions": list(manifest.permissions),
        "source": source,  # "installed" | "bundled"
        "installed": installed,
        "enabled": bool(record.enabled) if record else False,
        "state": record.status.value if record else "AVAILABLE",
        "verification": record.verification if record else ("official" if source == "bundled" else "unsigned"),
        "contributes": {k: len(v) for k, v in manifest.contributes.all_contribution_names().items() if v},
        "path": path,
    }


def list_available(manager: Any) -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    # Bundled reference plugins first (official).
    for path in manager.bundled_dirs():
        try:
            manifest, _ = read_manifest(path)
        except Exception:  # noqa: BLE001 - a broken bundled manifest is skipped, not fatal
            continue
        entries[manifest.id] = _entry(manifest, source="bundled", path=str(path), installed=False)
    # Installed plugins override (they are authoritative for id).
    for record in manager.store.list_plugins():
        manifest = manager.manifest_of(record.plugin_id)
        if manifest is None:
            continue
        entries[record.plugin_id] = _entry(
            manifest, source="installed", path=record.installation_path,
            installed=True, record=record,
        )
    return sorted(entries.values(), key=lambda e: e["name"].lower())


def search(manager: Any, query: str = "", *, category: Optional[str] = None,
           installed_only: bool = False) -> list[dict[str, Any]]:
    q = (query or "").strip().lower()
    results = []
    for entry in list_available(manager):
        if installed_only and not entry["installed"]:
            continue
        if category and entry["category"].lower() != category.lower():
            continue
        if q:
            haystack = " ".join([
                entry["id"], entry["name"], entry["description"], entry["publisher"],
                " ".join(entry["tags"]), entry["category"],
            ]).lower()
            if q not in haystack:
                continue
        results.append(entry)
    return results


def categories(manager: Any) -> list[str]:
    return sorted({e["category"] for e in list_available(manager) if e["category"]})


__all__ = ["list_available", "search", "categories"]
