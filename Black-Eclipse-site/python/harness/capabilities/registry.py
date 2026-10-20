"""Load active generated capabilities into the existing recipe registry."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Optional

from ..code.recipes import (
    Recipe,
    RecipeInput,
    clear_dynamic_recipes,
    dynamic_recipe_names,
    register_dynamic_recipe,
    unregister_dynamic_recipe,
)
from ..recovery.discovery import CapabilityDescriptor
from .manifest import CapabilityManifest
from .store import CapabilityStore
from .verifier import digest_text

DRAFT_RELATIVE = Path(".black-eclipse") / "capabilities"
_GLOBAL_DIR = Path(__file__).resolve().parents[1] / "generated" / "capabilities"


def draft_root(root: Optional[Path] = None) -> Path:
    base = Path(root) if root is not None else _default_root()
    return base / DRAFT_RELATIVE if base is not None else Path(os.getcwd()) / DRAFT_RELATIVE


def global_root() -> Path:
    return _GLOBAL_DIR


def _default_root() -> Optional[Path]:
    try:
        from ..code.workspace import default_root

        return default_root()
    except Exception:
        return None


def _as_store(store: Any) -> CapabilityStore:
    if isinstance(store, CapabilityStore):
        return store
    return CapabilityStore(store)


def load_manifest(directory: Path) -> Optional[CapabilityManifest]:
    try:
        return CapabilityManifest.load(directory / "manifest.json")
    except (OSError, ValueError):
        return None


def load_source(directory: Path) -> str:
    try:
        return (directory / "capability.py").read_text(encoding="utf-8")
    except OSError:
        return ""


def _inside(directory: Path, base: Path) -> bool:
    try:
        directory.resolve().relative_to(base.resolve())
        return True
    except (OSError, ValueError):
        return False


def resolve_directory(record: dict[str, Any], root: Optional[Path] = None) -> Optional[Path]:
    raw = str(record.get("dir") or "")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = (Path(root) if root is not None else Path.cwd()) / path
    if not (_inside(path, draft_root(root)) or _inside(path, global_root())):
        return None
    return path if path.is_dir() else None


def iter_active(
    store: Any,
    root: Optional[Path] = None,
) -> Iterable[tuple[dict[str, Any], CapabilityManifest, str, Path]]:
    capability_store = _as_store(store)
    for record in capability_store.records(status="active", limit=500):
        directory = resolve_directory(record, root)
        if directory is None:
            continue
        manifest = load_manifest(directory)
        source = load_source(directory)
        if manifest is None or not source.strip():
            continue
        if record.get("sourceDigest") and record["sourceDigest"] != digest_text(source):
            continue
        yield record, manifest, source, directory


def generated_descriptors(store: Any, root: Optional[Path] = None) -> list[CapabilityDescriptor]:
    out: list[CapabilityDescriptor] = []
    for _record, manifest, _source, _directory in iter_active(store, root):
        out.append(CapabilityDescriptor(
            id=manifest.id,
            kind="recipe" if manifest.kind in ("recipe", "report_template") else manifest.kind,
            description=manifest.description,
            available=True,
            permissions=tuple(manifest.permissions),
            provenance="native",
            tags=(manifest.kind, manifest.title),
        ))
    return out


def to_recipe(manifest: CapabilityManifest, source: str) -> Recipe:
    return Recipe(
        name=manifest.id,
        answers=manifest.description,
        inputs=tuple(
            RecipeInput(
                name=port.name,
                kind=port.kind,
                description=port.description or port.name,
                required=port.required,
            )
            for port in manifest.inputs
        ),
        source=source,
        missing_prompt=f"I need {{missing}} to run {manifest.title}.",
    )


def register(manifest: CapabilityManifest, source: str) -> bool:
    if manifest.kind not in ("recipe", "report_template"):
        return False
    register_dynamic_recipe(to_recipe(manifest, source))
    return True


def refresh_generated_recipes(store: Any, root: Optional[Path] = None) -> list[str]:
    if store is None:
        return []
    clear_dynamic_recipes()
    loaded: list[str] = []
    for _record, manifest, source, _directory in iter_active(store, root):
        if manifest.kind not in ("recipe", "report_template"):
            continue
        register_dynamic_recipe(to_recipe(manifest, source))
        loaded.append(manifest.id)
    return sorted(loaded)


def remove_generated_recipe(capability_id: str) -> None:
    unregister_dynamic_recipe(capability_id)


def is_generated_recipe(name: str) -> bool:
    return name in dynamic_recipe_names()


__all__ = [
    "DRAFT_RELATIVE",
    "draft_root",
    "generated_descriptors",
    "global_root",
    "is_generated_recipe",
    "iter_active",
    "load_manifest",
    "load_source",
    "refresh_generated_recipes",
    "register",
    "remove_generated_recipe",
    "resolve_directory",
    "to_recipe",
]
