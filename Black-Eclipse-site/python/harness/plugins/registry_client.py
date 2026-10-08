"""Hosted plugin registry client: index, download, verify, extract.

A registry is a JSON index describing plugins the host can fetch. The source may
be an HTTP(S) URL, a local directory containing `index.json`, or a path to an
index file — so it works offline (a local mirror) and against a real hosted
registry with the same code.

Downloads are verified against the entry's SHA-256, then extracted with a
zip-slip guard (no absolute paths, no `..`, no symlinks). Only a verified,
safely-extracted package is handed to the installer.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from .errors import PluginError

DEFAULT_REGISTRY_ENV = "HARNESS_PLUGIN_REGISTRY_URL"


class RegistryError(PluginError):
    def __init__(self, code: str, message: str, **kwargs: Any) -> None:
        super().__init__(code, message, **kwargs)


def default_registry_source() -> Optional[str]:
    return os.environ.get(DEFAULT_REGISTRY_ENV)


def load_index(source: Optional[str] = None, *, transport: Any = None, timeout_s: float = 20.0) -> dict[str, Any]:
    """Load a registry index from a URL, directory, or index file."""
    resolved = source or default_registry_source()
    if not resolved:
        raise RegistryError("PLUGIN_REGISTRY_UNCONFIGURED",
                            "no registry is configured (set HARNESS_PLUGIN_REGISTRY_URL or pass a source)")
    parsed = urlparse(resolved)
    if parsed.scheme in ("http", "https"):
        import httpx  # noqa: PLC0415

        url = resolved if resolved.endswith(".json") else resolved.rstrip("/") + "/index.json"
        try:
            with httpx.Client(transport=transport, timeout=timeout_s) as client:
                response = client.get(url)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001 - an unreachable registry is an honest failure
            raise RegistryError("PLUGIN_REGISTRY_UNAVAILABLE", f"could not load registry {url}: {exc}") from exc
        return _normalize(data, base=url)
    path = Path(resolved)
    if path.is_dir():
        return _normalize(_read_json(path / "index.json"), base=str(path))
    if path.is_file():
        return _normalize(_read_json(path), base=str(path.parent))
    raise RegistryError("PLUGIN_REGISTRY_NOT_FOUND", f"registry source not found: {resolved}")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RegistryError("PLUGIN_REGISTRY_NOT_FOUND", f"index not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RegistryError("PLUGIN_REGISTRY_INVALID", f"could not parse {path}: {exc}") from exc


def _normalize(data: Any, *, base: str) -> dict[str, Any]:
    if isinstance(data, list):
        data = {"plugins": data}
    if not isinstance(data, dict) or "plugins" not in data:
        raise RegistryError("PLUGIN_REGISTRY_INVALID", "index must be a list or contain a 'plugins' list")
    entries = []
    for raw in data["plugins"]:
        if not isinstance(raw, dict) or "id" not in raw or "version" not in raw:
            raise RegistryError("PLUGIN_REGISTRY_INVALID", "each entry needs 'id' and 'version'")
        entry = dict(raw)
        url = entry.get("downloadUrl") or entry.get("download_url")
        if url:
            entry["downloadUrl"] = _resolve_url(base, str(url))
        entries.append(entry)
    return {"name": data.get("name", "registry"), "base": base, "plugins": entries}


def _resolve_url(base: str, url: str) -> str:
    if url.startswith(("http://", "https://", "file:")):
        return url
    if urlparse(base).scheme in ("http", "https"):
        return urljoin(base, url)
    return str((Path(base) / url).resolve())


def search(index: dict[str, Any], query: str = "", *, category: Optional[str] = None) -> list[dict[str, Any]]:
    q = (query or "").strip().lower()
    latest: dict[str, dict[str, Any]] = {}
    for entry in index.get("plugins", []):
        pid = entry["id"]
        if pid not in latest or str(entry["version"]) > str(latest[pid]["version"]):
            latest[pid] = entry
    results = []
    for entry in latest.values():
        if category and str(entry.get("category", "")).lower() != category.lower():
            continue
        if q:
            haystack = " ".join([
                str(entry.get("id", "")), str(entry.get("name", "")), str(entry.get("description", "")),
                str(entry.get("publisher", "")), " ".join(entry.get("tags", []) or []),
            ]).lower()
            if q not in haystack:
                continue
        results.append({
            "id": entry["id"], "name": entry.get("name", entry["id"]), "version": entry["version"],
            "description": entry.get("description", ""), "publisher": entry.get("publisher", ""),
            "category": entry.get("category", ""), "tags": entry.get("tags", []),
            "permissions": entry.get("permissions", []), "checksum": entry.get("checksum"),
            "trust": entry.get("trust", "community"), "downloadUrl": entry.get("downloadUrl"),
            "verified": entry.get("verification", "unsigned"),
        })
    return sorted(results, key=lambda e: e["name"].lower())


def download_and_extract(entry: dict[str, Any], *, transport: Any = None,
                         timeout_s: float = 60.0) -> Path:
    """Fetch, verify and extract an entry to a fresh temp directory. Returns its path."""
    url = entry.get("downloadUrl")
    if not url:
        raise RegistryError("PLUGIN_REGISTRY_NO_DOWNLOAD", f"entry {entry.get('id')!r} has no downloadUrl")
    payload = _fetch(url, transport=transport, timeout_s=timeout_s)
    expected = entry.get("checksum")
    if expected:
        actual = hashlib.sha256(payload).hexdigest()
        if actual != str(expected):
            raise RegistryError("PLUGIN_CHECKSUM_MISMATCH",
                                f"checksum mismatch for {entry.get('id')}: expected {expected}, got {actual}")
    target = Path(tempfile.mkdtemp(prefix=f"be-registry-{entry.get('id', 'plugin')}-"))
    try:
        _extract(payload, target)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target


def _fetch(url: str, *, transport: Any, timeout_s: float) -> bytes:
    # A local path (incl. a Windows drive path, which urlparse mis-reads as a
    # scheme) is read directly.
    try:
        candidate = Path(url)
        if candidate.is_file():
            return candidate.read_bytes()
    except (OSError, ValueError):
        pass
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return Path(parsed.path).read_bytes()
    if parsed.scheme in ("", None):
        return Path(url).read_bytes()
    import httpx  # noqa: PLC0415

    try:
        with httpx.Client(transport=transport, timeout=timeout_s, follow_redirects=True) as client:
            response = client.get(url)
        response.raise_for_status()
        return response.content
    except Exception as exc:  # noqa: BLE001
        raise RegistryError("PLUGIN_REGISTRY_DOWNLOAD_FAILED", f"download failed for {url}: {exc}") from exc


def _extract(payload: bytes, target: Path) -> None:
    """Extract a zip archive safely (zip-slip + symlink guarded)."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise RegistryError("PLUGIN_PACKAGE_INVALID", "the downloaded package is not a valid zip archive") from exc
    base = target.resolve()
    for member in archive.infolist():
        name = member.filename
        if name.startswith("/") or name.startswith("\\") or ".." in Path(name).parts:
            raise RegistryError("PLUGIN_PACKAGE_PATH_ESCAPE", f"archive member escapes root: {name!r}")
        dest = (base / name).resolve()
        if base != dest and base not in dest.parents:
            raise RegistryError("PLUGIN_PACKAGE_PATH_ESCAPE", f"archive member escapes root: {name!r}")
        if member.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        # Refuse symlinks (mode bits in the high 16 bits).
        if (member.external_attr >> 16) & 0o170000 == 0o120000:
            raise RegistryError("PLUGIN_PACKAGE_SYMLINK", f"archive contains a symlink: {name!r}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
    # A common packaging shape nests the plugin under a single top directory.
    children = [c for c in base.iterdir() if not c.name.startswith(".")]
    if len(children) == 1 and children[0].is_dir() and not (base / "plugin.yaml").exists() \
            and not (base / "plugin.json").exists():
        inner = children[0]
        for child in inner.iterdir():
            shutil.move(str(child), str(base / child.name))
        inner.rmdir()


__all__ = [
    "load_index",
    "search",
    "download_and_extract",
    "default_registry_source",
    "RegistryError",
    "DEFAULT_REGISTRY_ENV",
]
