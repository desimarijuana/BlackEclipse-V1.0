"""Shared helpers for OOXML / ODF containers (docx, pptx, xlsx, ...).

Every Office file is a ZIP of XML parts. These helpers read parts *in memory*
(never extracting to disk), with per-entry and total byte guards so a zip bomb
cannot exhaust memory. XML is parsed with the stdlib `ElementTree`; untrusted
content is data only and is never evaluated.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any, Iterable, Optional
from xml.etree import ElementTree as ET

from ..errors import DocumentError, DocumentErrorClass

#: Per-part and aggregate ceilings while reading a container (defence in depth;
#: the archive guard also applies before we reach here).
MAX_PART_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_PARTS = 20_000


def open_container(data: bytes) -> zipfile.ZipFile:
    if data[:2] != b"PK":
        raise DocumentError(DocumentErrorClass.CORRUPTED_FILE, "not a ZIP/OOXML container")
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DocumentError(DocumentErrorClass.CORRUPTED_FILE, f"the container is corrupt: {exc}", cause=exc) from exc


def safe_names(zf: zipfile.ZipFile) -> list[str]:
    infos = zf.infolist()
    if len(infos) > MAX_PARTS:
        raise DocumentError(DocumentErrorClass.DECOMPRESSION_BOMB, f"the container has {len(infos)} parts")
    total = 0
    for info in infos:
        total += info.file_size
        if info.file_size > MAX_PART_BYTES:
            raise DocumentError(DocumentErrorClass.DECOMPRESSION_BOMB, f"part {info.filename!r} is too large")
        if total > MAX_TOTAL_BYTES:
            raise DocumentError(DocumentErrorClass.DECOMPRESSION_BOMB, "the container's uncompressed size is too large")
    return [i.filename for i in infos]


def read_part(zf: zipfile.ZipFile, name: str) -> Optional[bytes]:
    try:
        info = zf.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_PART_BYTES:
        raise DocumentError(DocumentErrorClass.DECOMPRESSION_BOMB, f"part {name!r} is too large")
    try:
        return zf.read(name)
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise DocumentError(DocumentErrorClass.CORRUPTED_FILE, f"part {name!r} could not be read: {exc}", cause=exc) from exc


def parse_xml(data: Optional[bytes]) -> Optional[ET.Element]:
    if data is None:
        return None
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        # Real Office parts are occasionally malformed (unbound namespace
        # prefixes, stray entities). Recover leniently with lxml when present so a
        # single bad metadata part never fails the whole document; only refuse when
        # no recovering parser can read it at all.
        recovered = _recover_xml(data)
        if recovered is not None:
            return recovered
        raise DocumentError(DocumentErrorClass.CORRUPTED_FILE, f"an XML part is malformed: {exc}", cause=exc) from exc


def _recover_xml(data: bytes) -> Optional[ET.Element]:
    try:
        from lxml import etree as lxml_etree  # noqa: PLC0415

        parser = lxml_etree.XMLParser(recover=True, resolve_entities=False, no_network=True, huge_tree=False)
        root = lxml_etree.fromstring(data, parser=parser)
        if root is None:
            return None
        return ET.fromstring(lxml_etree.tostring(root))
    except Exception:  # noqa: BLE001
        return None


def local(tag: str) -> str:
    """The local name of a `{namespace}tag` element/attribute name."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def iter_local(root: Optional[ET.Element], name: str) -> Iterable[ET.Element]:
    if root is None:
        return
    for el in root.iter():
        if local(el.tag) == name:
            yield el


def find_local(root: Optional[ET.Element], name: str) -> Optional[ET.Element]:
    for el in iter_local(root, name):
        return el
    return None


def text_of(el: Optional[ET.Element], *, depth: int = 0) -> str:
    """Concatenate all descendant text of an element (e.g. a `<w:t>` run chain)."""
    if el is None:
        return ""
    parts: list[str] = []
    for node in el.iter():
        if node.text and local(node.tag) in ("t", "text", "instrText", "v"):
            parts.append(node.text)
    return "".join(parts)


def attr(el: Optional[ET.Element], name: str, default: str = "") -> str:
    if el is None:
        return default
    for key, value in el.attrib.items():
        if local(key) == name:
            return value
    return default


_WS_RE = re.compile(r"[ \t]+")


def clean_text(text: str) -> str:
    if not text:
        return ""
    return _WS_RE.sub(" ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def rel_attr(el: Optional[ET.Element], name: str = "id") -> str:
    """Return the RELATIONSHIP-namespaced attribute value (e.g. `r:id`).

    OOXML elements often carry both a plain `id` and a namespaced `r:id`; the
    relationship one is the one that resolves through `.rels`, so it must win.
    """
    if el is None:
        return ""
    fallback = ""
    for key, value in el.attrib.items():
        if local(key) == name:
            if "}" in key:  # a namespaced attribute (r:id)
                return value
            fallback = fallback or value
    return fallback


def rels_map(zf: zipfile.ZipFile, part: str) -> dict[str, str]:
    """Return id -> target for a part's `_rels` file (e.g. `word/_rels/document.xml.rels`)."""
    directory, _, base = part.rpartition("/")
    rels_name = f"{directory}/_rels/{base}.rels" if directory else f"_rels/{base}.rels"
    root = parse_xml(read_part(zf, rels_name))
    out: dict[str, str] = {}
    for rel in iter_local(root, "Relationship"):
        rid = attr(rel, "Id")
        target = attr(rel, "Target")
        if rid and target:
            out[rid] = target
    return out


def resolve_target(base_part: str, target: str) -> str:
    """Resolve an OOXML relationship target against the part that referenced it."""
    if target.startswith("/"):
        return target.lstrip("/")
    directory = base_part.rpartition("/")[0]
    stack = directory.split("/") if directory else []
    for piece in target.split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if stack:
                stack.pop()
        else:
            stack.append(piece)
    return "/".join(stack)


__all__ = [
    "open_container", "safe_names", "read_part", "parse_xml", "local", "iter_local",
    "find_local", "text_of", "attr", "rel_attr", "clean_text", "rels_map", "resolve_target",
    "MAX_PART_BYTES", "MAX_TOTAL_BYTES", "MAX_PARTS",
]
