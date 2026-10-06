"""The artifact manager — bounded, hashed artifact collection.

An artifact is a file an execution produced, identified by a sha256 hash so a
later verification can prove it is byte-identical. Collection is bounded: only a
closed set of artifact directories is scanned, only inside the workspace, and
only up to a fixed count and size. A truncated collection is reported as such —
never silently partial.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Iterable, Optional

from .models import Artifact

# The directories and file shapes a build/test run commonly produces.
ARTIFACT_DIRS = ("dist", "build", "out", "coverage", "reports", "artifacts", "target/debug")
ARTIFACT_SUFFIXES = (".log", ".json", ".xml", ".html", ".txt", ".lcov", ".png", ".jar", ".exe", ".whl")
MAX_ARTIFACTS = 200
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_HASH_CHUNK = 65_536


def _hash_file(path: Path, *, limit: int = MAX_ARTIFACT_BYTES) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(_HASH_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    return "", size
                digest.update(chunk)
    except OSError:
        return "", 0
    return digest.hexdigest(), size


class ArtifactManager:
    """Collect artifacts produced by an execution, with hashes and sizes."""

    def __init__(self, *, root: Path, execution_id: str) -> None:
        self._root = Path(root)
        self._execution_id = execution_id

    def collect(self, *, baseline: Optional[dict[str, float]] = None) -> tuple[list[Artifact], bool]:
        """Collect artifacts under the known directories.

        When `baseline` (path -> mtime) is given, only files newer than the baseline
        are reported as produced by THIS execution; pre-existing files are skipped.
        Returns `(artifacts, truncated)`.
        """
        artifacts: list[Artifact] = []
        truncated = False
        for relative in ARTIFACT_DIRS:
            directory = self._root / relative
            if not directory.is_dir():
                continue
            for path in self._iter_files(directory):
                if len(artifacts) >= MAX_ARTIFACTS:
                    return artifacts, True
                artifact = self._make(path, baseline)
                if artifact is not None:
                    artifacts.append(artifact)
        return artifacts, truncated

    def collect_paths(self, paths: Iterable[str]) -> list[Artifact]:
        """Collect the exact files named by `paths` (workspace-relative)."""
        from ..code.policy import PolicyDenial, resolve_within  # noqa: PLC0415

        out: list[Artifact] = []
        for rel in paths:
            try:
                resolved = resolve_within(self._root, rel)
            except PolicyDenial:
                continue
            if resolved.is_file():
                artifact = self._make(resolved, None)
                if artifact is not None:
                    out.append(artifact)
            if len(out) >= MAX_ARTIFACTS:
                break
        return out

    def snapshot(self) -> dict[str, float]:
        """A {path: mtime} baseline of the artifact directories before a run."""
        baseline: dict[str, float] = {}
        for relative in ARTIFACT_DIRS:
            directory = self._root / relative
            if not directory.is_dir():
                continue
            for path in self._iter_files(directory):
                try:
                    baseline[str(path)] = path.stat().st_mtime or 0.0
                except OSError:
                    continue
        return baseline

    def _iter_files(self, directory: Path):
        from ..code import policy  # noqa: PLC0415

        for dirpath, dirnames, filenames in os.walk(directory):
            dirnames[:] = [d for d in dirnames if d not in policy.IGNORED_DIRS]
            for name in filenames:
                suffix = Path(name).suffix.casefold()
                if suffix not in ARTIFACT_SUFFIXES and not name.endswith((".log",)):
                    continue
                yield Path(dirpath) / name

    def _make(self, path: Path, baseline: Optional[dict[str, float]]) -> Artifact | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        if baseline is not None:
            previous = baseline.get(str(path))
            if previous is not None and stat.st_mtime <= previous:
                return None
        digest, size = _hash_file(path)
        try:
            rel = path.relative_to(self._root).as_posix()
        except ValueError:
            rel = path.name
        return Artifact(
            path=rel, type="file", size=size, hash=digest,
            execution_id=self._execution_id, created_at=time.time(),
        )


__all__ = ["ARTIFACT_DIRS", "ARTIFACT_SUFFIXES", "ArtifactManager", "MAX_ARTIFACTS"]
