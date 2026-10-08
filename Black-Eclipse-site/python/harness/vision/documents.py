"""Document / PDF vision.

A document page is first turned into text deterministically (PDF text layer when
present, OS OCR when the page is a scan), and only then — when the question needs
visual structure a text layer cannot give — is the rendered page sent to a vision
model. This keeps deterministic extraction cheap and reserves the model for
interpretation.

PDF support is deliberately layered and honest:

  * `pypdfium2` (a self-contained PDFium binding) is the preferred backend — it
    gives text extraction AND full page rasterization.
  * A pure-stdlib backend (`_StdlibPdf`) is the dependency-free fallback. It
    always extracts text from the page content streams (a real PDF text layer),
    and rasterizes a page only when Pillow is present and the page uses the common
    flate + standard-font encodings. When it cannot rasterize, it reports exactly
    that — the text is still returned, and the caller is told a visual analysis is
    unavailable, rather than being handed a fabricated page.

No PDF path is ever faked: the chosen backend and its method are recorded on the
`DocumentPage`.
"""

from __future__ import annotations

import io
import re
import zlib
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import VisionConfig, vision_config
from .contracts import VisionInput, VisionResult, VisionUsage, VisualObservation
from .errors import VisionError, VisionErrorClass
from .image import DecodedImage, decode_bytes
from .providers import call_model
from .routing import RoutingPlan

_NUMBER = re.compile(r"^\(?-?[\$€£¥]?\d[\d,]*\.?\d*%?\)?$")


def _pypdfium_available() -> bool:
    try:
        import pypdfium2  # noqa: F401,PLC0415

        return True
    except Exception:  # noqa: BLE001
        return False


def pdf_available() -> bool:
    """Whether ANY PDF backend is available (pypdfium2 or the stdlib fallback)."""
    return True


def pdf_capabilities() -> dict[str, Any]:
    """Report honestly which PDF backends/methods are available."""
    stdlib_raster = False
    try:
        from PIL import Image, ImageDraw  # noqa: F401,PLC0415

        stdlib_raster = True
    except Exception:  # noqa: BLE001
        stdlib_raster = False
    return {
        "pypdfium2": _pypdfium_available(),
        "stdlibText": True,
        "stdlibRaster": stdlib_raster,
        "textExtraction": True,
        "rasterization": _pypdfium_available() or stdlib_raster,
    }


def _read_pdf_bytes(source: Any) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    if isinstance(source, str):
        if source.lower().startswith(("http://", "https://")):
            raise VisionError(
                VisionErrorClass.SECURITY_BLOCKED,
                "remote PDFs must be fetched through the URL guard first",
                source_ref=source,
            )
        try:
            with open(source, "rb") as handle:  # noqa: PTH123
                return handle.read()
        except OSError as exc:
            raise VisionError(
                VisionErrorClass.NO_SOURCE, f"the PDF file could not be read: {exc}",
                source_ref=source, cause=exc,
            ) from exc
    raise VisionError(VisionErrorClass.INVALID_INPUT, "a PDF path or bytes are required")


def is_pdf_source(input: Any) -> bool:
    """Whether a `VisionInput` points at a PDF (by path, URL, MIME or magic)."""
    source = getattr(input, "source", "") or ""
    kind = getattr(input, "source_kind", "path")
    options = getattr(input, "options", {}) or {}
    mime = str(options.get("mime") or "").lower()
    if "pdf" in mime:
        return True
    if kind in ("path", "url") and isinstance(source, str) and source.lower().split("?")[0].endswith(".pdf"):
        return True
    if kind == "path" and isinstance(source, str):
        try:
            with open(source, "rb") as handle:  # noqa: PTH123
                return handle.read(5) == b"%PDF-"
        except OSError:
            return False
    if kind == "base64" and isinstance(source, str):
        stripped = source
        if stripped.startswith("data:"):
            header, _, stripped = stripped.partition(",")
            if "pdf" in header.lower():
                return True
        try:
            import base64  # noqa: PLC0415

            head = base64.b64decode(stripped[:32] + "==", validate=False)[:5]
            return head == b"%PDF-"
        except Exception:  # noqa: BLE001
            return False
    return False


@dataclass
class DocumentPage:
    index: int
    width: int
    height: int
    text: str = ""
    has_text_layer: bool = False
    ocr: Optional[dict[str, Any]] = None
    warnings: list[str] = field(default_factory=list)
    # How the text was obtained and whether the page can be rasterized.
    text_method: str = "none"           # pypdfium2 | stdlib | none
    raster_method: str = "none"         # pypdfium2 | stdlib | none

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index, "width": self.width, "height": self.height,
            "hasTextLayer": self.has_text_layer, "text": self.text[:20_000],
            "ocr": self.ocr, "warnings": self.warnings,
            "textMethod": self.text_method, "rasterMethod": self.raster_method,
        }


# ── backends ───────────────────────────────────────────────────────────────────


class _PypdfiumDoc:
    """The preferred backend: a thin wrapper over pypdfium2."""

    backend = "pypdfium2"

    def __init__(self, data: bytes) -> None:
        import pypdfium2 as pdfium  # noqa: PLC0415

        self._doc = pdfium.PdfDocument(data)
        self._closed = False

    def __len__(self) -> int:
        return len(self._doc)

    def page_size(self, index: int) -> tuple[float, float]:
        return self._doc[index].get_size()

    def text(self, index: int) -> str:
        textpage = self._doc[index].get_textpage()
        try:
            return textpage.get_text_range() or ""
        finally:
            try:
                textpage.close()
            except Exception:  # noqa: BLE001
                pass

    def render(self, index: int, scale: float) -> Any:
        bitmap = self._doc[index].render(scale=scale)
        return bitmap.to_pil().convert("RGB")

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self._doc.close()
            except Exception:  # noqa: BLE001
                pass


class _StdlibPdf:
    """A dependency-free PDF reader (text always; rasterization best-effort).

    Text extraction walks uncompressed and FlateDecode content streams and reads
    the `Tj`/`TJ` string operators. Rasterization renders those strings with Pillow
    using the standard (non-embedded) base-14 font metrics; it cannot render an
    arbitrary embedded font or vector art, and reports so honestly.
    """

    backend = "stdlib"

    _PAGES = re.compile(rb"/Type\s*/Page(?![sA-Za-z])")

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._streams = self._extract_streams(data)
        self._count = self._count_pages(data)
        self._pages = self._page_bounds(data)

    @staticmethod
    def _extract_streams(data: bytes) -> list[bytes]:
        streams: list[bytes] = []
        for match in re.finditer(rb"stream\r?\n?(.*?)\r?\n?endstream", data, re.DOTALL):
            raw = match.group(1)
            # A FlateDecode stream starts with the zlib header (0x78); try it, then
            # fall back to the raw bytes.
            decoded = None
            if raw[:1] == b"\x78":
                try:
                    decoded = zlib.decompress(raw)
                except Exception:  # noqa: BLE001
                    decoded = None
            streams.append(decoded if decoded is not None else raw)
        return streams

    @classmethod
    def _count_pages(cls, data: bytes) -> int:
        count = len(cls._PAGES.findall(data))
        return max(1, count)

    @staticmethod
    def _page_bounds(data: bytes) -> list[tuple[float, float]]:
        sizes: list[tuple[float, float]] = []
        for match in re.finditer(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]", data):
            try:
                x0, y0, x1, y1 = (float(match.group(i)) for i in range(1, 5))
                sizes.append((abs(x1 - x0), abs(y1 - y0)))
            except (TypeError, ValueError):
                continue
        return sizes

    def __len__(self) -> int:
        return self._count

    def page_size(self, index: int) -> tuple[float, float]:
        if index < len(self._pages):
            return self._pages[index]
        return (595.0, 842.0)  # A4 points (a stated default, not a fabrication of content)

    def _all_text_ops(self) -> list[list[str]]:
        per_stream: list[list[str]] = []
        for stream in self._streams:
            strings: list[str] = []
            for match in re.finditer(rb"\((?:\\.|[^\\()])*\)\s*Tj", stream):
                literal = match.group(0)[:-2].strip()
                strings.append(self._decode_literal(literal))
            for array in re.finditer(rb"\[(.*?)\]\s*TJ", stream, re.DOTALL):
                for part in re.finditer(rb"\((?:\\.|[^\\()])*\)", array.group(1)):
                    strings.append(self._decode_literal(part.group(0)))
            if strings:
                per_stream.append(strings)
        return per_stream

    @staticmethod
    def _decode_literal(literal: bytes) -> str:
        body = literal.strip()
        if body.startswith(b"(") and body.endswith(b")"):
            body = body[1:-1]
        try:
            text = body.decode("latin-1")
        except Exception:  # noqa: BLE001
            return ""
        # Unescape the PDF string escapes we can handle without guessing.
        text = text.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
        text = text.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
        return text

    def text(self, index: int) -> str:
        streams = self._all_text_ops()
        if not streams:
            return ""
        if index < len(streams):
            return " ".join(streams[index])
        return " ".join(" ".join(s) for s in streams)

    def render(self, index: int, scale: float) -> Any:
        if not _stdlib_raster_ok():
            raise VisionError(
                VisionErrorClass.UNSUPPORTED_FORMAT,
                "the stdlib PDF backend needs Pillow to rasterize a page; "
                "install Pillow or pypdfium2 for full PDF rendering",
            )
        from PIL import Image  # noqa: PLC0415

        width_pt, height_pt = self.page_size(index)
        width = max(1, int(width_pt * max(1.0, scale) / 2.0))
        height = max(1, int(height_pt * max(1.0, scale) / 2.0))
        canvas = Image.new("RGB", (width, height), (255, 255, 255))
        fonts = self._load_fonts()
        if fonts is None:
            raise VisionError(
                VisionErrorClass.UNSUPPORTED_FORMAT,
                "the stdlib PDF backend cannot rasterize this page (no usable font); "
                "install pypdfium2 for full PDF rendering",
            )
        from PIL import ImageDraw  # noqa: PLC0415

        draw = ImageDraw.Draw(canvas)
        streams = self._all_text_ops()
        lines = streams[index] if index < len(streams) else []
        y = int(height * 0.08)
        line_h = max(10, int(height * 0.024))
        for line in lines:
            draw.text((int(width * 0.07), y), line[:200], fill=(20, 20, 20), font=fonts)
            y += line_h
            if y > height - line_h:
                break
        return canvas

    def _load_fonts(self) -> Any:
        from PIL import ImageFont  # noqa: PLC0415

        for name in ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(name, 14)
            except Exception:  # noqa: BLE001
                continue
        try:
            return ImageFont.load_default()
        except Exception:  # noqa: BLE001
            return None

    def close(self) -> None:
        return None


def open_pdf(source: Any) -> Any:
    """Open a PDF, preferring pypdfium2 and falling back to the stdlib backend."""
    data = _read_pdf_bytes(source)
    if _pypdfium_available():
        try:
            return _PypdfiumDoc(data)
        except VisionError:
            raise
        except Exception:  # noqa: BLE001 - fall through to the stdlib backend
            pass
    try:
        return _StdlibPdf(data)
    except VisionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise VisionError(VisionErrorClass.INVALID_IMAGE, f"the PDF could not be opened: {exc}", cause=exc) from exc


def page_count(source: Any) -> int:
    doc = open_pdf(source)
    try:
        return len(doc)
    finally:
        doc.close()


def extract_page_text(source: Any, *, page_index: int = 0) -> DocumentPage:
    """Extract a page's text layer (empty when the page is a scan)."""
    data = _read_pdf_bytes(source)
    if _pypdfium_available():
        doc = open_pdf(data)
        try:
            if page_index < 0 or page_index >= len(doc):
                raise VisionError(VisionErrorClass.INVALID_INPUT, f"page {page_index} is out of range")
            width, height = doc.page_size(page_index)
            text = doc.text(page_index)
            return DocumentPage(
                index=page_index, width=int(width), height=int(height),
                text=text, has_text_layer=bool(text.strip()), text_method="pypdfium2",
                raster_method="pypdfium2",
            )
        finally:
            doc.close()
    doc = _StdlibPdf(data)
    if page_index < 0 or page_index >= len(doc):
        raise VisionError(VisionErrorClass.INVALID_INPUT, f"page {page_index} is out of range")
    width, height = doc.page_size(page_index)
    text = doc.text(page_index)
    raster = "stdlib" if _stdlib_raster_ok() else "none"
    warnings: list[str] = []
    if raster == "none":
        warnings.append("install pypdfium2 for full PDF rendering")
    return DocumentPage(
        index=page_index, width=int(width), height=int(height),
        text=text, has_text_layer=bool(text.strip()), text_method="stdlib",
        raster_method=raster, warnings=warnings,
    )


def _stdlib_raster_ok() -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401,PLC0415

        return True
    except Exception:  # noqa: BLE001
        return False


def render_page(source: Any, *, page_index: int = 0, scale: float = 2.0, cfg: Optional[VisionConfig] = None) -> DecodedImage:
    """Render a PDF page to a PNG `DecodedImage`."""
    cfg = cfg or vision_config()
    doc = open_pdf(source)
    try:
        if page_index < 0 or page_index >= len(doc):
            raise VisionError(VisionErrorClass.INVALID_INPUT, f"page {page_index} is out of range")
        try:
            pil = doc.render(page_index, scale)
        except VisionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise VisionError(
                VisionErrorClass.INVALID_IMAGE, f"the PDF page could not be rendered: {exc}", cause=exc
            ) from exc
        buffer = io.BytesIO()
        pil.convert("RGB").save(buffer, format="PNG")
        return decode_bytes(buffer.getvalue(), cfg=cfg, source=f"pdf:{page_index}", expected_mime="image/png")
    finally:
        doc.close()


# ── tables / financial lines ───────────────────────────────────────────────────

def parse_table(lines: list[str], *, min_columns: int = 2) -> list[list[str]]:
    """Best-effort deterministic table from whitespace/pipe-delimited lines.

    A line becomes a row when it splits into at least `min_columns` cells. This
    is the deterministic half; the vision model refines it when asked.
    """
    rows: list[list[str]] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if "|" in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
        else:
            cells = [c for c in re.split(r"\s{2,}|\t", line) if c]
        if len(cells) >= min_columns:
            rows.append(cells)
    return rows


def financial_lines(text: str) -> list[dict[str, Any]]:
    """Extract label→number pairs from a financial statement's text layer."""
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        tokens = line.split()
        if len(tokens) < 2:
            continue
        numbers = [t for t in tokens if _NUMBER.match(t)]
        if not numbers:
            continue
        label = " ".join(t for t in tokens if not _NUMBER.match(t)).strip()
        if not label:
            continue
        out.append({"label": label, "values": numbers})
    return out


_DOC_PROMPT = (
    "You are Eclipse's document-vision engine. Read the attached document page and "
    "answer the question from what is actually printed. Do not invent numbers.\n"
    "Question: {question}\n"
    "Reply with one JSON object:\n"
    '{{"description": "<answer>", "observations": [{{"text": "...", "region": null, "confidence": 0..1}}], '
    '"tables": [{{"rows": [["cell", "..."]]}}], "confidence": 0..1}}'
)


@dataclass
class DocumentOutcome:
    page: DocumentPage
    description: str
    observations: list[VisualObservation]
    tables: list[list[list[str]]]
    financials: list[dict[str, Any]]
    confidence: float
    warnings: list[str] = field(default_factory=list)
    ocr: Optional[dict[str, Any]] = None


async def analyze_document_page(
    decoded: DecodedImage,
    input: VisionInput,
    plan: RoutingPlan,
    *,
    page: Optional[DocumentPage] = None,
    timeout_s: float = 120.0,
    want_tables: bool = False,
) -> tuple[DocumentOutcome, Any]:
    """Analyze a rendered document page; deterministic text/OCR first, model second."""
    warnings: list[str] = []
    page = page or DocumentPage(index=int(input.options.get("page", 0)), width=decoded.width, height=decoded.height)
    tables: list[list[list[str]]] = []
    financials = financial_lines(page.text) if page.text else []

    if page.has_text_layer and page.text.strip():
        rows = parse_table(page.text.splitlines())
        if rows:
            tables.append(rows)

    description = ""
    observations: list[VisualObservation] = []
    confidence = 0.5
    result = None

    # A model call is warranted for interpretation / images / when no text layer.
    prompt = _DOC_PROMPT.format(question=input.question or "Summarize this page.")
    from .analyze import extract_json  # noqa: PLC0415

    try:
        result = await call_model(plan.settings, prompt, [decoded.image], task="document_analysis",
                                  timeout_s=timeout_s, structured=True, backend=plan.kind)
    except VisionError as exc:
        if page.has_text_layer and (page.text.strip() or tables):
            # Deterministic extraction succeeded; a model outage degrades, not fails.
            warnings.append(f"the vision model was unavailable ({exc.error_class.value}); returned the text layer only")
            return DocumentOutcome(
                page=page, description=page.text.strip()[:4000], observations=[],
                tables=tables, financials=financials, confidence=0.4, warnings=warnings, ocr=page.ocr,
            ), None
        raise

    payload = extract_json(result.text)
    if payload is None:
        warnings.append("the model reply was not valid JSON; returning deterministic extraction")
        description = page.text.strip()[:4000]
    else:
        description = str(payload.get("description") or page.text.strip()[:2000])
        for item in payload.get("observations", []) or []:
            if isinstance(item, dict) and item.get("text"):
                observations.append(VisualObservation(
                    text=str(item["text"]),
                    confidence=float(item.get("confidence", 0.5) or 0.5), method="model",
                    source={"page": page.index},
                ))
        for table in payload.get("tables", []) or []:
            if isinstance(table, dict) and isinstance(table.get("rows"), list):
                tables.append([[str(c) for c in row] for row in table["rows"] if isinstance(row, list)])
        try:
            confidence = float(payload.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5

    if page.has_text_layer and page.text.strip():
        observations.append(VisualObservation(
            text=page.text.strip()[:8000], kind="observed", method="deterministic",
            confidence=0.95, source={"page": page.index, "layer": "pdf_text"},
        ))
        confidence = max(confidence, 0.8)

    return DocumentOutcome(
        page=page, description=description, observations=observations,
        tables=tables, financials=financials, confidence=max(0.0, min(1.0, confidence)),
        warnings=warnings, ocr=page.ocr,
    ), result


def build_document_result(
    outcome: DocumentOutcome,
    result: Any,
    *,
    asset_id: Optional[str],
    provenance: Optional[dict[str, Any]],
) -> VisionResult:
    usage = VisionUsage(
        input_tokens=getattr(result, "usage", VisionUsage()).input_tokens,
        output_tokens=getattr(result, "usage", VisionUsage()).output_tokens,
        total_tokens=getattr(result, "usage", VisionUsage()).total_tokens,
    ) if result is not None else VisionUsage()
    return VisionResult(
        ok=True, mode="document", description=outcome.description,
        observations=outcome.observations, objects=outcome.observations,
        tables=[
            {"rows": rows, "page": outcome.page.index} for rows in outcome.tables
        ],
        structured={"financials": outcome.financials, "page": outcome.page.to_dict()},
        confidence=outcome.confidence,
        provider=getattr(result, "provider", None), model=getattr(result, "model", None),
        backend=getattr(result, "backend", "document") if result is not None else "document",
        latency_ms=getattr(result, "latency_ms", 0), usage=usage,
        provenance={**(provenance or {}), "document": {"page": outcome.page.index,
                                                         "hasTextLayer": outcome.page.has_text_layer,
                                                         "textMethod": outcome.page.text_method,
                                                         "rasterMethod": outcome.page.raster_method}},
        warnings=outcome.warnings, asset_id=asset_id,
    )


__all__ = [
    "pdf_available", "pdf_capabilities", "open_pdf", "page_count", "extract_page_text",
    "render_page", "parse_table", "financial_lines", "is_pdf_source",
    "DocumentPage", "DocumentOutcome", "analyze_document_page", "build_document_result",
]
