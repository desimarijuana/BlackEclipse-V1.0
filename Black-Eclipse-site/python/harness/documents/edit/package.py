"""Preservation-first OOXML package access.

An Office file is a ZIP of XML parts. Editing one part must not disturb any
other part: embedded media, charts, pivots, custom XML, fonts and VBA all live
in sibling parts and are easy to lose with a library round-trip. This module
owns the one safe read/mutate/write path.

The contract is deliberately narrow:

* bytes in, bytes out (never a filesystem path),
* every original entry is kept, in order, with its ZIP metadata,
* parts not explicitly targeted are written from their original bytes,
* timestamps are normalised on request so ``source + plan`` is reproducible,
* encrypted or malformed containers are refused rather than repaired.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from typing import Optional

from ...document_intelligence.adapters.office import (
    MAX_PART_BYTES,
    MAX_PARTS,
    MAX_TOTAL_BYTES,
    parse_xml,
)

_DETERMINISTIC_TIME = (1980, 1, 1, 0, 0, 0)


class OoxmlError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PartRecord:
    name: str
    data: bytes
    date_time: tuple[int, int, int, int, int, int]
    compress_type: int
    external_attr: int
    internal_attr: int
    create_system: int
    comment: bytes
    extra: bytes


def _safe_part_name(name: str) -> str:
    value = (name or "").replace("\\", "/").strip()
    if not value or value.startswith("/") or value.startswith("../"):
        raise OoxmlError("EDIT_PART_INVALID", f"invalid package part name {name!r}")
    pieces = [piece for piece in value.split("/") if piece not in ("", ".")]
    if any(piece == ".." for piece in pieces):
        raise OoxmlError("EDIT_PART_INVALID", f"package part escapes the container {name!r}")
    return "/".join(pieces)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class OoxmlPackage:
    """A ZIP package whose untouched parts survive an edit verbatim."""

    def __init__(self, records: list[PartRecord], *, order: list[str], comment: bytes = b"") -> None:
        self._records = records
        self._order = order
        self._comment = comment
        self._parts: dict[str, bytes] = {record.name: record.data for record in records}
        self._dirty: set[str] = set()
        self._added: list[str] = []

    @classmethod
    def from_bytes(cls, data: bytes) -> "OoxmlPackage":
        if not data:
            raise OoxmlError("EDIT_EMPTY", "the source document is empty")
        if data[:2] != b"PK":
            raise OoxmlError("EDIT_NOT_OOXML", "the source is not a ZIP/OOXML container")
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise OoxmlError("EDIT_CORRUPTED", f"the ZIP container is corrupt: {exc}") from exc

        records: list[PartRecord] = []
        order: list[str] = []
        seen: set[str] = set()
        total = 0
        with archive:
            infos = archive.infolist()
            if len(infos) > MAX_PARTS:
                raise OoxmlError("EDIT_LIMIT", f"the package has {len(infos)} parts")
            for info in infos:
                name = _safe_part_name(info.filename)
                key = name.casefold()
                if key in seen:
                    raise OoxmlError("EDIT_DUPLICATE_PART", f"duplicate package part {name!r}")
                seen.add(key)
                if info.flag_bits & 0x1:
                    raise OoxmlError("EDIT_ENCRYPTED", "encrypted Office packages are not supported")
                if info.file_size > MAX_PART_BYTES:
                    raise OoxmlError("EDIT_LIMIT", f"part {name!r} is too large")
                total += info.file_size
                if total > MAX_TOTAL_BYTES:
                    raise OoxmlError("EDIT_LIMIT", "the package decompresses to too many bytes")
                try:
                    payload = archive.read(info.filename)
                except (zipfile.BadZipFile, RuntimeError) as exc:
                    raise OoxmlError("EDIT_CORRUPTED", f"part {name!r} could not be read: {exc}") from exc
                records.append(PartRecord(
                    name=name,
                    data=payload,
                    date_time=tuple(info.date_time),  # type: ignore[arg-type]
                    compress_type=info.compress_type,
                    external_attr=info.external_attr,
                    internal_attr=info.internal_attr,
                    create_system=info.create_system,
                    comment=info.comment or b"",
                    extra=info.extra or b"",
                ))
                order.append(name)
        return cls(records, order=order, comment=archive.comment or b"")

    @property
    def names(self) -> list[str]:
        return list(self._order)

    @property
    def dirty_parts(self) -> set[str]:
        return set(self._dirty)

    def has(self, name: str) -> bool:
        return name in self._parts

    def read(self, name: str) -> Optional[bytes]:
        return self._parts.get(name)

    def require(self, name: str) -> bytes:
        value = self._parts.get(name)
        if value is None:
            raise OoxmlError("EDIT_PART_MISSING", f"the package has no part {name!r}")
        return value

    def write(self, name: str, data: bytes) -> None:
        safe = _safe_part_name(name)
        if safe not in self._parts:
            self._added.append(safe)
            self._order.append(safe)
        self._parts[safe] = data
        self._dirty.add(safe)

    def remove(self, name: str) -> bool:
        safe = _safe_part_name(name)
        if safe not in self._parts:
            return False
        del self._parts[safe]
        self._order = [item for item in self._order if item != safe]
        self._dirty.discard(safe)
        if safe in self._added:
            self._added.remove(safe)
        return True

    def part_hashes(self) -> dict[str, str]:
        return {name: sha256_hex(self._parts[name]) for name in self._order}

    def parse(self, name: str):
        return parse_xml(self.require(name))

    def to_bytes(self, *, deterministic: bool = True) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            records = {record.name: record for record in self._records}
            for name in self._order:
                payload = self._parts[name]
                record = records.get(name)
                if record is None:
                    info = zipfile.ZipInfo(name, date_time=_DETERMINISTIC_TIME if deterministic else _DETERMINISTIC_TIME)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 0
                    archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED)
                    continue
                info = zipfile.ZipInfo(name, date_time=_DETERMINISTIC_TIME if deterministic else record.date_time)
                info.compress_type = record.compress_type
                info.external_attr = record.external_attr
                info.internal_attr = record.internal_attr
                info.create_system = record.create_system
                info.comment = record.comment
                info.extra = record.extra
                info.flag_bits = 0
                archive.writestr(info, payload, compress_type=record.compress_type)
            if self._comment:
                archive.comment = self._comment
        return buffer.getvalue()

    def verify_zip(self) -> None:
        try:
            with zipfile.ZipFile(io.BytesIO(self.to_bytes())) as archive:
                bad = archive.testzip()
                if bad is not None:
                    raise OoxmlError("EDIT_CORRUPTED", f"package part {bad!r} failed its CRC check")
        except zipfile.BadZipFile as exc:
            raise OoxmlError("EDIT_CORRUPTED", f"the edited container is not a valid ZIP: {exc}") from exc


__all__ = ["OoxmlError", "OoxmlPackage", "PartRecord", "sha256_hex"]
