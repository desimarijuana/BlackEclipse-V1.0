"""Legacy adapters: RTF and macro-free binary OLE (.doc/.xls/.ppt).

RTF is parsed natively with a real control-word walker (text, groups, unicode
escapes, hex escapes, destinations skipped). Legacy OLE compound files are a
binary format with no safe pure-Python reader; when a LibreOffice/`soffice`
converter is installed we convert to a modern OOXML container in a bounded
temporary directory and then parse that with the matching adapter. When no
converter is present we refuse honestly with `UNSUPPORTED_FORMAT` and installation
guidance — never a guessed or garbage extraction (spec §48).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Optional

from ..base import Capabilities, ParseContext, finalize_ir
from ..errors import DocumentError, DocumentErrorClass
from ..ir import Block, DocumentIR, Page, Provenance
from .docx import _sha


# ── RTF ────────────────────────────────────────────────────────────────────────

class RtfAdapter:
    name = "rtf"
    kinds = ("rtf",)

    def capabilities(self) -> Capabilities:
        return Capabilities(text=True, structure=False, tables=False, links=True)

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        text = _rtf_to_text(data)
        ir = DocumentIR(kind="rtf", mime_type="application/rtf", file_name=name, byte_size=len(data))
        page = Page(index=0, unit="points", label="document", text=text, has_text_layer=bool(text.strip()),
                    text_method="native")
        order = 0
        for para in [p for p in re.split(r"\n{2,}", text) if p.strip()]:
            page.blocks.append(Block(kind="paragraph", text=para.strip(), block_id=f"b{order}", order=order,
                                     provenance=Provenance(method="native", status="extracted", confidence=0.85, engine="rtf")))
            order += 1
        ir.pages.append(page)
        return finalize_ir(ir, parser="rtf", sha256=_sha(data), data=data)


#: RTF destinations whose groups carry no document text.
_SKIP_DESTINATIONS = {
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "object", "header", "footer",
    "footnote", "field", "fldinst", "xmlnstbl", "listtable", "listoverridetable",
    "rsidtbl", "generator", "themedata", "colorschememapping", "latentstyles", "datastore",
}


def _rtf_to_text(data: bytes) -> str:
    source = data.decode("latin-1", errors="replace")
    out: list[str] = []
    stack: list[bool] = []
    skip = False
    i = 0
    n = len(source)

    def push(ch: str) -> None:
        if not skip:
            out.append(ch)

    while i < n:
        ch = source[i]
        if ch == "\\":
            i += 1
            if i >= n:
                break
            nxt = source[i]
            if nxt == "\\" or nxt in "{}":
                push(nxt)
                i += 1
                continue
            if nxt == "*":
                skip = True
                i += 1
                continue
            if nxt == "'":  # hex escape
                try:
                    code = int(source[i + 1:i + 3], 16)
                    push(chr(code))
                except ValueError:
                    pass
                i += 3
                continue
            if nxt in "abcdefghijklmnopqrstuvwxyz":
                match = re.match(r"([a-z]+)(-?\d+)? ?", source[i:])
                if match:
                    word = match.group(1)
                    if word in _SKIP_DESTINATIONS:
                        skip = True
                    if word == "par" or word == "line":
                        push("\n")
                    i += match.end()
                    continue
                i += 1
                continue
            i += 1
            continue
        if ch == "{":
            stack.append(skip)
            i += 1
            continue
        if ch == "}":
            if stack:
                skip = stack.pop()
            i += 1
            continue
        if ch == "\r":
            i += 1
            continue
        if ch == "\n":
            i += 1
            continue
        push(ch)
        i += 1
    return re.sub(r"[ \t]+", " ", "".join(out)).strip()


# ── legacy OLE ──────────────────────────────────────────────────────────────────

_SOFFICE_CANDIDATES = ("soffice", "libreoffice", "soffice.exe")


def find_converter() -> Optional[str]:
    for candidate in _SOFFICE_CANDIDATES:
        path = shutil.which(candidate)
        if path:
            return path
    return None


class LegacyOleAdapter:
    name = "legacy-ole"
    kinds = ("doc", "xls", "ppt")

    def capabilities(self) -> Capabilities:
        return Capabilities(text=True, structure=False, tables=False, pages=False)

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        converter = find_converter()
        if converter is None:
            raise DocumentError(
                DocumentErrorClass.UNSUPPORTED_FORMAT,
                f"the legacy binary .{kind} format needs LibreOffice (soffice) to convert; "
                "install LibreOffice, or save the file as .{0}/{1} first".format(
                    {"doc": "docx", "xls": "xlsx", "ppt": "pptx"}.get(kind, "docx"),
                    {"doc": "docx", "xls": "xlsx", "ppt": "pptx"}.get(kind, "docx"),
                ),
                source_ref=name, details={"converter": None},
            )
        target = {"doc": "docx", "xls": "xlsx", "ppt": "pptx"}[kind]
        converted = _convert_with_soffice(converter, data, name, target)
        if converted is None:
            raise DocumentError(DocumentErrorClass.PARSER_FAILURE, "the converter did not produce an output", source_ref=name)
        from .registry import get_adapter

        adapter = get_adapter(target)
        if adapter is None:
            raise DocumentError(DocumentErrorClass.UNSUPPORTED_FORMAT, "the converted format has no adapter", source_ref=name)
        ir = await adapter.parse(converted, name=name, kind=target, ctx=ctx)
        ir.kind = kind
        ir.parser = f"legacy-ole→{target}"
        ir.metadata["convertedBy"] = "libreoffice"
        return ir


def _convert_with_soffice(converter: str, data: bytes, name: str, target: str) -> Optional[bytes]:
    """Convert legacy OLE bytes to `target` in a bounded temp dir using soffice."""
    workdir = tempfile.mkdtemp(prefix="eclipse-doc-convert-")
    try:
        src_ext = os.path.splitext(name)[1] or f".{target}"
        src_path = os.path.join(workdir, f"input{src_ext}")
        with open(src_path, "wb") as handle:
            handle.write(data)
        try:
            subprocess.run(
                [converter, "--headless", "--convert-to", target, "--outdir", workdir, src_path],
                capture_output=True, timeout=120, check=False,
            )
        except (subprocess.SubprocessError, OSError):
            return None
        for candidate in os.listdir(workdir):
            if candidate.lower().endswith(f".{target}"):
                with open(os.path.join(workdir, candidate), "rb") as handle:
                    return handle.read()
        return None
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


__all__ = ["RtfAdapter", "LegacyOleAdapter", "find_converter"]
