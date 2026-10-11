"""Portable strategy bundles — export, import and (de)serialize.

A strategy must never be reachable only through one authoring surface. A bundle
is a self-describing, checksummed package that carries the canonical Strategy IR
plus the provenance needed to reproduce it, independent of the UI that produced
it (visual graph, Python lab, or AI copilot).

Wire format: a zip archive containing

    manifest.json   — format id/version, schema version, content hash, provenance
    strategy.json   — the canonical Strategy IR (the source of truth)
    README.md       — a short human-readable summary (informational only)

Safety rules (an imported bundle is untrusted input):
  * the compressed bundle size is capped,
  * the total *uncompressed* size is capped (zip-bomb guard),
  * member count is capped,
  * absolute paths, drive letters and `..` traversal are rejected,
  * only expected members are read; the archive is never extracted to disk,
  * the declared content hash is verified (a mismatch is a warning, not a silent
    accept), and
  * the IR is re-validated through the normal schema path on import.

Import never discards information: unknown top-level keys are preserved rather
than dropped, and validation issues are returned with the parsed spec.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Any, Optional, Union

from .errors import StrategyBundleError
from .schema import (
    STRATEGY_SCHEMA_VERSION,
    canonical_spec_dict,
    check_schema,
    spec_content_hash,
)
from .strategy import StrategySpec, parse_strategy, validate_strategy

BUNDLE_FORMAT = "blackeclipse.strategy-bundle"
BUNDLE_VERSION = 1

MANIFEST_NAME = "manifest.json"
SPEC_NAME = "strategy.json"
README_NAME = "README.md"
_EXPECTED_MEMBERS = {MANIFEST_NAME, SPEC_NAME, README_NAME}

MAX_BUNDLE_BYTES = 5 * 1024 * 1024          # compressed upload cap
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024   # zip-bomb guard
MAX_MEMBERS = 64


def build_manifest(
    spec: StrategySpec,
    *,
    provenance: Optional[dict[str, Any]] = None,
    schema_version: Optional[str] = None,
) -> dict[str, Any]:
    """Build the bundle manifest (format, schema, checksum, provenance).

    The content hash covers the *pure* Strategy IR; the schema version is carried
    in the manifest (and provenance) rather than injected into the IR, so the
    stored and exported IR dicts stay byte-identical for the same strategy.
    """
    return {
        "format": BUNDLE_FORMAT,
        "bundleVersion": BUNDLE_VERSION,
        "schemaVersion": schema_version or STRATEGY_SCHEMA_VERSION,
        "strategyId": spec.id,
        "strategyVersion": spec.version,
        "name": spec.name,
        "description": spec.description,
        "contentHash": spec_content_hash(spec),
        "provenance": provenance or {},
        "requires": {
            "engine": "quant",
            "schema": schema_version or STRATEGY_SCHEMA_VERSION,
        },
    }


def export_bundle(
    spec: StrategySpec,
    *,
    provenance: Optional[dict[str, Any]] = None,
    schema_version: Optional[str] = None,
) -> dict[str, Any]:
    """The in-memory bundle: manifest + canonical IR."""
    return {
        "manifest": build_manifest(spec, provenance=provenance, schema_version=schema_version),
        "strategy": spec.to_dict(),
    }


def _readme(bundle: dict[str, Any]) -> str:
    m = bundle["manifest"]
    return (
        f"# Strategy bundle: {m.get('name')}\n\n"
        f"- id: `{m.get('strategyId')}`\n"
        f"- version: `{m.get('strategyVersion')}`\n"
        f"- schema: `{m.get('schemaVersion')}`\n"
        f"- content hash: `{m.get('contentHash')}`\n\n"
        "This package contains the canonical Strategy IR (`strategy.json`) and a "
        "manifest (`manifest.json`). The IR is the source of truth; it can be "
        "imported by any BlackEclipse runtime that supports the declared schema "
        "version.\n"
    )


def bundle_to_bytes(bundle: dict[str, Any]) -> bytes:
    """Serialize a bundle to a zip archive in memory."""
    manifest = bundle.get("manifest") or {}
    strategy = bundle.get("strategy")
    if not isinstance(strategy, dict):
        raise StrategyBundleError("bundle is missing its strategy IR")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, sort_keys=True))
        zf.writestr(SPEC_NAME, json.dumps(strategy, indent=2))
        zf.writestr(README_NAME, _readme(bundle))
    return buf.getvalue()


def write_bundle(bundle: dict[str, Any], path: str) -> str:
    """Write a bundle zip to `path` (creating parent dirs). Returns the path."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = bundle_to_bytes(bundle)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


# ── Import (untrusted input) ─────────────────────────────────────────────────

def _safe_member_name(name: str) -> None:
    if not name or name.startswith("/") or name.startswith("\\"):
        raise StrategyBundleError(f"unsafe member path {name!r}")
    if ":" in name.split("/")[0]:  # drive letter / scheme
        raise StrategyBundleError(f"unsafe member path {name!r}")
    parts = name.replace("\\", "/").split("/")
    if any(p == ".." for p in parts):
        raise StrategyBundleError(f"unsafe member path {name!r}")


def read_bundle_bytes(data: bytes, *, max_bytes: int = MAX_BUNDLE_BYTES) -> dict[str, Any]:
    """Parse and validate a bundle zip from bytes. Never extracts to disk.

    Returns `{"manifest", "strategy", "warnings", "schema"}`. Raises
    `StrategyBundleError` for anything malformed or unsafe.
    """
    if not data:
        raise StrategyBundleError("empty bundle")
    if len(data) > max_bytes:
        raise StrategyBundleError(
            f"bundle is {len(data)} bytes, over the {max_bytes}-byte limit")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise StrategyBundleError("bundle is not a valid zip archive") from exc

    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise StrategyBundleError(f"bundle has too many members ({len(infos)})")
        total = 0
        for info in infos:
            _safe_member_name(info.filename)
            total += info.file_size
            if total > MAX_UNCOMPRESSED_BYTES:
                raise StrategyBundleError("bundle expands beyond the size limit")
        names = {i.filename for i in infos}
        if MANIFEST_NAME not in names or SPEC_NAME not in names:
            raise StrategyBundleError(
                "bundle must contain manifest.json and strategy.json")
        try:
            manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
            strategy = json.loads(zf.read(SPEC_NAME).decode("utf-8"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StrategyBundleError(f"bundle payload is not valid JSON: {exc}") from exc

    if not isinstance(manifest, dict) or not isinstance(strategy, dict):
        raise StrategyBundleError("bundle manifest/strategy must be JSON objects")
    if manifest.get("format") != BUNDLE_FORMAT:
        raise StrategyBundleError(
            f"unknown bundle format {manifest.get('format')!r}; expected {BUNDLE_FORMAT!r}")
    if int(manifest.get("bundleVersion") or 0) > BUNDLE_VERSION:
        raise StrategyBundleError(
            f"bundle version {manifest.get('bundleVersion')} is newer than supported")

    schema = check_schema(manifest.get("schemaVersion"))
    warnings: list[str] = []
    if not schema["compatible"]:
        raise StrategyBundleError(str(schema["message"]))
    declared_hash = manifest.get("contentHash")
    actual_hash = spec_content_hash(strategy)
    if declared_hash and declared_hash != actual_hash:
        warnings.append(
            "content hash mismatch: the bundle may have been modified after export")

    return {
        "manifest": manifest,
        "strategy": strategy,
        "warnings": warnings,
        "schema": schema,
        "contentHash": actual_hash,
    }


def import_bundle(
    source: Union[bytes, dict[str, Any]],
    *,
    max_bytes: int = MAX_BUNDLE_BYTES,
) -> dict[str, Any]:
    """Parse a bundle into a validated `StrategySpec`.

    `source` is either raw zip bytes or an already-decoded `{"manifest",
    "strategy"}` dict. Returns `{"spec", "manifest", "issues", "warnings",
    "contentHash", "schema"}` — never persists; the caller decides.
    """
    if isinstance(source, (bytes, bytearray)):
        parsed = read_bundle_bytes(bytes(source), max_bytes=max_bytes)
    elif isinstance(source, dict):
        if "strategy" in source:
            strategy = source["strategy"]
            manifest = source.get("manifest") or build_manifest(
                parse_strategy(strategy))
        else:
            strategy = source
            manifest = build_manifest(parse_strategy(strategy))
        schema = check_schema(manifest.get("schemaVersion"))
        if not schema["compatible"]:
            raise StrategyBundleError(str(schema["message"]))
        actual = spec_content_hash(strategy)
        dict_warnings: list[str] = []
        declared = manifest.get("contentHash")
        if declared and declared != actual:
            dict_warnings.append(
                "content hash mismatch: the bundle may have been modified after export")
        parsed = {
            "manifest": manifest,
            "strategy": strategy,
            "warnings": dict_warnings,
            "schema": schema,
            "contentHash": actual,
        }
    else:
        raise StrategyBundleError("bundle source must be zip bytes or a dict")

    spec = parse_strategy(dict(parsed["strategy"]))
    issues = validate_strategy(spec)
    return {
        "spec": spec,
        "manifest": parsed["manifest"],
        "issues": issues,
        "warnings": parsed["warnings"],
        "contentHash": parsed["contentHash"],
        "schema": parsed["schema"],
    }


__all__ = [
    "BUNDLE_FORMAT",
    "BUNDLE_VERSION",
    "MAX_BUNDLE_BYTES",
    "bundle_to_bytes",
    "build_manifest",
    "export_bundle",
    "import_bundle",
    "read_bundle_bytes",
    "write_bundle",
]
