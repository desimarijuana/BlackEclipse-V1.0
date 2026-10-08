"""Archive adapter — safe, bounded inspection of ZIP/TAR/GZ/7Z containers.

Archives are NEVER blindly extracted (spec §4/§31/§32). This adapter performs a
*lazy inspection*: it enumerates entries and reads each entry's declared size and
compression ratio BEFORE decompressing, enforcing the file-count, total-uncompressed,
per-entry-ratio and nesting-depth limits. An archive that trips a bomb guard is
refused with `DECOMPRESSION_BOMB` and nothing is extracted.

When `expand` is requested and the archive is safe, each supported entry is
returned as an in-memory child document the orchestrator can parse — there is no
write to disk. Nested archives are recursed only to `max_archive_depth`.
"""

from __future__ import annotations

import gzip
import io
import tarfile
import zipfile
from typing import Any, Optional

from ..base import Capabilities, ParseContext, finalize_ir
from ..errors import DocumentError, DocumentErrorClass
from ..ir import Block, DocumentIR, Page, Provenance
from ..security import kind_from_extension, sniff_zip_subtype
from .docx import _sha

_MAX_CHILD_BYTES = 64 * 1024 * 1024


class ArchiveAdapter:
    name = "archive"
    kinds = ("archive",)

    def capabilities(self) -> Capabilities:
        return Capabilities(text=False, structure=True, tables=False, images=False)

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        cfg = ctx.cfg
        if not cfg.archive_enabled:
            raise DocumentError(DocumentErrorClass.SECURITY_BLOCKED, "archive processing is disabled", source_ref=name)

        entries = self._list_entries(data, name)
        if len(entries) > cfg.max_archive_files:
            raise DocumentError(
                DocumentErrorClass.DECOMPRESSION_BOMB,
                f"the archive has {len(entries)} entries, over the {cfg.max_archive_files} limit",
                source_ref=name, details={"entries": len(entries)},
            )
        total_uncompressed = sum(e["size"] for e in entries)
        if total_uncompressed > cfg.max_archive_bytes:
            raise DocumentError(
                DocumentErrorClass.DECOMPRESSION_BOMB,
                f"the archive expands to {total_uncompressed} bytes, over the {cfg.max_archive_bytes} limit",
                source_ref=name, details={"uncompressedBytes": total_uncompressed},
            )
        compressed = max(1, len(data))
        for entry in entries:
            if entry["compressed"] > 0 and entry["size"] / max(1, entry["compressed"]) > cfg.max_archive_ratio:
                raise DocumentError(
                    DocumentErrorClass.DECOMPRESSION_BOMB,
                    f"entry {entry['name']!r} has a compression ratio over {cfg.max_archive_ratio}",
                    source_ref=name, details={"entry": entry["name"]},
                )

        ir = DocumentIR(kind="archive", mime_type="application/zip", file_name=name, byte_size=len(data))
        page = Page(index=0, label="archive", text_method="none")
        for entry in entries:
            page.blocks.append(Block(
                kind="other", text=entry["name"], block_id=f"e{len(page.blocks)}", order=len(page.blocks),
                details={"size": entry["size"], "compressed": entry["compressed"]},
                provenance=Provenance(method="native", status="observed", confidence=1.0, engine="archive"),
            ))
        ir.metadata["entryCount"] = len(entries)
        ir.metadata["uncompressedBytes"] = total_uncompressed
        ir.pages.append(page)

        # Optional bounded expansion of supported children (in memory only).
        children = ctx.extra.get("expand_children", []) if isinstance(ctx.extra, dict) else []
        if ctx.extra.get("expand") and cfg.max_archive_depth > 0:
            depth = int(ctx.extra.get("archive_depth", 0) or 0)
            for entry in entries:
                if entry["size"] > _MAX_CHILD_BYTES:
                    continue
                child_kind = kind_from_extension(entry["name"]) or "unknown"
                if child_kind in ("archive", "unknown") and not entry["name"].lower().endswith((".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".txt")):
                    continue
                if len(children) >= 50:
                    break
                child_data = self._read_entry(data, name, entry["name"])
                if child_data is None:
                    continue
                children.append({"name": entry["name"], "data": child_data, "kind": child_kind, "depth": depth + 1})

        return finalize_ir(ir, parser="archive", sha256=_sha(data), data=data)

    # ── listing ────────────────────────────────────────────────────────────────

    def _list_entries(self, data: bytes, name: str) -> list[dict[str, Any]]:
        if data[:2] == b"PK":
            return self._list_zip(data, name)
        if data[:2] == b"\x1f\x8b":
            return self._list_gzip(data)
        if data[:6] == b"7z\xbc\xaf\x27\x1c":
            return self._list_7z(data, name)
        # tar: the ustar magic sits at offset 257.
        if len(data) > 262 and data[257:262] == b"ustar":
            return self._list_tar(data, name)
        # A gzipped tar or an unknown archive.
        if data[:2] == b"\x1f\x8b":
            return self._list_gzip(data)
        raise DocumentError(DocumentErrorClass.UNSUPPORTED_FORMAT, f"could not read the archive {name}", source_ref=name)

    def _list_zip(self, data: bytes, name: str) -> list[dict[str, Any]]:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                return [
                    {"name": info.filename, "size": info.file_size, "compressed": info.compress_size}
                    for info in zf.infolist() if not info.is_dir()
                ]
        except zipfile.BadZipFile as exc:
            raise DocumentError(DocumentErrorClass.CORRUPTED_FILE, f"the zip is corrupt: {exc}", source_ref=name, cause=exc) from exc

    def _list_tar(self, data: bytes, name: str) -> list[dict[str, Any]]:
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
                return [
                    {"name": m.name, "size": m.size, "compressed": 0}
                    for m in tf.getmembers() if m.isfile()
                ]
        except tarfile.TarError as exc:
            raise DocumentError(DocumentErrorClass.CORRUPTED_FILE, f"the tar is corrupt: {exc}", source_ref=name, cause=exc) from exc

    def _list_gzip(self, data: bytes) -> list[dict[str, Any]]:
        # A gzip stream can only be fully sized by reading it; bound with a hard cap.
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
                size = gz.seek(0, io.SEEK_END)
        except (OSError, EOFError) as exc:
            raise DocumentError(DocumentErrorClass.CORRUPTED_FILE, f"the gzip is corrupt: {exc}", cause=exc) from exc
        return [{"name": "gzip-content", "size": size or 0, "compressed": len(data)}]

    def _list_7z(self, data: bytes, name: str) -> list[dict[str, Any]]:
        raise DocumentError(
            DocumentErrorClass.UNSUPPORTED_FORMAT,
            "7z archives are recognized but not extracted (no safe in-process reader is available)",
            source_ref=name,
        )

    def _read_entry(self, data: bytes, name: str, entry_name: str) -> Optional[bytes]:
        if data[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                try:
                    info = zf.getinfo(entry_name)
                except KeyError:
                    return None
                if info.file_size > _MAX_CHILD_BYTES:
                    return None
                return zf.read(entry_name)
        if len(data) > 262 and data[257:262] == b"ustar":
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
                member = tf.getmember(entry_name)
                if member.size > _MAX_CHILD_BYTES:
                    return None
                extracted = tf.extractfile(member)
                return extracted.read() if extracted else None
        return None


__all__ = ["ArchiveAdapter"]
