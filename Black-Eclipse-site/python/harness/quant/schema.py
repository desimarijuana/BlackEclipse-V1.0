"""Strategy IR schema identity, compatibility and migration.

The strategy contract (`StrategySpec`) is the canonical, serializable Strategy
Intermediate Representation. This module owns the *version identity* of that IR:

  * a single monotonic `STRATEGY_SCHEMA_VERSION` for the wire format,
  * a compatibility policy (which historical versions the current runtime can
    still load), and
  * an ordered, deterministic migration registry that upgrades an older
    serialized spec dict to the current version.

Migration rules:
  * migrations operate on plain dicts, never on the live pydantic model,
  * they are applied in order and are idempotent per hop,
  * they NEVER silently discard unknown keys — an unknown field is preserved so
    an older runtime re-importing a newer document cannot lose information.

The content hash is intentionally decoupled from the schema version: it is a
sha256 over the *canonicalized spec JSON* and is what makes a stored strategy
version immutable and reproducible.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Optional, Union

from .strategy import StrategySpec

# The current wire-format version of the strategy IR. Bump the minor for purely
# additive/back-compatible fields, the major for a breaking shape change.
STRATEGY_SCHEMA_VERSION = "1.0.0"

# Every historical version this runtime can still load without a breaking change.
SUPPORTED_SCHEMA_VERSIONS: tuple[str, ...] = ("1.0.0",)


class SchemaError(ValueError):
    """A serialized strategy declares a schema version this runtime cannot load."""

    code = "UNSUPPORTED_SCHEMA_VERSION"


def parse_schema_version(version: str) -> tuple[int, int, int]:
    core = str(version).split("-")[0].split("+")[0]
    parts = core.split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError as exc:
        raise SchemaError(f"invalid schema version {version!r}") from exc


def schema_compatible(version: Optional[str]) -> bool:
    """True when `version` can be loaded by the current runtime.

    An absent version is treated as compatible (legacy documents predate the
    field). A newer *major* is never compatible; a same-major version is
    accepted (additive changes stay readable).
    """
    if not version:
        return True
    try:
        cur = parse_schema_version(STRATEGY_SCHEMA_VERSION)
        got = parse_schema_version(version)
    except SchemaError:
        return False
    # Same major ⇒ additive-compatible: a newer minor/patch is still loadable.
    # A different major is a breaking change and is never accepted.
    return got[0] == cur[0]


def check_schema(version: Optional[str]) -> dict[str, Any]:
    """A structured compatibility report — never raises."""
    ok = schema_compatible(version)
    return {
        "declaredVersion": version,
        "currentVersion": STRATEGY_SCHEMA_VERSION,
        "supportedVersions": list(SUPPORTED_SCHEMA_VERSIONS),
        "compatible": ok,
        "message": (
            "compatible with the current runtime"
            if ok
            else f"schema version {version!r} is not loadable by this runtime "
            f"(current {STRATEGY_SCHEMA_VERSION})"
        ),
    }


# ── Migration registry ───────────────────────────────────────────────────────
#
# `_MIGRATIONS[from_version]` upgrades a document *from* that version to the next
# one. There are no historical versions yet, so the registry is empty and the
# upgrade is the identity; the mechanism exists so a future schema change has one
# obvious, tested home.

Migration = Callable[[dict[str, Any]], dict[str, Any]]

_MIGRATIONS: dict[str, Migration] = {}


def migrate(
    data: dict[str, Any],
    *,
    from_version: Optional[str] = None,
    to_version: str = STRATEGY_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Return a copy of `data` upgraded to `to_version` (deterministic, lossless).

    Unknown keys are preserved. Raises `SchemaError` if the document's version is
    newer than the target or a migration hop is missing.
    """
    doc = dict(data)
    declared = from_version or _declared_version(doc) or STRATEGY_SCHEMA_VERSION
    if parse_schema_version(declared) > parse_schema_version(to_version):
        # A newer document: never downgrade (would lose information).
        if declared != to_version:
            raise SchemaError(
                f"cannot migrate from newer schema {declared!r} to {to_version!r}"
            )
        return doc
    version = declared
    guard = 0
    while version != to_version:
        step = _MIGRATIONS.get(version)
        if step is None:
            # No path forward for this version; if it is still compatible, accept
            # it as-is rather than discarding data.
            if schema_compatible(version):
                break
            raise SchemaError(f"no migration path from schema {version!r}")
        doc = step(doc)
        version = _next_known(version)
        guard += 1
        if guard > 64:  # pragma: no cover - defensive; registry is tiny
            raise SchemaError("migration did not converge")
    meta = doc.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
    meta = dict(meta)
    meta.setdefault("schemaVersion", to_version)
    doc["metadata"] = meta
    return doc


def _declared_version(doc: dict[str, Any]) -> Optional[str]:
    if isinstance(doc.get("schemaVersion"), str):
        return doc["schemaVersion"]
    meta = doc.get("metadata")
    if isinstance(meta, dict) and isinstance(meta.get("schemaVersion"), str):
        return meta["schemaVersion"]
    return None


def _next_known(version: str) -> str:
    """The next version in `SUPPORTED_SCHEMA_VERSIONS` after `version`."""
    try:
        idx = SUPPORTED_SCHEMA_VERSIONS.index(version)
    except ValueError:
        return STRATEGY_SCHEMA_VERSION
    if idx + 1 < len(SUPPORTED_SCHEMA_VERSIONS):
        return SUPPORTED_SCHEMA_VERSIONS[idx + 1]
    return STRATEGY_SCHEMA_VERSION


# ── Canonical content hash ───────────────────────────────────────────────────

def canonical_spec_dict(spec: Union[StrategySpec, dict[str, Any]]) -> dict[str, Any]:
    """The canonical, serialization-stable dict for hashing.

    The schema version lives in `metadata` (not a top-level field) so it is part
    of the hash: a schema bump is a real content change.
    """
    if isinstance(spec, StrategySpec):
        data = spec.to_dict()
    else:
        data = dict(spec)
    return data


def spec_content_hash(spec: Union[StrategySpec, dict[str, Any]]) -> str:
    """A stable sha256 over the canonicalized spec (order-independent reconstruction).

    Two specs that differ only in key ordering or whitespace hash identically;
    any semantic change changes the hash. This is the immutability identity for a
    stored strategy version.
    """
    canonical = canonical_spec_dict(spec)
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


__all__ = [
    "STRATEGY_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "SchemaError",
    "canonical_spec_dict",
    "check_schema",
    "migrate",
    "parse_schema_version",
    "schema_compatible",
    "spec_content_hash",
]
