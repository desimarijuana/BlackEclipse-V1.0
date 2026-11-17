"""Artifact storage adapter — a confined, content-addressed local store.

The adapter owns the ONE artifact storage root
(``<repo>/.black-eclipse/artifacts/`` by default, overridable with
``HARNESS_ARTIFACT_ROOT``). The domain service never sees a filesystem path: it
passes and receives an opaque, relative ``storage_key``.

Safety properties enforced here (not in prose):

* Every read/write/delete resolves the key through ``resolve_within`` and
  refuses traversal, absolute paths and symlink escapes.
* Object keys are unique and content-addressed (a sha256 prefix), so two
  artifacts with the same filename never collide.
* Writes are atomic (temp file + ``os.replace``) and size-bounded.
* Reads are streamed; callers get a file handle, never a full in-memory blob
  unless they explicitly bound the read.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Optional

from .content import extension_of, guess_mime, safe_display_name
from .model import MAX_IMPORT_BYTES

_HASH_CHUNK = 65_536
#: how much is read for magic-byte sniffing
_SNIFF_BYTES = 64


def default_artifact_root() -> Path:
    """The ONE artifact storage root. Never the CWD, never a user home."""
    override = os.environ.get("HARNESS_ARTIFACT_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    from ..persistence import _harness_root  # noqa: PLC0415

    return Path(_harness_root()) / ".black-eclipse" / "artifacts"


@dataclass(frozen=True)
class StoredObject:
    storage_key: str
    checksum: str
    size_bytes: int
    mime_type: str
    extension: str


class StorageError(Exception):
    """A storage operation could not be completed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_file(path: Path, *, limit: int = MAX_IMPORT_BYTES) -> tuple[str, int, bytes]:
    digest = hashlib.sha256()
    size = 0
    header = b""
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(_HASH_CHUNK)
                if not chunk:
                    break
                if not header:
                    header = chunk[:_SNIFF_BYTES]
                size += len(chunk)
                if size > limit:
                    raise StorageError(
                        "ARTIFACT_TOO_LARGE",
                        f"file exceeds the {limit} byte artifact limit",
                    )
                digest.update(chunk)
    except OSError as exc:
        raise StorageError("STORAGE_READ_FAILED", str(exc)) from exc
    return digest.hexdigest(), size, header


class LocalArtifactStorage:
    """A confined content-addressed store rooted at one directory."""

    name = "local"

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = Path(root) if root is not None else default_artifact_root()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    # ── key derivation ───────────────────────────────────────────────────────

    def _key_for(self, *, owner_id: str, checksum: str, name: str) -> str:
        owner = safe_display_name(owner_id or "local", fallback="local")
        now = datetime.now(timezone.utc)
        safe = safe_display_name(name)
        return f"{owner}/{now:%Y/%m}/{checksum[:16]}-{safe}"

    def _resolve(self, storage_key: str) -> Path:
        """Confine a storage key to the artifact root.

        Dedicated confinement — the code policy's workspace ignore/protected
        lists do NOT apply here (this is the artifact store, not a code
        checkout): `*.png`, `.black-eclipse/**` etc. are legitimate content.
        Rejects absolute paths, `..` traversal and symlink escapes.
        """
        if not storage_key or os.path.isabs(storage_key) or storage_key.startswith(("/", "\\")):
            raise StorageError("ARTIFACT_PATH_INVALID", "storage key must be relative")
        parts = [p for p in storage_key.replace("\\", "/").split("/") if p not in ("", ".")]
        if any(p == ".." for p in parts):
            raise StorageError("ARTIFACT_PATH_DENIED", "storage key escapes the artifact root")
        root_real = os.path.realpath(self._root)
        candidate = os.path.realpath(os.path.join(root_real, *parts))
        if candidate != root_real and not candidate.startswith(root_real + os.sep):
            raise StorageError("ARTIFACT_PATH_DENIED", "storage key escapes the artifact root")
        return Path(candidate)

    # ── writes ───────────────────────────────────────────────────────────────

    def save_bytes(
        self, data: bytes, *, name: str, owner_id: str = "local", mime_type: Optional[str] = None
    ) -> StoredObject:
        if not data:
            # An empty file is valid; only a None/oversized payload is refused.
            pass
        if len(data) > MAX_IMPORT_BYTES:
            raise StorageError(
                "ARTIFACT_TOO_LARGE", f"file exceeds the {MAX_IMPORT_BYTES} byte artifact limit"
            )
        checksum = _hash_bytes(data)
        mime = guess_mime(name, mime_type, header=data[:_SNIFF_BYTES])
        key = self._key_for(owner_id=owner_id, checksum=checksum, name=name)
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(target, data)
        return StoredObject(key, checksum, len(data), mime, extension_of(name))

    def import_file(
        self,
        source: str | Path,
        *,
        name: Optional[str] = None,
        owner_id: str = "local",
        mime_type: Optional[str] = None,
    ) -> StoredObject:
        """Copy an existing file into the store, hashing as it streams."""
        src = Path(source)
        if not src.is_file():
            raise StorageError("ARTIFACT_SOURCE_MISSING", f"source file not found: {source}")
        checksum, size, header = _hash_file(src)
        display = name or src.name
        mime = guess_mime(display, mime_type, header=header)
        key = self._key_for(owner_id=owner_id, checksum=checksum, name=display)
        target = self._resolve(key)
        if target.exists():
            return StoredObject(key, checksum, size, mime, extension_of(display))
        last_exc: Optional[OSError] = None
        for attempt in range(2):
            tmp_path: Optional[Path] = None
            try:
                # Re-create the parent on every attempt: artifact discovery and
                # the reconciler can remove an empty month directory between the
                # temp write and the rename (observed as WinError 3 on
                # `os.replace`). A retry is safe for a read-only import.
                target.parent.mkdir(parents=True, exist_ok=True)
                if not src.is_file():
                    raise StorageError(
                        "ARTIFACT_SOURCE_MISSING", f"source file not found: {source}"
                    )
                with open(src, "rb") as reader, tempfile.NamedTemporaryFile(
                    "wb", dir=target.parent, delete=False
                ) as tmp:
                    tmp_path = Path(tmp.name)
                    while True:
                        chunk = reader.read(_HASH_CHUNK)
                        if not chunk:
                            break
                        tmp.write(chunk)
                os.replace(tmp_path, target)
                return StoredObject(key, checksum, size, mime, extension_of(display))
            except StorageError:
                raise
            except FileNotFoundError as exc:
                last_exc = exc
                self._cleanup_temp(tmp_path)
                if attempt == 0:
                    continue
            except OSError as exc:
                self._cleanup_temp(tmp_path)
                raise StorageError("STORAGE_WRITE_FAILED", str(exc)) from exc
        raise StorageError(
            "STORAGE_WRITE_FAILED",
            f"the artifact store path disappeared during the write: {last_exc}",
        ) from last_exc

    def save_bytes_at(self, storage_key: str, data: bytes) -> Optional[str]:
        """Write bytes at an EXPLICIT key (used for derived thumbnails).

        The key is still confined; no caller-supplied absolute path is allowed.
        Returns the key on success, None when the write fails.
        """
        try:
            target = self._resolve(storage_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(target, data)
            return storage_key
        except (StorageError, OSError):
            return None

    def _atomic_write(self, target: Path, data: bytes) -> None:
        last_exc: Optional[OSError] = None
        for attempt in range(2):
            tmp_path: Optional[Path] = None
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile("wb", dir=target.parent, delete=False) as tmp:
                    tmp.write(data)
                    tmp_path = Path(tmp.name)
                os.replace(tmp_path, target)
                return
            except FileNotFoundError as exc:
                last_exc = exc
                self._cleanup_temp(tmp_path)
                if attempt == 0:
                    continue
                break
            except OSError as exc:
                self._cleanup_temp(tmp_path)
                raise StorageError("STORAGE_WRITE_FAILED", str(exc)) from exc
        raise StorageError(
            "STORAGE_WRITE_FAILED",
            f"the artifact store path disappeared during the write: {last_exc}",
        ) from last_exc

    @staticmethod
    def _cleanup_temp(tmp_path: Optional[Path]) -> None:
        try:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass

    # ── reads ────────────────────────────────────────────────────────────────

    def exists(self, storage_key: str) -> bool:
        try:
            return self._resolve(storage_key).is_file()
        except StorageError:
            return False

    def stat(self, storage_key: str) -> Optional[tuple[int, float]]:
        try:
            st = self._resolve(storage_key).stat()
        except (OSError, StorageError):
            return None
        return st.st_size, st.st_mtime

    def open(self, storage_key: str) -> BinaryIO:
        path = self._resolve(storage_key)
        if not path.is_file():
            raise StorageError("ARTIFACT_CONTENT_MISSING", "artifact content is missing")
        try:
            return open(path, "rb")
        except OSError as exc:
            raise StorageError("STORAGE_READ_FAILED", str(exc)) from exc

    def read_bytes(self, storage_key: str, *, limit: int = 8 * 1024 * 1024) -> bytes:
        with self.open(storage_key) as handle:
            return handle.read(limit)

    def checksum(self, storage_key: str) -> Optional[str]:
        try:
            digest, _, _ = _hash_file(self._resolve(storage_key))
        except (StorageError, OSError):
            return None
        return digest

    def checksum_for_path(self, path: str | Path) -> Optional[str]:
        """Hash an arbitrary file on disk (used by bounded workspace discovery)."""
        try:
            digest, _, _ = _hash_file(Path(path))
        except (StorageError, OSError):
            return None
        return digest

    def delete(self, storage_key: str) -> bool:
        try:
            path = self._resolve(storage_key)
        except StorageError:
            return False
        if not path.is_file():
            return False
        try:
            path.unlink()
            return True
        except OSError:
            return False

    # ── thumbnail keys live beside the object, never inside it ────────────────

    def thumbnail_key(self, storage_key: str) -> str:
        return f"{storage_key}.thumb.png"


__all__ = [
    "default_artifact_root",
    "LocalArtifactStorage",
    "StorageError",
    "StoredObject",
]
