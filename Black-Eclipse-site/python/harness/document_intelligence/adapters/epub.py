"""EPUB adapter — an e-book as an ordered sequence of XHTML documents.

Reads `META-INF/container.xml` → the OPF package → the spine, and turns each
spine document into a `Page` by running it through the same sanitizing HTML
pipeline the HTML adapter uses (active content stripped, text data only). No
external resource is ever fetched.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from ..base import Capabilities, ParseContext, finalize_ir
from ..errors import DocumentError, DocumentErrorClass
from ..ir import Block, DocumentIR, Page, Provenance
from ..security import sanitize_html
from .docx import _sha
from .office import (
    attr, find_local, iter_local, local, open_container, parse_xml,
    read_part, resolve_target, safe_names,
)

_TAG_RE = re.compile(r"<[^>]+>")


class EpubAdapter:
    name = "epub"
    kinds = ("epub",)

    def capabilities(self) -> Capabilities:
        return Capabilities(pages=True, text=True, structure=True, tables=True, images=True, links=True)

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        with open_container(data) as zf:
            safe_names(zf)
            container = parse_xml(read_part(zf, "META-INF/container.xml"))
            rootfile = None
            for rf in iter_local(container, "rootfile"):
                rootfile = attr(rf, "full-path")
                if rootfile:
                    break
            if not rootfile:
                raise DocumentError(DocumentErrorClass.CORRUPTED_FILE, "the EPUB has no package document")
            opf = parse_xml(read_part(zf, rootfile))
            if opf is None:
                raise DocumentError(DocumentErrorClass.CORRUPTED_FILE, "the EPUB package document is unreadable")

            manifest: dict[str, str] = {}
            for item in iter_local(opf, "item"):
                manifest[attr(item, "id")] = attr(item, "href")
            spine_ids = [attr(ref, "idref") for ref in iter_local(opf, "itemref")]

            ir = DocumentIR(kind="epub", mime_type="application/epub+zip", file_name=name, byte_size=len(data))
            ir.title = self._dc(opf, "title")
            ir.metadata = {k: v for k, v in {
                "creator": self._dc(opf, "creator"), "language": self._dc(opf, "language"),
                "identifier": self._dc(opf, "identifier"),
            }.items() if v}

            for index, idref in enumerate(spine_ids):
                href = manifest.get(idref)
                if not href:
                    continue
                part = resolve_target(rootfile, href)
                raw = read_part(zf, part)
                if raw is None:
                    continue
                html = raw.decode("utf-8", errors="replace")
                clean, _ = sanitize_html(html)
                page = Page(index=index, label=href, text_method="native")
                page.text = _strip_tags(clean)
                page.has_text_layer = bool(page.text.strip())
                page.blocks.append(Block(
                    kind="paragraph", text=page.text.strip()[:50_000], block_id=f"b0", order=0,
                    provenance=Provenance(method="native", status="extracted", confidence=0.9, engine="epub"),
                ))
                ir.pages.append(page)

            return finalize_ir(ir, parser="epub", sha256=_sha(data), data=data)

    def _dc(self, opf: Any, name: str) -> Optional[str]:
        for el in opf.iter():
            if local(el.tag) == name and el.text:
                return el.text.strip()
        return None


def _strip_tags(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return re.sub(r"[ \t]+", " ", text).strip()


__all__ = ["EpubAdapter"]
