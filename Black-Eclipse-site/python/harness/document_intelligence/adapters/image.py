"""Image adapter — photographs, screenshots, scans and receipts as documents.

An image is a single-page document: deterministic OCR first, then a vision-model
analysis for layout/classification/captioning when a model is available. The
image bytes are stored through the vision asset store (content-addressed) when one
is present. An image with no OCR and no model is reported honestly, never faked.
"""

from __future__ import annotations

from typing import Any, Optional

from ..base import Capabilities, ParseContext, finalize_ir
from ..errors import DocumentError, DocumentErrorClass
from ..ir import BBox, Block, DocumentImage, DocumentIR, Page, Provenance
from .docx import _sha


class ImageAdapter:
    name = "image"
    kinds = ("image",)

    def capabilities(self) -> Capabilities:
        return Capabilities(text=True, structure=False, images=True, ocr=True, vision=True, render=False)

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR:
        ir = DocumentIR(kind="image", mime_type=_mime(data), file_name=name, byte_size=len(data))
        page = Page(index=0, label=name or "image", text_method="none")
        image = DocumentImage(
            image_id="img_0", content_type=_mime(data), byte_size=len(data), sha256=_sha(data), data=data,
            provenance=Provenance(method="native", status="observed", confidence=1.0, engine="image"),
        )
        try:
            from ...vision.image import decode_bytes

            decoded = decode_bytes(data, source=name or "image")
            image.width, image.height = decoded.width, decoded.height
            page.width, page.height = float(decoded.width), float(decoded.height)
            page.unit = "px"
            if ctx.asset_store is not None:
                try:
                    asset = ctx.asset_store.save(decoded, run_id=ctx.run_id, source_kind="document",
                                                 source_ref=(name or "")[:500])
                    image.asset_id = asset.asset_id
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            raise DocumentError(DocumentErrorClass.INVALID_IMAGE,
                                f"the image could not be decoded: {exc}", source_ref=name, cause=exc) from exc

        # Deterministic OCR.
        if ctx.ocr is not None and ctx.cfg.ocr_enabled:
            try:
                info = ctx.ocr(data)
                if hasattr(info, "__await__"):
                    info = await info
                text = getattr(info, "text", "") or ""
                if text:
                    page.text = text
                    page.has_text_layer = True
                    page.text_method = "ocr"
                    page.ocr_confidence = float(getattr(info, "confidence", 0.0) or 0.0)
                    image.ocr_text = text
                    page.blocks.append(Block(
                        kind="paragraph", text=text.strip(), block_id="b0", order=0,
                        provenance=Provenance(method="ocr", status="extracted",
                                              confidence=page.ocr_confidence or 0.5, engine="ocr"),
                    ))
            except Exception as exc:  # noqa: BLE001
                page.warnings.append(f"OCR failed: {exc}")

        # Vision analysis for layout / classification / captioning.
        if ctx.analyze_image is not None and ctx.cfg.vision_enabled:
            try:
                result = await ctx.analyze_image(
                    data, "Describe this image: what it is, its layout, and transcribe any text.",
                    mode="analyze",
                )
                payload = result.to_dict() if hasattr(result, "to_dict") else result
                if isinstance(payload, dict) and payload.get("ok"):
                    description = str(payload.get("description") or "").strip()
                    if description:
                        page.blocks.append(Block(
                            kind="caption", text=description[:4000], block_id="b_caption", order=len(page.blocks),
                            provenance=Provenance(method="vision", status="observed",
                                                  confidence=float(payload.get("confidence", 0.6) or 0.6),
                                                  engine=str(payload.get("model") or "vision")),
                        ))
                        if not page.text:
                            page.text = description
                            page.text_method = "vision"
                    for obs in payload.get("observations") or []:
                        if isinstance(obs, dict) and obs.get("text"):
                            page.blocks.append(Block(
                                kind="paragraph", text=str(obs["text"])[:4000], block_id=f"b{len(page.blocks)}",
                                order=len(page.blocks),
                                provenance=Provenance(method="vision", status="observed",
                                                      confidence=float(obs.get("confidence", 0.5) or 0.5),
                                                      engine="vision"),
                            ))
            except Exception as exc:  # noqa: BLE001
                page.warnings.append(f"vision analysis unavailable: {exc}")

        page.images.append(image)
        ir.images.append(image)
        ir.pages.append(page)
        if not page.text:
            page.warnings.append("no text could be extracted (no OCR engine and no vision model)")
        return finalize_ir(ir, parser="image", sha256=_sha(data), data=data)


def _mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:2] == b"BM":
        return "image/bmp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:256].lstrip()
    if head.startswith(b"<svg") or b"<svg" in head:
        return "image/svg+xml"
    return "application/octet-stream"


__all__ = ["ImageAdapter"]
