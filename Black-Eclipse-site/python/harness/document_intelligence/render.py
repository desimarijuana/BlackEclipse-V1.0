"""Document rendering — turn a document into page/slide images the vision system
can consume (spec §22).

Deterministic-first: a PDF page is rasterized through the vision subsystem's
backend. Office formats are converted with a system LibreOffice (`soffice`) when
one is installed, then the resulting PDF page is rasterized. When no renderer
exists the call fails honestly with installation guidance rather than returning a
blank or faked page. Rendered bytes are stored in the vision asset store
(content-addressed) when one is attached.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import DocumentConfig, document_config
from .errors import DocumentError, DocumentErrorClass

_SOFFICE_CANDIDATES = ("soffice", "libreoffice", "soffice.exe")
_CONVERTIBLE = frozenset({"docx", "pptx", "doc", "ppt", "xlsx", "xls", "odt", "odp", "ods", "rtf"})


@dataclass
class RenderedPage:
    data: bytes
    mime_type: str = "image/png"
    width: int = 0
    height: int = 0
    method: str = "none"
    asset_id: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        import base64

        return {
            "mimeType": self.mime_type, "width": self.width, "height": self.height,
            "method": self.method, "assetId": self.asset_id, "byteSize": len(self.data),
            "dataBase64": base64.b64encode(self.data).decode("ascii"),
            "warnings": self.warnings,
        }


def renderer_available(kind: str = "pdf") -> bool:
    if kind == "pdf":
        try:
            from ..vision.documents import pdf_capabilities

            return bool(pdf_capabilities().get("rasterization"))
        except Exception:  # noqa: BLE001
            return False
    if kind in _CONVERTIBLE:
        return find_soffice() is not None and renderer_available("pdf")
    return False


def find_soffice() -> Optional[str]:
    for candidate in _SOFFICE_CANDIDATES:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def render_page(
    data: bytes, *, kind: str, page_index: int = 0, scale: float = 2.0, name: str = "",
    cfg: Optional[DocumentConfig] = None, asset_store: Any = None, run_id: Optional[str] = None,
    owner: str = "local",
) -> RenderedPage:
    """Render one page/slide to a PNG `RenderedPage`."""
    cfg = cfg or document_config()
    if kind == "pdf":
        png, width, height = _render_pdf(data, page_index, scale)
        method = "pdf-raster"
    elif kind == "image":
        return RenderedPage(data=data, mime_type="image/png" if data[:4] == b"\x89PNG" else "image/jpeg",
                            method="passthrough")
    elif kind in _CONVERTIBLE:
        soffice = find_soffice()
        if soffice is None:
            raise DocumentError(
                DocumentErrorClass.UNSUPPORTED_FORMAT,
                f"rendering a {kind} needs LibreOffice (soffice) to convert it to PDF; install LibreOffice",
                source_ref=name,
            )
        pdf = _convert_to_pdf(soffice, data, kind, name)
        png, width, height = _render_pdf(pdf, page_index, scale)
        method = "soffice-pdf-raster"
    else:
        raise DocumentError(DocumentErrorClass.UNSUPPORTED_FORMAT, f"rendering is not supported for {kind}", source_ref=name)

    rendered = RenderedPage(data=png, width=width, height=height, method=method)
    if asset_store is not None:
        try:
            from ..vision.image import decode_bytes

            decoded = decode_bytes(png, source=f"render:{name}:{page_index}", expected_mime="image/png")
            asset = asset_store.save(
                decoded, run_id=run_id, source_kind="document", source_ref=name[:500],
                owner=owner,
            )
            rendered.asset_id = asset.asset_id
        except Exception as exc:  # noqa: BLE001 - storage is best-effort
            rendered.warnings.append(f"could not store the rendered page: {exc}")
    return rendered


def _render_pdf(data: bytes, page_index: int, scale: float) -> tuple[bytes, int, int]:
    from ..vision.documents import open_pdf

    try:
        doc = open_pdf(data)
    except Exception as exc:  # noqa: BLE001
        raise DocumentError(DocumentErrorClass.PARSER_FAILURE, f"the PDF could not be opened: {exc}", cause=exc) from exc
    try:
        if page_index < 0 or page_index >= len(doc):
            raise DocumentError(DocumentErrorClass.INVALID_INPUT, f"page {page_index} is out of range")
        try:
            pil = doc.render(page_index, scale)
        except Exception as exc:  # noqa: BLE001
            raise DocumentError(
                DocumentErrorClass.UNSUPPORTED_FORMAT,
                "the page could not be rasterized (install pypdfium2 or Pillow for rendering)",
                cause=exc,
            ) from exc
        buffer = io.BytesIO()
        pil.convert("RGB").save(buffer, format="PNG")
        return buffer.getvalue(), pil.width, pil.height
    finally:
        doc.close()


def _convert_to_pdf(soffice: str, data: bytes, kind: str, name: str) -> bytes:
    workdir = tempfile.mkdtemp(prefix="eclipse-render-")
    try:
        ext = os.path.splitext(name)[1] or f".{kind}"
        src_path = os.path.join(workdir, f"input{ext}")
        with open(src_path, "wb") as handle:
            handle.write(data)
        try:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", workdir, src_path],
                capture_output=True, timeout=180, check=False,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise DocumentError(DocumentErrorClass.PARSER_FAILURE, f"conversion failed: {exc}", cause=exc) from exc
        for candidate in os.listdir(workdir):
            if candidate.lower().endswith(".pdf"):
                with open(os.path.join(workdir, candidate), "rb") as handle:
                    return handle.read()
        raise DocumentError(DocumentErrorClass.PARSER_FAILURE, "the converter produced no PDF")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


__all__ = ["RenderedPage", "render_page", "renderer_available", "find_soffice"]
