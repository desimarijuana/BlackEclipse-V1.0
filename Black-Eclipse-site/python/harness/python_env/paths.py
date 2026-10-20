"""Managed package paths, the lock file and installed-module discovery."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

_ENV_RELATIVE = Path(".black-eclipse") / "python-env"


def base_root(root: Optional[Path] = None) -> Path:
    if root is not None:
        return Path(root)
    try:
        from ..code.workspace import default_root  # noqa: PLC0415

        resolved = default_root()
        if resolved is not None:
            return Path(resolved)
    except Exception:  # noqa: BLE001
        pass
    return Path.cwd()


def env_root(root: Optional[Path] = None) -> Path:
    return base_root(root) / _ENV_RELATIVE


def site_packages(root: Optional[Path] = None) -> Path:
    return env_root(root) / "site-packages"


def lock_path(root: Optional[Path] = None) -> Path:
    return env_root(root) / "lock.json"


def pip_cache(root: Optional[Path] = None) -> Path:
    return base_root(root) / ".black-eclipse" / "pip-cache"


def read_lock(root: Optional[Path] = None) -> dict[str, Any]:
    path = lock_path(root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "manager": "pip", "target": str(site_packages(root)), "packages": []}
    if not isinstance(raw, dict):
        return {"version": 1, "manager": "pip", "target": str(site_packages(root)), "packages": []}
    packages = raw.get("packages")
    if not isinstance(packages, list):
        raw["packages"] = []
    return raw


def lock_digest(root: Optional[Path] = None) -> str:
    path = lock_path(root)
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(data).hexdigest()


def _modules(dist: Any) -> list[str]:
    try:
        raw = dist.read_text("top_level.txt") or ""
    except Exception:  # noqa: BLE001
        raw = ""
    modules = [
        line.strip() for line in raw.splitlines()
        if line.strip() and not line.startswith(("_", "."))
    ]
    if modules:
        return sorted(dict.fromkeys(modules))
    inferred: list[str] = []
    for file in dist.files or []:
        parts = str(file).replace("\\", "/").split("/")
        top = parts[0]
        if not top or top.startswith((".", "_")) or top.endswith((".dist-info", ".egg-info")):
            continue
        if top.endswith((".py", ".pyd", ".so", ".dll")):
            top = top.rsplit(".", 1)[0]
        if top and top not in inferred:
            inferred.append(top)
    return sorted(inferred)


def installed_packages(root: Optional[Path] = None) -> list[dict[str, Any]]:
    target = site_packages(root)
    if not target.is_dir():
        return []
    try:
        from importlib.metadata import distributions  # noqa: PLC0415

        found = distributions(path=[str(target)])
    except Exception:  # noqa: BLE001
        return []
    out: list[dict[str, Any]] = []
    for dist in found:
        try:
            name = dist.metadata.get("Name") or ""
            version = dist.version or ""
        except Exception:  # noqa: BLE001
            continue
        if not name:
            continue
        out.append({"name": name, "version": version, "modules": _modules(dist)})
    return sorted(out, key=lambda item: str(item["name"]).casefold())


def installed_modules(root: Optional[Path] = None) -> list[str]:
    lock = read_lock(root)
    modules: list[str] = []
    for package in lock.get("packages") or []:
        if isinstance(package, dict):
            modules.extend(str(module) for module in package.get("modules") or [])
    if not modules:
        for package in installed_packages(root):
            modules.extend(package.get("modules") or [])
    return sorted(dict.fromkeys(module for module in modules if module))


def write_lock(packages: list[dict[str, Any]], root: Optional[Path] = None) -> dict[str, Any]:
    from ..persistence import now_iso  # noqa: PLC0415

    payload = {
        "version": 1,
        "manager": "pip",
        "target": str(site_packages(root)),
        "packages": sorted(packages, key=lambda item: str(item.get("name") or "").casefold()),
        "updatedAt": now_iso(),
    }
    path = lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    temporary.replace(path)
    return payload


__all__ = [
    "base_root",
    "env_root",
    "installed_modules",
    "installed_packages",
    "lock_digest",
    "lock_path",
    "pip_cache",
    "read_lock",
    "site_packages",
    "write_lock",
]
