"""SBOM for the native video worker (Phase 8).

The worker's entire Rust dependency graph is pinned by the committed
``Cargo.lock``; this module turns that lock into a reviewable SOFTWARE BILL OF
MATERIALS (``rust/fframes-worker/SBOM.json``) and pins the one dependency that
matters most — fframes — to an EXACT version in ``Cargo.toml``.

What the SBOM records, and what it honestly does not:

- every locked crate's name, version, registry source and checksum (straight
  from the lock — exact, not inferred);
- the fframes pin (parsed from ``Cargo.toml``; a non-exact pin is refused);
- the FFmpeg build identity and licensing note (the BtbN GPL variant used on
  this machine — redistribution must account for it);
- the licenses that were verified BY HAND (fframes: MIT upstream). Per-crate
  license strings are NOT extracted here: ``Cargo.lock`` has no license field,
  and this repo deliberately does not run a resolver/tooling chain for it.
  ``cargo metadata``/``cargo-about`` is the honest way to add them later.

Regenerate with ``python -m harness.video.sbom``; the test suite fails when the
committed file drifts from the lock, so a dependency bump cannot ship without a
fresh SBOM.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

SBOM_SCHEMA_VERSION = 1
WORKER_DIR_PARTS = ("rust", "fframes-worker")
SBOM_FILENAME = "SBOM.json"

_FFRAMES_PIN_RE = re.compile(
    r"^\s*fframes\s*=\s*\{[^}]*version\s*=\s*\"=([^\"]+)\"", re.MULTILINE
)


def worker_dir() -> Path:
    """`<site>/rust/fframes-worker` — independent of the process cwd."""
    from ..persistence import _harness_root  # noqa: PLC0415

    return Path(_harness_root()).joinpath(*WORKER_DIR_PARTS)


def sbom_path() -> Path:
    return worker_dir() / SBOM_FILENAME


# ── parsing ───────────────────────────────────────────────────────────────────


def parse_fframes_pin(cargo_toml_text: str) -> str:
    """The EXACT fframes pin (`=X.Y.Z`). A loose pin is an error, not a warning:
    an unpinned renderer is a supply-chain and reproducibility hazard."""
    match = _FFRAMES_PIN_RE.search(cargo_toml_text or "")
    if not match:
        raise ValueError("Cargo.toml does not pin fframes with an exact (`=x.y.z`) version")
    return f"={match.group(1)}"


def parse_cargo_lock(lock_text: str) -> list[dict[str, Any]]:
    """Every `[[package]]` block as `{name, version, source?, checksum?}`."""
    packages: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    for line in (lock_text or "").splitlines():
        stripped = line.strip()
        if stripped == "[[package]]":
            if current is not None:
                packages.append(current)
            current = {}
            continue
        if current is None:
            continue
        if stripped.startswith("["):  # the next section (`[metadata]`, …)
            packages.append(current)
            current = None
            continue
        match = re.match(r"^(name|version|source|checksum)\s*=\s*\"([^\"]*)\"$", stripped)
        if match:
            current[match.group(1)] = match.group(2)
    if current is not None:
        packages.append(current)
    return [package for package in packages if package.get("name") and package.get("version")]


# ── the SBOM ──────────────────────────────────────────────────────────────────


def build_sbom(cargo_lock_text: str, cargo_toml_text: str) -> dict[str, Any]:
    """Build the deterministic SBOM document for the worker's locked graph."""
    pin = parse_fframes_pin(cargo_toml_text)
    packages = parse_cargo_lock(cargo_lock_text)
    packages.sort(key=lambda package: (package["name"], package["version"]))
    fframes = [p for p in packages if p["name"] == "fframes"]
    if not fframes or f"={fframes[0]['version']}" != pin:
        raise ValueError(
            f"fframes pin {pin} does not match the locked "
            f"{[p['version'] for p in fframes] or 'nothing'}"
        )
    return {
        "schemaVersion": SBOM_SCHEMA_VERSION,
        "kind": "native-video-worker",
        "generatedBy": "python -m harness.video.sbom",
        "worker": {
            "name": "fframes-worker",
            "fframesPin": pin,
        },
        "ffmpeg": {
            "build": "BtbN ffmpeg-n9.0-latest-win64-gpl-shared-9.0",
            "note": (
                "Linked at build time and loaded at run time from FFMPEG_DIR/bin. "
                "This build is the GPL variant (x264/x265): distributing the worker "
                "binary must account for the FFmpeg/encoder licenses."
            ),
        },
        "licenses": {
            "fframes": "MIT (verified upstream; not extracted from the lock)",
            "ffmpeg": "GPL (BtbN variant used here) — see ffmpeg.note",
            "crates": "per-crate licenses are NOT extracted here (Cargo.lock has no "
                      "license field); use `cargo metadata`/`cargo-about` to extend",
        },
        "packageCount": len(packages),
        "packages": packages,
    }


def generate_from_worker_dir(directory: Optional[Path] = None) -> dict[str, Any]:
    base = Path(directory) if directory is not None else worker_dir()
    lock = (base / "Cargo.lock").read_text(encoding="utf-8")
    toml = (base / "Cargo.toml").read_text(encoding="utf-8")
    return build_sbom(lock, toml)


def write_sbom(path: Optional[Path] = None, directory: Optional[Path] = None) -> Path:
    """Regenerate the committed SBOM (atomic write). Returns the written path."""
    document = generate_from_worker_dir(directory)
    target = Path(path) if path is not None else (
        (Path(directory) / SBOM_FILENAME) if directory is not None else sbom_path()
    )
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return target


def main() -> int:
    target = write_sbom()
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())


__all__ = [
    "SBOM_FILENAME",
    "SBOM_SCHEMA_VERSION",
    "build_sbom",
    "generate_from_worker_dir",
    "main",
    "parse_cargo_lock",
    "parse_fframes_pin",
    "sbom_path",
    "worker_dir",
    "write_sbom",
]
