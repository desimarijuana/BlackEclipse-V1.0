"""Fixture builders for document-intelligence tests.

Builds minimal, valid documents in memory (OOXML, CSV, JSON, HTML, RTF, PDF,
archives, images) so tests need no binary assets on disk. Nothing here contacts
the network or a model.
"""

from __future__ import annotations

import io
import struct
import zipfile
import zlib
from typing import Optional


def make_zip(parts: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in parts.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            zf.writestr(name, data)
    return buffer.getvalue()


def make_docx(*, heading: str = "Introduction", body: str = "Hello world paragraph.",
              table: bool = True, comments: bool = False) -> bytes:
    table_xml = ""
    if table:
        table_xml = (
            "<w:tbl><w:tr>"
            "<w:tc><w:p><w:r><w:t>Item</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>Value</w:t></w:r></w:p></w:tc>"
            "</w:tr><w:tr>"
            "<w:tc><w:p><w:r><w:t>Revenue</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>125000</w:t></w:r></w:p></w:tc>"
            "</w:tr></w:tbl>"
        )
    document = (
        '<?xml version="1.0"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{heading}</w:t></w:r></w:p>'
        f'<w:p><w:r><w:t>{body}</w:t></w:r></w:p>'
        + table_xml
        + "</w:body></w:document>"
    )
    parts: dict[str, str | bytes] = {
        "[Content_Types].xml": "<Types/>",
        "word/document.xml": document,
        "docProps/core.xml": (
            '<cp:coreProperties xmlns:cp="x" xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/">'
            "<dc:title>Test Doc</dc:title><dcterms:created>2024-03-15T00:00:00Z</dcterms:created>"
            "</cp:coreProperties>"
        ),
        "docProps/app.xml": "<Properties><Application>Test</Application></Properties>",
    }
    if comments:
        parts["word/comments.xml"] = (
            '<w:comments xmlns:w="x"><w:comment w:id="1" w:author="A"><w:p><w:r><w:t>a note</w:t></w:r></w:p></w:comment></w:comments>'
        )
    return make_zip(parts)


def make_pptx() -> bytes:
    slide = (
        '<?xml version="1.0"?>'
        '<p:sld xmlns:a="a" xmlns:p="p" xmlns:r="r"><p:cSld>'
        "<p:spTree>"
        '<p:sp><p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>Quarterly Review</a:t></a:r></a:p></p:txBody></p:sp>'
        "<p:sp><p:txBody><a:p><a:r><a:t>Revenue grew 18 percent</a:t></a:r></a:p></p:txBody></p:sp>"
        '<p:graphicFrame><a:tbl><a:tr><a:tc><a:t>Region</a:t></a:tc><a:tc><a:t>Sales</a:t></a:tc></a:tr>'
        "<a:tr><a:tc><a:t>EMEA</a:t></a:tc><a:tc><a:t>500</a:t></a:tc></a:tr></a:tbl></p:graphicFrame>"
        '<p:graphicFrame><p:graphic><a:graphicData><c:chart xmlns:c="c" r:id="rIdChart"/></a:graphicData></p:graphic></p:graphicFrame>'
        "</p:spTree></p:cSld></p:sld>"
    )
    notes = (
        '<p:notes xmlns:a="a" xmlns:p="p"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Speaker note here</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:notes>'
    )
    return make_zip({
        "[Content_Types].xml": "<Types/>",
        "ppt/presentation.xml": (
            '<p:presentation xmlns:p="p" xmlns:r="r"><p:sldIdLst>'
            '<p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>'
        ),
        "ppt/_rels/presentation.xml.rels": (
            '<Relationships><Relationship Id="rId1" Type="slide" Target="slides/slide1.xml"/></Relationships>'
        ),
        "ppt/slides/slide1.xml": slide,
        "ppt/slides/_rels/slide1.xml.rels": (
            '<Relationships><Relationship Id="rIdChart" Type="chart" Target="../charts/chart1.xml"/>'
            '<Relationship Id="rIdNotes" Type="notesSlide" Target="../notesSlides/notesSlide1.xml"/></Relationships>'
        ),
        "ppt/notesSlides/notesSlide1.xml": notes,
        "docProps/core.xml": (
            '<cp:coreProperties xmlns:cp="x" xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:title>Deck</dc:title></cp:coreProperties>"
        ),
    })


def make_xlsx(*, hidden_sheet: bool = False, formula: bool = True) -> bytes:
    formula_cell = '<c r="B2"><f>A2*3</f><v>300</v></c>' if formula else '<c r="B2"><v>300</v></c>'
    sheet = (
        '<?xml version="1.0"?><worksheet xmlns="x"><sheetData>'
        '<row r="1"><c r="A1" t="inlineStr"><is><t>Metric</t></is></c><c r="B1" t="inlineStr"><is><t>Amount</t></is></c></row>'
        f'<row r="2"><c r="A2" t="inlineStr"><is><t>Revenue</t></is></c>{formula_cell}</row>'
        '<row r="3" hidden="1"><c r="A3" t="inlineStr"><is><t>Hidden</t></is></c></row>'
        "</sheetData>"
        '<mergeCells><mergeCell ref="A1:B1"/></mergeCells>'
        "</worksheet>"
    )
    sheets = '<sheet name="Sheet1" sheetId="1" r:id="rId1"/>'
    rels = '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
    parts: dict[str, str | bytes] = {
        "xl/workbook.xml": f'<workbook xmlns:r="r"><sheets>{sheets}</sheets><definedNames><definedName name="Rev">Sheet1!$B$2</definedName></definedNames></workbook>',
        "xl/_rels/workbook.xml.rels": f"<Relationships>{rels}</Relationships>",
        "xl/worksheets/sheet1.xml": sheet,
        "xl/sharedStrings.xml": "<sst/>",
    }
    if hidden_sheet:
        parts["xl/workbook.xml"] = (
            '<workbook xmlns:r="r"><sheets><sheet name="Visible" sheetId="1" r:id="rId1"/>'
            '<sheet name="Secret" sheetId="2" state="hidden" r:id="rId2"/></sheets></workbook>'
        )
        parts["xl/_rels/workbook.xml.rels"] = (
            '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>'
        )
        parts["xl/worksheets/sheet2.xml"] = "<worksheet><sheetData/></worksheet>"
    return make_zip(parts)


def make_odt() -> bytes:
    content = (
        '<?xml version="1.0"?>'
        '<office:document-content xmlns:office="o" xmlns:text="t" xmlns:table="tb">'
        "<office:body><office:text>"
        '<text:h text:outline-level="1">Title Heading</text:h>'
        "<text:p>An ODF paragraph.</text:p>"
        "<table:table><table:table-row><table:table-cell><text:p>X</text:p></table:table-cell>"
        "<table:table-cell><text:p>Y</text:p></table:table-cell></table:table-row></table:table>"
        "</office:text></office:body></office:document-content>"
    )
    return make_zip({
        "mimetype": "application/vnd.oasis.opendocument.text",
        "content.xml": content,
        "meta.xml": '<office:document-meta xmlns:office="o" xmlns:dc="d"><dc:title>ODF Title</dc:title></office:document-meta>',
    })


def make_epub() -> bytes:
    return make_zip({
        "mimetype": "application/epub+zip",
        "META-INF/container.xml": (
            '<container><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
        ),
        "OEBPS/content.opf": (
            '<package><metadata><dc:title xmlns:dc="d">Book</dc:title></metadata>'
            '<manifest><item id="c1" href="chap1.xhtml" media-type="application/xhtml+xml"/></manifest>'
            "<spine><itemref idref=\"c1\"/></spine></package>"
        ),
        "OEBPS/chap1.xhtml": "<html><body><h1>Chapter One</h1><p>It was a dark stormy night.</p></body></html>",
    })


def make_rtf() -> bytes:
    return rb"{\rtf1\ansi\deff0 {\fonttbl {\f0 Arial;}} \f0\fs24 Hello RTF world.\par Second line.}"


def make_csv() -> bytes:
    return b"region,revenue,churn\nEMEA,1000,false\nAPAC,2500,true\nAMER,1800,false\n"


def make_json() -> bytes:
    return b'{"company":"Acme","ticker":"NASDAQ:ACME","revenue":125000,"founded":"2010-01-15","segments":["a","b"]}'


def make_html() -> bytes:
    return (
        b"<html><head><title>Report</title>"
        b"<script>alert('x')</script><meta name='author' content='Jane'/></head>"
        b"<body><h1>Summary</h1><p>Revenue rose 18%.</p>"
        b"<table><tr><th>Y</th><th>V</th></tr><tr><td>2023</td><td>100</td></tr></table>"
        b"<a href='https://example.com'>link</a></body></html>"
    )


def make_markdown() -> bytes:
    return (
        b"# Title\n\nIntro paragraph.\n\n## Section A\n\n- first\n- second\n\n"
        b"| A | B |\n|---|---|\n| 1 | 2 |\n\n[link](https://example.com)\n"
    )


def make_pdf(*, pages: int = 1, text: bool = True) -> bytes:
    """A minimal PDF. `text=False` makes a blank (scanned-like) page."""
    objects: list[bytes] = []
    content = b"BT /F1 12 Tf 72 720 Td (Hello PDF world) Tj ET" if text else b""
    # Object numbering: 1=catalog, 2=pages, 3..(2+pages)=page objects, then font, then stream.
    font_obj = 3 + pages
    stream_obj = font_obj + 1
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{3 + i} 0 R" for i in range(pages))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode())
    for _ in range(pages):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {stream_obj} 0 R "
            f"/Resources << /Font << /F1 {font_obj} 0 R >> >> >>".encode()
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    stream = b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"
    objects.append(stream)

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode()
    return bytes(out)


def make_png(width: int = 8, height: int = 8) -> bytes:
    """A tiny valid PNG with no text (a solid colour)."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b""
    for _ in range(height):
        raw += b"\x00" + b"\xff\x00\x00" * width
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def make_zip_archive(files: Optional[dict[str, bytes]] = None) -> bytes:
    return make_zip(files or {"a.txt": "hello", "b.csv": "x,y\n1,2\n"})


def make_zip_bomb(*, entries: int = 5, each: int = 2_000_000) -> bytes:
    """A zip whose declared uncompressed size is huge (bomb guard should refuse)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(entries):
            zf.writestr(f"bomb_{i}.txt", b"\x00" * each)
    return buffer.getvalue()


def make_macro_docx() -> bytes:
    parts = {
        "[Content_Types].xml": "<Types/>",
        "word/document.xml": "<w:document xmlns:w=\"x\"><w:body><w:p><w:r><w:t>x</w:t></w:r></w:p></w:body></w:document>",
        "word/vbaProject.bin": b"\x00\x01MZ VBA payload",
    }
    return make_zip(parts)


def write_temp(tmp_path, name: str, data: bytes) -> str:
    import os

    path = os.path.join(str(tmp_path), name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path
