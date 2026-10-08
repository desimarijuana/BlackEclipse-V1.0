"""Textual + structured-data adapters: Markdown, MDX, TXT, HTML, JSON, JSONL,
XML, YAML, TOML.

These formats have no fixed paging, so each becomes a single `Page` whose blocks
preserve structure (headings, paragraphs, lists, code, tables, links). HTML is
sanitized of active content before anything is read (spec §15/§31); JSON/XML/YAML/
TOML get schema inference and a bounded, navigable projection (spec §14). Nothing
here executes scripts or resolves external resources.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from xml.etree import ElementTree as ET

from ..base import Capabilities, ParseContext, finalize_ir
from ..ir import BBox, Block, DocumentImage, DocumentIR, Page, Provenance, Table, TableCell
from ..security import sanitize_html, scan_text
from .docx import _sha

# ── Markdown / plain text ───────────────────────────────────────────────────────

_ATX = re.compile(r"^(#{1,6})\s+(.*)$")
_SETEXT = re.compile(r"^(=+|-{2,})\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)(.*)$")
_LIST = re.compile(r"^\s*([-*+]|\d+[.)])\s+(.*)$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)")
_MD_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")


class MarkdownAdapter:
    name = "markdown"
    kinds = ("markdown", "mdx", "txt")

    def capabilities(self) -> Capabilities:
        return Capabilities(text=True, structure=True, tables=True, links=True, entities=True)

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        text = _decode_text(data)
        ir = DocumentIR(kind=kind, mime_type="text/markdown" if kind != "txt" else "text/plain",
                        file_name=name, byte_size=len(data))
        page = Page(index=0, label="document", text=text, has_text_layer=bool(text), text_method="native")
        order = 0
        lines = text.splitlines()
        i = 0
        in_code = False
        while i < len(lines):
            line = lines[i]
            fence = _FENCE.match(line)
            if fence:
                in_code = not in_code
                i += 1
                continue
            if in_code:
                i += 1
                continue
            atx = _ATX.match(line)
            if atx:
                _append(page, Block(kind="heading", text=atx.group(2).strip(), level=len(atx.group(1)),
                                    block_id=f"b{order}", order=order, provenance=_native(0.98)))
                order += 1
                i += 1
                continue
            if i + 1 < len(lines) and _SETEXT.match(lines[i + 1]) and line.strip():
                level = 1 if lines[i + 1].strip().startswith("=") else 2
                _append(page, Block(kind="heading", text=line.strip(), level=level, block_id=f"b{order}",
                                    order=order, provenance=_native(0.98)))
                order += 1
                i += 2
                continue
            if _MD_TABLE_ROW.match(line) and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|", lines[i + 1] or ""):
                rows, consumed = _read_md_table(lines, i)
                table = Table(table_id=f"table_{order}", rows=rows, headers=rows[0] if rows else [],
                              provenance=_native(0.95))
                page.tables.append(table)
                _append(page, Block(kind="table", text="", table_id=table.table_id, block_id=f"b{order}",
                                    order=order, provenance=_native(0.95)))
                order += 1
                i += consumed
                continue
            list_match = _LIST.match(line)
            if list_match:
                _append(page, Block(kind="list_item", text=list_match.group(2).strip(), block_id=f"b{order}",
                                    order=order, provenance=_native(0.95)))
                order += 1
                i += 1
                continue
            links = [m.group(2) for m in _LINK.finditer(line)]
            if line.strip():
                _append(page, Block(kind="paragraph", text=line.strip(), block_id=f"b{order}", order=order,
                                    links=links, provenance=_native(0.95)))
                order += 1
            i += 1
        ir.pages.append(page)
        return finalize_ir(ir, parser="markdown", sha256=_sha(data), data=data)


class TxtAdapter(MarkdownAdapter):
    name = "txt"
    kinds = ("txt",)


# ── HTML ────────────────────────────────────────────────────────────────────────

class HtmlAdapter:
    name = "html"
    kinds = ("html", "htm")

    def capabilities(self) -> Capabilities:
        return Capabilities(text=True, structure=True, tables=True, images=True, links=True, render=True)

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        raw = _decode_text(data)
        clean, warnings = sanitize_html(raw) if ctx.cfg.injection_guard or True else (raw, [])
        ir = DocumentIR(kind="html", mime_type="text/html", file_name=name, byte_size=len(data))
        page = Page(index=0, label="document", text_method="native")
        page.warnings.extend(warnings)

        try:
            from bs4 import BeautifulSoup  # noqa: PLC0415

            soup = BeautifulSoup(clean, "html.parser")
        except Exception:  # noqa: BLE001 - fall back to a regex strip
            soup = None

        if soup is not None:
            if soup.title and soup.title.string:
                ir.title = soup.title.string.strip()
            page.text = "\n".join(t for t in soup.stripped_strings)
            page.has_text_layer = bool(page.text)
            order = 0
            for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "blockquote"]):
                text = tag.get_text(" ", strip=True)
                if not text:
                    continue
                name_tag = tag.name
                if name_tag.startswith("h"):
                    kind_ = "heading"
                    level = int(name_tag[1])
                elif name_tag == "li":
                    kind_, level = "list_item", None
                elif name_tag == "pre":
                    kind_, level = "code", None
                elif name_tag == "blockquote":
                    kind_, level = "quote", None
                else:
                    kind_, level = "paragraph", None
                links = [a.get("href") for a in tag.find_all("a") if a.get("href") and not str(a.get("href")).lower().startswith("javascript:")]
                _append(page, Block(kind=kind_, text=text, level=level, block_id=f"b{order}", order=order,
                                    links=[str(x) for x in links], provenance=_native(0.92)))
                order += 1
            for i, table_tag in enumerate(soup.find_all("table")):
                rows = []
                for tr in table_tag.find_all("tr"):
                    cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                    if cells:
                        rows.append(cells)
                if rows:
                    page.tables.append(Table(table_id=f"table_{i}", rows=rows, headers=rows[0],
                                             provenance=_native(0.9)))
            for a in soup.find_all("a"):
                href = a.get("href")
                if href and not str(href).lower().startswith(("javascript:", "#")):
                    page.links.append(str(href))
            for i, img in enumerate(soup.find_all("img")):
                src = img.get("src")
                page.images.append(DocumentImage(
                    image_id=f"img_{i}", content_type="image/*", caption=img.get("alt") or None,
                    provenance=Provenance(method="native", status="observed", confidence=0.8, engine="html"),
                    details={"src": str(src)} if src else {},
                ))

        # Metadata.
        if soup is not None:
            for meta in soup.find_all("meta"):
                key = meta.get("name") or meta.get("property")
                if key and meta.get("content"):
                    ir.metadata[str(key)] = str(meta.get("content"))
        ir.pages.append(page)
        return finalize_ir(ir, parser="html", sha256=_sha(data), data=data)


# ── structured data ─────────────────────────────────────────────────────────────

class DataAdapter:
    name = "data"
    kinds = ("json", "jsonl", "xml", "yaml", "toml")

    def capabilities(self) -> Capabilities:
        return Capabilities(text=True, structure=True, entities=True)

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        text = _decode_text(data)
        ir = DocumentIR(kind=kind, mime_type=_data_mime(kind), file_name=name, byte_size=len(data))
        page = Page(index=0, label="document", text_method="native")
        value, schema, error = _load_structured(text, kind)
        if error:
            page.warnings.append(error)
        if value is not None:
            schema = infer_schema(value)
            ir.metadata["schema"] = schema
            ir.entities = _data_entities(value)
            _flatten_blocks(value, page, order_start=0, prefix="")
            page.text = json.dumps(_bounded(value), ensure_ascii=False, default=str)[:200_000]
            page.has_text_layer = bool(page.text)
        else:
            page.text = text[:200_000]
            page.has_text_layer = bool(page.text)
        ir.pages.append(page)
        return finalize_ir(ir, parser=kind, sha256=_sha(data), data=data)


def _data_mime(kind: str) -> str:
    return {"json": "application/json", "jsonl": "application/x-ndjson", "xml": "application/xml",
            "yaml": "application/yaml", "toml": "application/toml"}.get(kind, "application/octet-stream")


def _load_structured(text: str, kind: str) -> tuple[Any, Optional[dict], Optional[str]]:
    try:
        if kind == "json":
            return json.loads(text), None, None
        if kind == "jsonl":
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
            return rows, None, None
        if kind == "yaml":
            import yaml  # noqa: PLC0415

            return yaml.safe_load(text), None, None
        if kind == "toml":
            import tomllib  # noqa: PLC0415

            return tomllib.loads(text), None, None
        if kind == "xml":
            root = ET.fromstring(text)
            return _xml_to_dict(root), None, None
    except Exception as exc:  # noqa: BLE001 - report, never crash the parse
        return None, None, f"the structured parse failed: {exc}"
    return None, None, None


def _xml_to_dict(el: ET.Element) -> dict[str, Any]:
    out: dict[str, Any] = {"tag": el.tag if "}" not in el.tag else el.tag.rsplit("}", 1)[-1]}
    if el.attrib:
        out["attributes"] = {k.rsplit("}", 1)[-1]: v for k, v in el.attrib.items()}
    children = list(el)
    if children:
        out["children"] = [_xml_to_dict(c) for c in children]
    if el.text and el.text.strip():
        out["text"] = el.text.strip()
    return out


def infer_schema(value: Any, *, depth: int = 0, max_depth: int = 8) -> dict[str, Any]:
    """A bounded, deterministic schema inference for JSON/XML/YAML/TOML."""
    if depth > max_depth:
        return {"type": "any"}
    if isinstance(value, dict):
        return {"type": "object", "properties": {str(k): infer_schema(v, depth=depth + 1) for k, v in list(value.items())[:200]}}
    if isinstance(value, list):
        if not value:
            return {"type": "array", "items": {"type": "any"}}
        sample = [infer_schema(v, depth=depth + 1) for v in value[:20]]
        return {"type": "array", "items": sample[0], "length": len(value)}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if value is None:
        return {"type": "null"}
    return {"type": "string"}


def _flatten_blocks(value: Any, page: Page, *, order_start: int, prefix: str) -> None:
    order = order_start

    def walk(node: Any, path: str) -> None:
        nonlocal order
        if isinstance(node, dict):
            for key, child in list(node.items())[:500]:
                walk(child, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for idx, child in enumerate(node[:200]):
                walk(child, f"{path}[{idx}]")
        else:
            text = f"{path} = {node}" if path else str(node)
            _append(page, Block(kind="paragraph", text=text[:2000], block_id=f"b{order}", order=order,
                                provenance=_native(0.95), details={"path": path}))
            order += 1

    walk(value, prefix)


def _data_entities(value: Any) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in list(value.items())[:100]:
            if isinstance(child, (str, int, float, bool)) and key.lower() in (
                "ticker", "symbol", "company", "name", "isin", "cik", "currency", "date", "id",
            ):
                entities.append({"type": key.lower(), "value": str(child), "path": key})
    return entities


def _bounded(value: Any, *, depth: int = 0, max_depth: int = 6, max_items: int = 500) -> Any:
    if depth > max_depth:
        return "…"
    if isinstance(value, dict):
        return {k: _bounded(v, depth=depth + 1, max_depth=max_depth, max_items=max_items)
                for k, v in list(value.items())[:max_items]}
    if isinstance(value, list):
        return [_bounded(v, depth=depth + 1, max_depth=max_depth, max_items=max_items) for v in value[:max_items]]
    return value


# ── shared helpers ───────────────────────────────────────────────────────────────

def _native(confidence: float, *, method: str = "native") -> Provenance:
    return Provenance(method=method, status="extracted", confidence=confidence, engine="native-parser")


def _append(page: Page, block: Block) -> None:
    page.blocks.append(block)


def _read_md_table(lines: list[str], start: int) -> tuple[list[list[str]], int]:
    rows: list[list[str]] = []
    i = start
    while i < len(lines) and _MD_TABLE_ROW.match(lines[i]):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if not re.match(r"^[\s:|-]+$", lines[i].strip().strip("|")):
            rows.append(cells)
        i += 1
    return rows, i - start


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


__all__ = ["MarkdownAdapter", "TxtAdapter", "HtmlAdapter", "DataAdapter", "infer_schema"]
