"""Encoding, BOM and line-ending handling + atomic writes.

Reads and writes never silently corrupt a file:

  * a UTF-8 BOM, UTF-16 LE/BE BOM is detected and PRESERVED on write;
  * the dominant line ending (LF or CRLF) is reported so a patch can keep it;
  * an undecodable byte sequence raises `INVALID_ENCODING` rather than writing
    replacement characters back over the user's file;
  * a write goes through `write_text_atomic` — a temp file in the same directory
    is flushed and then `os.replace`d over the target, so a crash never leaves a
    half-written source file.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import errors as err

# Bounded read for a text file the agent may edit. Larger files refuse rather
# than stream an unbounded blob into the model.
MAX_TEXT_BYTES = 4_000_000

_BOM_UTF8 = b"\xef\xbb\xbf"
_BOM_UTF16_LE = b"\xff\xfe"
_BOM_UTF16_BE = b"\xfe\xff"

SUPPORTED_ENCODINGS = ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be")


@dataclass(frozen=True)
class DecodedText:
    text: str          # BOM stripped; line endings preserved exactly
    encoding: str      # the encoding to re-encode with ("utf-8" when no BOM)
    had_bom: bool
    newline: str       # "\n" or "\r\n" — the dominant line ending

    def to_dict(self) -> dict[str, object]:
        return {"encoding": self.encoding, "bom": self.had_bom, "newline": self.newline}


def _detect_bom(raw: bytes) -> tuple[str, bool, int]:
    """Return `(base_encoding, had_bom, bom_len)` for a byte prefix."""
    if raw.startswith(_BOM_UTF8):
        return "utf-8", True, len(_BOM_UTF8)
    if raw.startswith(_BOM_UTF16_LE):
        return "utf-16-le", True, len(_BOM_UTF16_LE)
    if raw.startswith(_BOM_UTF16_BE):
        return "utf-16-be", True, len(_BOM_UTF16_BE)
    return "utf-8", False, 0


def detect_newline(text: str) -> str:
    """The dominant line ending: CRLF when it appears at all, else LF."""
    return "\r\n" if "\r\n" in text else "\n"


def decode(raw: bytes, *, encoding: Optional[str] = None) -> DecodedText:
    """Decode bytes to text, preserving BOM/encoding/line endings.

    An explicit `encoding` overrides detection (but the BOM is still respected
    for re-encoding). A byte sequence that cannot be decoded raises
    `INVALID_ENCODING` — never a silent lossy decode.
    """
    base, had_bom, bom_len = _detect_bom(raw)
    chosen = (encoding or base).lower()
    if chosen not in SUPPORTED_ENCODINGS:
        raise err.FsError(err.INVALID_ENCODING, f"The encoding {encoding!r} isn't supported.")
    payload = raw[bom_len:] if had_bom else raw
    try:
        text = payload.decode(chosen, errors="strict")
    except (UnicodeDecodeError, LookupError):
        if encoding is not None:
            raise err.FsError(err.INVALID_ENCODING, "That file couldn't be read as text.") from None
        # No explicit choice: try UTF-16 without a BOM as a last honest attempt.
        try:
            text = payload.decode("utf-16", errors="strict")
            chosen = "utf-16"
        except (UnicodeDecodeError, LookupError):
            raise err.FsError(err.INVALID_ENCODING, "That file couldn't be read as text.") from None
    return DecodedText(text=text, encoding=chosen, had_bom=had_bom, newline=detect_newline(text))


def encode(text: str, *, encoding: str = "utf-8", had_bom: bool = False) -> bytes:
    """Encode text back to bytes, restoring the BOM when the file had one."""
    base = encoding.lower()
    if base not in SUPPORTED_ENCODINGS:
        base = "utf-8"
    try:
        data = text.encode(base, errors="strict")
    except (UnicodeEncodeError, LookupError):
        raise err.FsError(err.INVALID_ENCODING, "That text couldn't be saved in the file's encoding.") from None
    if had_bom:
        # Restore the exact BOM the file carried. `utf-16` writes its own; the
        # explicit LE/BE and UTF-8 codecs do not, so prepend it here.
        if base == "utf-16-be" and not data.startswith(_BOM_UTF16_BE):
            data = _BOM_UTF16_BE + data
        elif base == "utf-16-le" and not data.startswith(_BOM_UTF16_LE):
            data = _BOM_UTF16_LE + data
        elif base in ("utf-8", "utf-8-sig") and not data.startswith(_BOM_UTF8):
            data = _BOM_UTF8 + data
    return data


def read_bytes(path: Path, *, limit: int = MAX_TEXT_BYTES) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise err.FsError(err.PATH_NOT_FOUND, "That file isn't there.", path=str(path)) from exc
    if size > limit:
        raise err.FsError(
            err.TOO_LARGE,
            f"That file is too large to open as text ({size} bytes).",
            path=str(path),
            details={"size": size, "limit": limit},
        )
    try:
        return path.read_bytes()
    except OSError as exc:
        raise err.FsError(err.PERMISSION_DENIED, "That file couldn't be read.", path=str(path)) from exc


def read_text(path: Path, *, encoding: Optional[str] = None, limit: int = MAX_TEXT_BYTES) -> DecodedText:
    return decode(read_bytes(path, limit=limit), encoding=encoding)


def write_text_atomic(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    had_bom: bool = False,
) -> int:
    """Atomically write `text`. Returns the number of bytes written.

    A temp file is created in the target's directory, written, flushed and
    `os.replace`d over the target — atomic on the same filesystem, so a crash
    never leaves a partial file.
    """
    data = encode(text, encoding=encoding, had_bom=had_bom)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = parent / f".{path.name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise err.FsError(err.PERMISSION_DENIED, "That file couldn't be saved.", path=str(path)) from exc
    return len(data)


__all__ = [
    "DecodedText",
    "MAX_TEXT_BYTES",
    "SUPPORTED_ENCODINGS",
    "decode",
    "detect_newline",
    "encode",
    "read_bytes",
    "read_text",
    "write_text_atomic",
]
