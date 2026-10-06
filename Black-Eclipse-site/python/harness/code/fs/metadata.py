"""File metadata, hashing and permissions — normalized across platforms.

  * `file_metadata` returns a stable record (type, size, extension, mime,
    encoding, created/modified/accessed time, permissions, symlink info).
  * `file_hash` is SHA-256 with a safe cache keyed by (realpath, mtime_ns, size) —
    the hash is always recomputed when the file could have changed.
  * `file_permissions` reports a normalized read/write/execute view PLUS the
    platform-specific detail. Windows and Unix are not pretended to be identical:
    on Windows the read-only attribute is reported and the POSIX bits are absent;
    on POSIX the octal mode and owner/group are reported.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .. import policy
from . import encoding as enc
from . import errors as err
from . import resolver as res

_HASH_CHUNK = 65_536

# Extension → mime overrides where the stdlib map is wrong or missing for the
# source formats an agent edits.
_MIME_OVERRIDES: dict[str, str] = {
    ".ts": "text/typescript",
    ".tsx": "text/tsx",
    ".jsx": "text/jsx",
    ".md": "text/markdown",
    ".py": "text/x-python",
    ".toml": "text/x-toml",
    ".yml": "text/x-yaml",
    ".yaml": "text/x-yaml",
    ".sql": "text/x-sql",
    ".env": "text/plain",
}

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".svg"}
_ARCHIVE_EXTS = {".zip", ".gz", ".tar", ".tgz", ".7z", ".rar", ".jar", ".whl"}


@dataclass
class _HashEntry:
    mtime_ns: int
    size: int
    digest: str


# Process-wide, bounded hash cache. Keyed by real path; correctness is preserved
# because the key includes mtime_ns AND size — a change invalidates the entry.
_HASH_CACHE: dict[str, _HashEntry] = {}
_HASH_CACHE_MAX = 4096


def clear_hash_cache() -> None:
    _HASH_CACHE.clear()


def _real(path: Path) -> str:
    return os.path.realpath(str(path))


def hash_file(path: Path, *, use_cache: bool = True) -> str:
    """SHA-256 of a file. Recomputes whenever mtime/size could have changed."""
    try:
        st = path.stat()
    except OSError as exc:
        raise err.FsError(err.PATH_NOT_FOUND, "That file isn't there.", path=str(path)) from exc
    key = _real(path)
    if use_cache:
        entry = _HASH_CACHE.get(key)
        if entry is not None and entry.mtime_ns == st.st_mtime_ns and entry.size == st.st_size:
            return entry.digest
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
                digest.update(chunk)
    except OSError as exc:
        raise err.FsError(err.PERMISSION_DENIED, "That file couldn't be read.", path=str(path)) from exc
    hexdigest = digest.hexdigest()
    if use_cache:
        if len(_HASH_CACHE) >= _HASH_CACHE_MAX:
            _HASH_CACHE.clear()
        _HASH_CACHE[key] = _HashEntry(mtime_ns=st.st_mtime_ns, size=st.st_size, digest=hexdigest)
    return hexdigest


def hash_text(text: str) -> str:
    """The SHA-256 of text encoded as UTF-8, matching the patch engine's own."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _MIME_OVERRIDES:
        return _MIME_OVERRIDES[suffix]
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return guessed
    if suffix in _IMAGE_EXTS:
        return "image/" + suffix.lstrip(".")
    if suffix in _ARCHIVE_EXTS:
        return "application/octet-stream"
    return "application/octet-stream"


def _file_type(path: Path) -> str:
    try:
        if path.is_symlink():
            return "symlink"
    except OSError:
        pass
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    return "other"


def permissions_for(path: Path) -> dict[str, Any]:
    """Normalized + platform-specific permission detail. Never invented."""
    try:
        st = path.stat()
    except OSError as exc:
        raise err.FsError(err.PATH_NOT_FOUND, "That file isn't there.", path=str(path)) from exc
    mode = st.st_mode
    normalized = {
        "readable": os.access(path, os.R_OK),
        "writable": os.access(path, os.W_OK),
        "executable": os.access(path, os.X_OK),
    }
    result: dict[str, Any] = {"normalized": normalized, "platform": os.name}
    if os.name == "posix":
        result["mode"] = oct(stat.S_IMODE(mode))
        result["uid"] = st.st_uid
        result["gid"] = st.st_gid
    else:
        result["readonly"] = not bool(mode & stat.S_IWRITE)
        result["hidden"] = path.name.startswith(".") or bool(
            getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0)
        )
    return result


def file_metadata(ws: Any, rel_path: str) -> dict[str, Any]:
    """The full metadata record for one path inside the workspace."""
    target = res.resolve(ws, rel_path)
    rel = res.relative(ws, target)
    if not target.exists() and not target.is_symlink():
        raise err.FsError(err.PATH_NOT_FOUND, "That path isn't there.", path=rel)
    ftype = _file_type(target)
    try:
        st = target.stat()
    except OSError as exc:
        raise err.FsError(err.PERMISSION_DENIED, "That path couldn't be inspected.", path=rel) from exc
    is_binary = ftype == "file" and res.is_binary_file(target)
    record: dict[str, Any] = {
        "status": "ok",
        "path": rel,
        "type": ftype,
        "size": st.st_size,
        "extension": target.suffix,
        "mimeType": mime_type(target),
        "binary": is_binary,
        "hidden": target.name.startswith("."),
        "protected": policy.is_protected(rel),
        "ignored": policy.is_ignored(rel),
        "created": _iso(st.st_ctime),
        "modified": _iso(st.st_mtime),
        "accessed": _iso(st.st_atime),
        "permissions": permissions_for(target),
    }
    if ftype == "file" and not is_binary:
        record["sha256"] = hash_file(target)
        try:
            decoded = enc.read_text(target)
            record["encoding"] = decoded.encoding
            record["bom"] = decoded.had_bom
            record["newline"] = decoded.newline
        except err.FsError:
            record["encoding"] = None
    if ftype == "symlink":
        try:
            link_target = os.readlink(target)
            record["symlink"] = {"target": link_target, "escapes": not res.is_inside(ws, Path(os.path.realpath(target)))}
        except OSError:
            record["symlink"] = {"target": None, "escapes": None}
    # Git awareness is additive: it is present only when the folder is a checkout.
    try:
        from . import git as git_mod  # noqa: PLC0415 - avoid a circular import

        record["git"] = git_mod.status_for(ws.root, rel)
    except Exception:  # noqa: BLE001 - git must never break metadata
        record["git"] = None
    return record


def _iso(ts: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ── workspace-bound public helpers (used by tools) ──────────────────────────


def file_hash(ws: Any, rel_path: str) -> dict[str, Any]:
    target = res.require_regular_file(ws, rel_path)
    rel = res.relative(ws, target)
    return {"status": "ok", "path": rel, "algorithm": "sha256", "sha256": hash_file(target), "size": target.stat().st_size}


def file_permissions(ws: Any, rel_path: str) -> dict[str, Any]:
    target = res.resolve(ws, rel_path)
    if not target.exists():
        raise err.FsError(err.PATH_NOT_FOUND, "That path isn't there.", path=res.relative(ws, target))
    rel = res.relative(ws, target)
    return {"status": "ok", "path": rel, "type": _file_type(target), "permissions": permissions_for(target)}


def stat_for(ws: Any, rel_path: str) -> Optional[os.stat_result]:
    try:
        return res.resolve(ws, rel_path).stat()
    except (err.FsError, OSError):
        return None


__all__ = [
    "clear_hash_cache",
    "file_hash",
    "file_metadata",
    "file_permissions",
    "hash_file",
    "hash_text",
    "mime_type",
    "permissions_for",
    "stat_for",
]
