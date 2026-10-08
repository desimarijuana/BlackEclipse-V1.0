"""The Document Intelligence orchestrator — the ONE processing pipeline.

    validate → cache → detect kind → adapter parse → OCR/vision (in-adapter,
    routed) → sections → entities → chunk → index → evidence → assess → READY

Every stage is bounded and emits telemetry. Nothing is faked: a stage that cannot
run is recorded as UNAVAILABLE/SKIPPED and the document becomes PARTIALLY_READY
rather than READY. The same file never reprocesses when its content hash matches a
fresh cache entry (unless forced).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from . import telemetry as tel
from .adapters import known_kinds
from .adapters.registry import get_adapter
from .base import Capabilities, ParseContext, build_sections, finalize_ir
from .chunking import Chunk, chunk_ir
from .compare import ComparisonResult, compare_documents
from .config import DocumentConfig, document_config
from .entities import extract_entities
from .errors import DocumentError, DocumentErrorClass
from .ir import DocumentIR, content_hash
from .ocr import OCRInfo, ocr_available, route_ocr
from .processing import ProcessingState, StageResult, assess_capabilities, resolve_state
from .query import QueryResult, query_rows
from .retrieval import RetrievalResult, search
from .security import read_local_file, scan_text, validate_source, ValidatedSource
from .store import DocumentStore

#: Bounded retry for transient parse failures (spec §56).
_MAX_PARSE_ATTEMPTS = 3


@dataclass
class DocumentContext:
    """Everything the orchestrator needs for one document operation."""

    run_settings: Any = None
    aux_settings: Any = None
    bridge: Any = None
    store: Optional[DocumentStore] = None            # durable document store
    asset_store: Any = None                          # vision asset store (binary tier)
    evidence_store: Any = None
    emitter: Any = None
    run_id: Optional[str] = None
    user_id: Optional[str] = None
    cfg: Optional[DocumentConfig] = None
    evidence_sink: Any = None                        # callable(list[str]) for the run's source collector
    force: bool = False


@dataclass
class ProcessedDocument:
    document_id: str
    version: int
    kind: str
    state: ProcessingState
    capabilities: dict[str, str]
    stages: list[StageResult]
    title: Optional[str]
    page_count: int
    sheet_count: int
    confidence: float
    text_method: str
    warnings: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    chunk_count: int = 0
    table_count: int = 0
    image_count: int = 0
    entity_count: int = 0
    cached: bool = False
    ir: Optional[DocumentIR] = None

    def to_dict(self, *, include_ir: bool = False, include_image_data: bool = False) -> dict[str, Any]:
        out = {
            "type": "document_result", "documentId": self.document_id, "version": self.version,
            "kind": self.kind, "state": self.state.value, "capabilities": self.capabilities,
            "stages": [s.to_dict() for s in self.stages], "title": self.title,
            "pageCount": self.page_count, "sheetCount": self.sheet_count, "confidence": self.confidence,
            "textMethod": self.text_method, "warnings": self.warnings, "evidenceIds": self.evidence_ids,
            "chunkCount": self.chunk_count, "tableCount": self.table_count, "imageCount": self.image_count,
            "entityCount": self.entity_count, "cached": self.cached,
        }
        if include_ir and self.ir is not None:
            out["ir"] = self.ir.to_dict(include_image_data=include_image_data)
        return out


async def process_document(
    *,
    data: Optional[bytes] = None,
    path: Optional[str] = None,
    name: str = "",
    mime: str = "",
    kind: Optional[str] = None,
    ctx: Optional[DocumentContext] = None,
    force: bool = False,
    version: Optional[int] = None,
) -> ProcessedDocument:
    """Parse, understand and index one document. Returns a truthful result."""
    ctx = ctx or DocumentContext()
    cfg = ctx.cfg or document_config()
    telemetry = tel.DocumentTelemetry(emitter=ctx.emitter, enabled=cfg.telemetry)
    started = time.perf_counter()
    stages: list[StageResult] = []

    telemetry.emit(tel.EVENT_REQUEST, {"name": name, "kind": kind, "sourceKind": "path" if path else "bytes"})

    if not cfg.enabled:
        raise DocumentError(DocumentErrorClass.SECURITY_BLOCKED, "the document subsystem is disabled", source_ref=name)

    # ── ingest + validate ─────────────────────────────────────────────────────
    stage_start = time.perf_counter()
    if data is None and path:
        data = read_local_file(path, cfg=cfg)
        name = name or path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    if data is None:
        raise DocumentError(DocumentErrorClass.INVALID_INPUT, "document bytes or a path are required", source_ref=name)

    validated: ValidatedSource = validate_source(data=data, name=name, mime=mime, kind=kind, cfg=cfg)
    stages.append(StageResult("validate", "PASS", duration_ms=_ms(stage_start)))
    telemetry.emit(tel.EVENT_VALIDATE, {"kind": validated.kind, "bytes": validated.byte_size, "macro": validated.macro})

    chash = content_hash(data)

    # ── cache ─────────────────────────────────────────────────────────────────
    if ctx.store is not None and cfg.cache_enabled and not force:
        cached_id = ctx.store.get_cached_document(chash)
        if cached_id:
            cached_doc = ctx.store.get_document(cached_id)
            if cached_doc and cached_doc.get("status") in ("READY", "PARTIALLY_READY"):
                telemetry.emit(tel.EVENT_CACHE_HIT, {"documentId": cached_id, "contentHash": chash})
                return _cached_result(cached_doc, ctx)
        telemetry.emit(tel.EVENT_CACHE_MISS, {"contentHash": chash})

    job_id = ctx.store.create_job(None, status=ProcessingState.VALIDATING.value) if ctx.store else None

    def _advance(state: ProcessingState, stage: Optional[str] = None) -> None:
        if ctx.store and job_id:
            ctx.store.update_job(job_id, status=state.value, stage=stage)

    # ── parse ─────────────────────────────────────────────────────────────────
    adapter = get_adapter(validated.kind)
    if adapter is None:
        if ctx.store and job_id:
            ctx.store.update_job(job_id, status=ProcessingState.FAILED.value, error="unsupported format")
        raise DocumentError(
            DocumentErrorClass.UNSUPPORTED_FORMAT,
            f"{validated.kind!r} is not a supported document format (supported: {', '.join(known_kinds())})",
            source_ref=name,
        )

    _advance(ProcessingState.PARSING, stage="parse")
    stage_start = time.perf_counter()
    parse_ctx = _parse_context(ctx, cfg)
    try:
        ir, attempts = await _parse_with_retry(adapter, data, name, validated.kind, parse_ctx, cfg)
    except DocumentError as exc:
        if ctx.store and job_id:
            ctx.store.update_job(job_id, status=ProcessingState.FAILED.value, error=exc.error_class.value)
        raise
    if attempts > 1:
        stages.append(StageResult("retry", "PASS", detail=f"{attempts} parse attempt(s)"))
    stages.append(StageResult("parse", "PASS", detail=f"{ir.page_count} page(s)", duration_ms=_ms(stage_start)))
    telemetry.emit(tel.EVENT_PARSE, {"kind": ir.kind, "pages": ir.page_count, "sheets": ir.sheet_count,
                                    "parser": ir.parser, "method": ir.text_method})

    # ── OCR / vision stage accounting ─────────────────────────────────────────
    ocr_pages = [p.index for p in ir.pages if p.text_method in ("ocr", "vision")]
    if ocr_pages:
        confidences = [p.ocr_confidence for p in ir.pages if p.ocr_confidence is not None]
        avg = sum(confidences) / len(confidences) if confidences else 0.0
        stages.append(StageResult("ocr", "PASS", detail=f"{len(ocr_pages)} page(s), mean confidence {avg:.2f}"))
        telemetry.emit(tel.EVENT_OCR, {"pages": ocr_pages[:50], "confidence": avg})
        if any(p.text_method == "vision" for p in ir.pages):
            stages.append(StageResult("vision", "PASS", detail="vision transcription used"))
            telemetry.emit(tel.EVENT_VISION, {"pages": ocr_pages[:50]})
    else:
        # No OCR needed; record whether OCR was even possible.
        stages.append(StageResult("ocr", "SKIPPED", detail="native text layer used"))
        if any(p.has_text_layer for p in ir.pages):
            stages.append(StageResult("vision", "SKIPPED", detail="not required"))
        else:
            stages.append(StageResult("vision", "UNAVAILABLE" if not ocr_available(cfg) else "SKIPPED"))

    # ── structuring: sections + entities ───────────────────────────────────────
    _advance(ProcessingState.STRUCTURING, stage="structure")
    if ir.pages and not ir.sections:
        ir.sections = build_sections(ir.pages)
    stage_start = time.perf_counter()
    det_entities = extract_entities(ir)
    ir.entities = det_entities
    stages.append(StageResult("structure", "PASS", detail=f"{len(ir.sections)} section(s), {len(det_entities)} entities",
                               duration_ms=_ms(stage_start)))

    # ── security scan of extracted text ─────────────────────────────────────────
    if cfg.injection_guard or cfg.sensitive_scan:
        sample = ir.plain_text(limit=100_000)
        scan = scan_text(sample)
        if scan.sensitive:
            ir.warnings.append("the document contains injection-like phrasing and/or secret/PII-shaped strings (treated as untrusted data)")
            ir.metadata["security"] = scan.to_dict()

    # ── chunk + index ─────────────────────────────────────────────────────────
    _advance(ProcessingState.INDEXING, stage="index")
    stage_start = time.perf_counter()
    chunks = chunk_ir(ir, cfg=cfg)
    if ctx.store is not None and cfg.index_enabled:
        try:
            ir.version = version or _next_version(ctx.store, ir)
            ctx.store.save_document(ir, run_id=ctx.run_id, source_ref=name, status="PROCESSING")
            ctx.store.save_ir(ir)
            ctx.store.save_chunks(chunks)
            ctx.store.save_tables(ir.document_id, ir.version, ir.tables)
            ctx.store.save_images(ir.document_id, ir.version, ir.images)
            ctx.store.save_entities(ir.document_id, ir.version, ir.entities)
            ctx.store.put_cache(chash, ir.document_id, kind=ir.kind, ttl_seconds=cfg.cache_ttl_seconds)
            stages.append(StageResult("index", "PASS", detail=f"{len(chunks)} chunk(s)", duration_ms=_ms(stage_start)))
            telemetry.emit(tel.EVENT_INDEX, {"documentId": ir.document_id, "chunks": len(chunks)})
        except Exception as exc:  # noqa: BLE001
            ir.warnings.append(f"indexing failed: {exc}")
            stages.append(StageResult("index", "FAIL", detail=str(exc)))
            telemetry.emit(tel.EVENT_ERROR, {"stage": "index", "error": str(exc)})
    else:
        stages.append(StageResult("index", "SKIPPED", detail="indexing disabled or no store"))

    # ── evidence ──────────────────────────────────────────────────────────────
    evidence_ids: list[str] = []
    if ctx.evidence_store is not None and chunks:
        from .evidence import record_document_evidence

        try:
            evidence_ids = record_document_evidence(ctx.evidence_store, chunks, ir)
            stages.append(StageResult("evidence", "PASS", detail=f"{len(evidence_ids)} evidence item(s)"))
            telemetry.emit(tel.EVENT_EVIDENCE, {"documentId": ir.document_id, "count": len(evidence_ids)})
        except Exception as exc:  # noqa: BLE001
            stages.append(StageResult("evidence", "FAIL", detail=str(exc)))
    else:
        stages.append(StageResult("evidence", "SKIPPED"))

    # ── assess + persist final state ────────────────────────────────────────────
    capabilities = assess_capabilities(ir, stages)
    state = resolve_state(capabilities)
    ir.metadata["capabilities"] = capabilities
    if ctx.store is not None and cfg.index_enabled and "index" in [s.stage for s in stages] and \
            any(s.stage == "index" and s.status == "PASS" for s in stages):
        try:
            ctx.store.save_document(ir, run_id=ctx.run_id, source_ref=name, status=state.value)
        except Exception:  # noqa: BLE001
            pass
    if ctx.store and job_id:
        ctx.store.update_job(job_id, status=state.value, stage="done",
                             document_id=ir.document_id, version=ir.version,
                             progress=1.0 if state == ProcessingState.READY else 0.5)

    telemetry.emit(tel.EVENT_STORE, {"documentId": ir.document_id, "state": state.value,
                                     "durationMs": _ms(started)})

    result = ProcessedDocument(
        document_id=ir.document_id, version=ir.version, kind=ir.kind, state=state,
        capabilities=capabilities, stages=stages, title=ir.title, page_count=ir.page_count,
        sheet_count=ir.sheet_count, confidence=ir.confidence, text_method=ir.text_method,
        warnings=list(ir.warnings), evidence_ids=evidence_ids, chunk_count=len(chunks),
        table_count=len(ir.tables), image_count=len(ir.images), entity_count=len(ir.entities),
        ir=ir,
    )

    if ctx.evidence_sink is not None:
        try:
            ctx.evidence_sink(evidence_ids)
        except Exception:  # noqa: BLE001
            pass
    return result


# ── helpers ─────────────────────────────────────────────────────────────────────

def _parse_context(ctx: DocumentContext, cfg: DocumentConfig) -> ParseContext:
    async def _ocr(image_bytes: bytes) -> OCRInfo:
        return await route_ocr(image_bytes, cfg=cfg, settings=ctx.run_settings)

    async def _analyze(image_bytes: bytes, question: str, mode: str = "analyze") -> Any:
        return await _vision_analyze(
            image_bytes, question, mode=mode, settings=ctx.run_settings, timeout_s=120.0,
            asset_store=ctx.asset_store, emitter=ctx.emitter, run_id=ctx.run_id,
        )

    return ParseContext(
        cfg=cfg, run_settings=ctx.run_settings, aux_settings=ctx.aux_settings, bridge=ctx.bridge,
        asset_store=ctx.asset_store, emitter=ctx.emitter, run_id=ctx.run_id, user_id=ctx.user_id,
        ocr=_ocr, vision_ocr=lambda b, i: _ocr(b), analyze_image=_analyze,
    )


async def _vision_analyze(
    image_bytes: bytes, question: str, *, mode: str, settings: Any, timeout_s: float,
    asset_store: Any = None, emitter: Any = None, run_id: Optional[str] = None,
) -> Any:
    """Analyze an embedded document image through the VISION ORCHESTRATOR.

    Routing (native-first, then any credentialed vision model) is owned by the
    vision subsystem, so a document whose run model is text-only still gets a real
    vision model when one is available — instead of sending the image to a model
    that cannot read it.
    """
    try:
        from ..vision.contracts import VisionInput
        from ..vision.orchestrator import VisionContext, orchestrate

        # `source_kind="bytes"` reads the bytes from `source` — the documented
        # seam `vision.load.resolve_source` supports.
        vision_input = VisionInput(
            source=image_bytes, source_kind="bytes",  # type: ignore[arg-type]
            question=question or "Describe this image.",
            mode="analyze", model_settings=settings,
            options={"mime": "image/png"},
            task_hint="document_analysis",
        )
        ctx = VisionContext(
            run_settings=settings, emitter=emitter, asset_store=asset_store, run_id=run_id,
        )
        return await orchestrate(vision_input, ctx)
    except Exception as exc:  # noqa: BLE001 - vision is best-effort for an embedded image
        return {"ok": False, "error": {"errorClass": "VISION_UNAVAILABLE", "message": str(exc)}}


async def _parse_with_retry(
    adapter: Any, data: bytes, name: str, kind: str, parse_ctx: ParseContext, cfg: DocumentConfig,
) -> tuple[DocumentIR, int]:
    """Parse with bounded retry for transient (retryable) failures only.

    A corrupted file / unsupported format / macro refusal is permanent and is
    raised immediately without retry (spec §56). Each attempt is bounded by the
    processing timeout.
    """
    attempts = 0
    delay = 0.25
    last: Optional[DocumentError] = None
    while attempts < _MAX_PARSE_ATTEMPTS:
        attempts += 1
        try:
            ir = await asyncio.wait_for(
                adapter.parse(data, name=name, kind=kind, ctx=parse_ctx),
                timeout=cfg.processing_timeout_seconds,
            )
            return ir, attempts
        except asyncio.TimeoutError as exc:
            last = DocumentError(DocumentErrorClass.TIMEOUT,
                                 f"parsing exceeded the {cfg.processing_timeout_seconds}s budget",
                                 source_ref=name, cause=exc)
        except DocumentError as exc:
            if not exc.retryable:
                raise
            last = exc
        except Exception as exc:  # noqa: BLE001 - a parser bug is classified, never swallowed
            last = DocumentError(DocumentErrorClass.PARSER_FAILURE, f"the parser failed: {exc}",
                                 source_ref=name, cause=exc)
        if attempts < _MAX_PARSE_ATTEMPTS and last is not None and last.retryable:
            await asyncio.sleep(delay)
            delay *= 2
            continue
        break
    assert last is not None
    raise last


def _next_version(store: DocumentStore, ir: DocumentIR) -> int:
    existing = store.get_document(ir.document_id)
    if existing and existing.get("contentHash") == ir.content_hash:
        return int(existing.get("currentVersion", 1) or 1)
    if existing:
        return int(existing.get("currentVersion", 1) or 1) + 1
    return 1


def _cached_result(cached_doc: dict[str, Any], ctx: DocumentContext) -> ProcessedDocument:
    document_id = cached_doc["documentId"]
    capabilities = (cached_doc.get("metadata") or {}).get("capabilities", {})
    return ProcessedDocument(
        document_id=document_id, version=int(cached_doc.get("currentVersion", 1) or 1),
        kind=cached_doc.get("kind", "unknown"),
        state=ProcessingState(cached_doc.get("status", "READY"))
        if cached_doc.get("status") in {s.value for s in ProcessingState} else ProcessingState.READY,
        capabilities=capabilities, stages=[StageResult("cache", "PASS", detail="content hash matched")],
        title=cached_doc.get("title"), page_count=int(cached_doc.get("pageCount", 0) or 0),
        sheet_count=int(cached_doc.get("sheetCount", 0) or 0),
        confidence=float(cached_doc.get("confidence", 0.0) or 0.0),
        text_method=cached_doc.get("textMethod", "none"), warnings=["served from the content-hash cache"],
        cached=True,
    )


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


# ── higher-level operations ──────────────────────────────────────────────────────

def search_document(store: DocumentStore, query: str, **kwargs: Any) -> RetrievalResult:
    return search(store, query, **kwargs)


def compare_documents_by_ir(a: DocumentIR, b: DocumentIR) -> ComparisonResult:
    return compare_documents(a, b)


def query_document(rows: list[list[str]], columns: list[str], sql: str, **kwargs: Any) -> QueryResult:
    return query_rows(rows, columns, sql, **kwargs)


def document_available_kinds() -> list[str]:
    return known_kinds()


__all__ = [
    "DocumentContext", "ProcessedDocument", "process_document",
    "search_document", "compare_documents_by_ir", "query_document", "document_available_kinds",
]
