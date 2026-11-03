"""The Vision Orchestrator — the ONE entry point for a vision request.

Every vision tool calls `orchestrate(input, ctx)`. The orchestrator owns the
whole pipeline so no tool ever selects a provider or decodes an image itself:

    validate → resolve source → preprocess → security scan → store (asset)
      → capability detect → route (native-first) → cache lookup
      → dispatch by mode (analyze/ocr/ground/chart/document/compare)
      → fallback across permitted candidates on a fallbackable failure
      → normalize → cache store → telemetry → VisionResult

It never fakes success: a failure is a `VisionResult(ok=False, error=...)`, and
partial results (e.g. deterministic OCR succeeded, model unavailable) are
reported honestly with warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from . import telemetry as tel
from .analyze import analyze_image, build_result
from .cache import cache_key, get_cache
from .capabilities import record_vision_failure, record_vision_success
from .charts import analyze_chart, build_chart_result
from .compare import build_compare_result, compare_images
from .config import VisionConfig, vision_config
from .contracts import Region, VisionInput, VisionResult, VisionUsage, VisualObservation
from .documents import analyze_document_page, build_document_result, extract_page_text, pdf_available, render_page
from .errors import VisionError, VisionErrorClass
from .grounding import ground_image
from .image import DecodedImage, preprocess
from .load import resolve_source
from .ocr import run_ocr
from .providers import ModelCallResult
from .routing import RoutingPlan, plan_route
from .security import scan_text
from .storage import VisionAssetStore

#: Sensitive, ephemeral sources are stored with a short TTL unless the caller
#: explicitly asks to keep them (never persisted permanently by default, spec §35).
_EPHEMERAL_KINDS = frozenset({"screenshot", "clipboard", "browser"})
_SENSITIVE_TTL_SECONDS = 3600

#: Modes with NO deterministic path: with no usable vision model they fail
#: honestly. Other modes (ocr, ground, document, compare) have a deterministic
#: path and proceed, degrading with warnings when the model is unavailable.
_MODEL_REQUIRED_MODES = frozenset({"analyze", "describe", "chart"})


@dataclass
class VisionContext:
    """Everything the orchestrator needs for one request."""

    run_settings: Any = None
    aux_settings: Any = None
    emitter: Any = None
    bridge: Any = None                 # DataBridge for market verification
    asset_store: Optional[VisionAssetStore] = None
    run_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    cfg: Optional[VisionConfig] = None
    runtime: Any = None
    # Optional callback invoked with the finished result for evidence recording.
    evidence_sink: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


async def orchestrate(input: VisionInput, ctx: VisionContext) -> VisionResult:
    """Run the full vision pipeline for `input`."""
    cfg = ctx.cfg or vision_config()
    telemetry = tel.VisionTelemetry(emitter=ctx.emitter, enabled=cfg.telemetry)
    started_modes = {"mode": input.mode}
    telemetry.emit(tel.EVENT_REQUEST, {
        "mode": input.mode, "sourceKind": input.source_kind,
        "sensitive": input.sensitive, "question": bool(input.question),
    })

    if not cfg.enabled:
        return VisionResult.failure(
            VisionError(VisionErrorClass.SECURITY_BLOCKED, "the vision subsystem is disabled"),
            mode=input.mode,
        )

    # ── resolve + preprocess ──────────────────────────────────────────────────
    try:
        decoded, doc_page = await _resolve(input, cfg)
    except VisionError as exc:
        telemetry.emit(tel.EVENT_ERROR, {"stage": "resolve", **exc.to_dict()})
        return VisionResult.failure(exc, mode=input.mode)

    original_asset_id = decoded.asset_id
    try:
        processed = preprocess(decoded, cfg=cfg, region=input.region)
    except VisionError as exc:
        telemetry.emit(tel.EVENT_ERROR, {"stage": "preprocess", **exc.to_dict()})
        return VisionResult.failure(exc, mode=input.mode)
    telemetry.emit(tel.EVENT_PREPROCESS, {
        "originalSha": decoded.sha256, "processedSha": processed.sha256,
        "width": processed.width, "height": processed.height, "bytes": processed.byte_size,
    })

    # ── pre-flight sensitive scan (BEFORE any model call or storage) ─────────
    # The agent's `sensitive` flag is only a hint; a screenshot the agent did not
    # flag can still contain a credential or PII. The deterministic OCR pre-scan
    # runs here so the privacy policy can keep a sensitive frame off a cloud
    # provider — and so it is stored with a TTL — instead of uploading first and
    # discovering the secret afterward.
    preflight_scan = scan_text("")
    if cfg.sensitive_scan:
        try:
            from .security import preflight_scan as _preflight  # noqa: PLC0415

            preflight_scan = _preflight(decoded, cfg=cfg)
        except Exception:  # noqa: BLE001 - a failed pre-scan must not break the call
            preflight_scan = scan_text("")
    if preflight_scan.sensitive:
        input.sensitive = True
    telemetry.emit(tel.EVENT_SECURITY, {
        "stage": "preflight", "sensitive": preflight_scan.sensitive,
        "injectionSignals": len(preflight_scan.injection_signals),
        "credentialLike": preflight_scan.credential_like, "piiLike": preflight_scan.pii_like,
    })

    # ── store asset (provenance + dedup) ──────────────────────────────────────
    asset_id = original_asset_id
    if ctx.asset_store is not None:
        asset_id = _store_asset(ctx.asset_store, decoded, input, ctx, cfg, telemetry)

    # ── route (native-first) ──────────────────────────────────────────────────
    plan = plan_route(
        input, run_settings=ctx.run_settings, cfg=cfg, runtime=ctx.runtime, aux_settings=ctx.aux_settings,
    )
    telemetry.emit(tel.EVENT_ROUTE, plan.to_dict())
    # A plan with no usable model is only fatal for modes that genuinely require
    # one. Deterministic modes (ocr) and modes with a deterministic path
    # (ground via OCR, document via its text layer, compare via the pixel diff)
    # proceed and degrade honestly rather than failing early.
    if not plan.usable and input.mode in _MODEL_REQUIRED_MODES:
        error = VisionError(
            VisionErrorClass.PRIVACY_REFUSED if not plan.privacy.allow_cloud else VisionErrorClass.NO_VISION_MODEL,
            plan.reason,
        )
        telemetry.emit(tel.EVENT_ERROR, {"stage": "route", **error.to_dict()})
        return VisionResult.failure(error, mode=input.mode)

    # ── cache ─────────────────────────────────────────────────────────────────
    # Deterministic modes (ocr, pixel diff) are cheap and may bypass the model
    # cache; only cache when a model call is involved.
    cache = get_cache() if plan.usable else None
    key = cache_key(asset_id=asset_id, settings=plan.settings, input=input, backend=plan.kind) if cache else ""
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            telemetry.emit(tel.EVENT_CACHE_HIT, {"key": key[:24], "mode": input.mode})
            result = _result_from_cache(cached)
            result.cached = True
            result.latency_ms = 0
            return result
        telemetry.emit(tel.EVENT_CACHE_MISS, {"key": key[:24], "mode": input.mode})

    # ── dispatch with fallback ────────────────────────────────────────────────
    try:
        result = await _dispatch(processed, input, plan, ctx, telemetry, asset_id=asset_id, doc_page=doc_page)
    except VisionError as exc:
        telemetry.emit(tel.EVENT_ERROR, {"stage": "dispatch", **exc.to_dict()})
        return VisionResult.failure(exc, mode=input.mode)

    if result.ok:
        record_vision_success(_model_info_for(plan, ctx))
        if cache is not None:
            _maybe_cache(cache, key, result)
    else:
        record_vision_failure(_model_info_for(plan, ctx))

    _record_evidence(ctx, result)
    return result


# ── dispatch ──────────────────────────────────────────────────────────────────

async def _resolve(input: VisionInput, cfg: VisionConfig) -> tuple[DecodedImage, Any]:
    """Resolve a source into an image, rendering a document page when needed.

    A PDF (path/URL/bytes) is opened, its requested page rendered to an image,
    and its text layer extracted — so `mode=document` and any other mode work on
    a real page rather than failing with "not an image".
    """
    from .documents import extract_page_text, is_pdf_source, render_page

    if is_pdf_source(input):
        page_index = int(input.options.get("page", 0))
        pdf_source = _pdf_source_bytes(input)
        page = extract_page_text(pdf_source, page_index=page_index)
        decoded = render_page(pdf_source, page_index=page_index, cfg=cfg)
        return decoded, page
    return await resolve_source(input, cfg=cfg), None


def _pdf_source_bytes(input: VisionInput) -> Any:
    """Return a path or bytes suitable for pypdfium2 for a PDF input."""
    import base64 as _b64  # noqa: PLC0415

    source = input.source
    if input.source_kind == "base64":
        text = str(source)
        if text.startswith("data:"):
            _, _, text = text.partition(",")
        return _b64.b64decode(text, validate=False)
    if input.source_kind == "url":
        raise VisionError(
            VisionErrorClass.SECURITY_BLOCKED,
            "remote PDFs must be fetched through the URL guard (use source_kind=path or fetch first)",
            source_ref=str(source),
        )
    return source


async def _dispatch(
    decoded: DecodedImage,
    input: VisionInput,
    plan: RoutingPlan,
    ctx: VisionContext,
    telemetry: tel.VisionTelemetry,
    *,
    asset_id: str,
    doc_page: Any = None,
) -> VisionResult:
    mode = input.mode
    if mode == "ocr":
        return _do_ocr(decoded, input, telemetry, asset_id=asset_id)
    if mode in ("ground",):
        return await _try_candidates(
            plan, telemetry,
            lambda settings: _do_ground(decoded, input, plan, settings, telemetry, asset_id=asset_id),
        )
    if mode == "chart":
        return await _try_candidates(
            plan, telemetry,
            lambda settings: _do_chart(decoded, input, plan, settings, ctx, telemetry, asset_id=asset_id),
        )
    if mode == "document":
        return await _try_candidates(
            plan, telemetry,
            lambda settings: _do_document(decoded, input, plan, settings, telemetry, asset_id=asset_id, page=doc_page),
        )
    if mode == "compare":
        return await _try_candidates(
            plan, telemetry,
            lambda settings: _do_compare(decoded, input, plan, settings, ctx, telemetry, asset_id=asset_id),
        )
    # analyze / describe / visual QA
    return await _try_candidates(
        plan, telemetry,
        lambda settings: _do_analyze(decoded, input, plan, settings, telemetry, asset_id=asset_id),
    )


async def _try_candidates(plan: RoutingPlan, telemetry: tel.VisionTelemetry, factory: Any) -> VisionResult:
    """Try the plan's primary settings, then each permitted fallback candidate."""
    attempts = [plan.settings] + [c.settings for c in plan.candidates]
    last_error: Optional[VisionError] = None
    for index, settings in enumerate(attempts):
        try:
            result = await factory(settings)
            if index > 0:
                result.provenance = {**result.provenance, "fallback": True, "fallbackAttempt": index}
                telemetry.emit(tel.EVENT_PROVIDER_CALL, {
                    "fallback": True, "attempt": index, "provider": getattr(settings, "provider", None),
                    "model": getattr(settings, "model", None), "ok": result.ok,
                })
            return result
        except VisionError as exc:
            last_error = exc
            telemetry.emit(tel.EVENT_PROVIDER_CALL, {
                "fallback": index > 0, "attempt": index, "provider": getattr(settings, "provider", None),
                "model": getattr(settings, "model", None), "ok": False, "errorClass": exc.error_class.value,
            })
            if not exc.fallbackable:
                break
        except Exception as exc:  # noqa: BLE001 - an unexpected bug must not crash the tool
            last_error = VisionError(VisionErrorClass.INTERNAL_ERROR, f"vision dispatch failed: {exc}", cause=exc)
            telemetry.emit(tel.EVENT_PROVIDER_CALL, {
                "fallback": index > 0, "attempt": index, "ok": False, "errorClass": last_error.error_class.value,
            })
            if not last_error.fallbackable:
                break
    if last_error is None:
        last_error = VisionError(VisionErrorClass.NO_VISION_MODEL, "no vision candidate produced a result")
    telemetry.emit(tel.EVENT_ERROR, {"stage": "provider", **last_error.to_dict()})
    return VisionResult.failure(last_error, mode=plan.kind)


async def _do_analyze(
    decoded: DecodedImage, input: VisionInput, plan: RoutingPlan, settings: Any,
    telemetry: tel.VisionTelemetry, *, asset_id: str,
) -> VisionResult:
    from dataclasses import replace

    outcome, result = await analyze_image(decoded, input, replace(plan, settings=settings))
    telemetry.emit(tel.EVENT_PROVIDER_CALL, {
        "provider": result.provider, "model": result.model, "backend": result.backend,
        "latencyMs": result.latency_ms, **tel.usage_fields(result.usage),
    })
    return build_result(outcome, result, mode=input.mode, asset_id=asset_id,
                        provenance={"source": input.source_kind, "question": input.question})


def _do_ocr(
    decoded: DecodedImage, input: VisionInput, telemetry: tel.VisionTelemetry, *, asset_id: str,
) -> VisionResult:
    run = run_ocr(decoded)
    from .security import wrap_untrusted

    scan = scan_text(run.text)
    telemetry.emit(tel.EVENT_OCR, {
        "engine": run.engine, "confidence": run.confidence, "spans": len(run.spans),
        "sensitive": scan.sensitive,
    })
    observations = [
        VisualObservation(text=span.text, region=span.region, confidence=span.confidence, method="ocr")
        for span in run.spans[:2000]
    ]
    return VisionResult(
        ok=True, mode="ocr", description=wrap_untrusted(run.text, source="image") if scan.injection_signals else run.text,
        text=run.spans, objects=observations, confidence=run.confidence,
        backend=f"ocr:{run.engine}", provider=None, model=None,
        provenance={"ocr": run.to_dict(), "security": scan.to_dict()}, asset_id=asset_id,
    )


async def _do_ground(
    decoded: DecodedImage, input: VisionInput, plan: RoutingPlan, settings: Any,
    telemetry: tel.VisionTelemetry, *, asset_id: str,
) -> VisionResult:
    from dataclasses import replace

    outcome = await ground_image(decoded, input.question, replace(plan, settings=settings))
    telemetry.emit(tel.EVENT_GROUNDING, {
        "method": outcome.method, "found": outcome.found, "count": len(outcome.elements),
        "confidence": outcome.confidence,
    })
    observations = [
        VisualObservation(text=e.label, kind="observed", region=e.region, confidence=e.confidence,
                          method=e.method, source=e.source, details={"role": e.role})
        for e in outcome.elements
    ]
    return VisionResult(
        ok=True, mode="ground", description=outcome.method,
        observations=observations, regions=observations, objects=observations,
        confidence=outcome.confidence, backend=outcome.method,
        provider=getattr(settings, "provider", None), model=getattr(settings, "model", None),
        provenance={"grounding": outcome.to_dict(), "target": input.question}, asset_id=asset_id,
    )


async def _do_chart(
    decoded: DecodedImage, input: VisionInput, plan: RoutingPlan, settings: Any, ctx: VisionContext,
    telemetry: tel.VisionTelemetry, *, asset_id: str,
) -> VisionResult:
    from dataclasses import replace

    symbol = input.options.get("symbol")
    market = input.options.get("market")
    outcome, result = await analyze_chart(
        decoded, input, replace(plan, settings=settings), bridge=ctx.bridge, symbol=symbol, market=market,
    )
    telemetry.emit(tel.EVENT_CHART, {
        "chartType": outcome.chart_type, "trend": outcome.trend, "patterns": len(outcome.patterns),
        "confidence": outcome.confidence, "verified": bool(outcome.verification and outcome.verification.get("available")),
    })
    return build_chart_result(outcome, result, asset_id=asset_id, provenance={"source": input.source_kind})


async def _do_document(
    decoded: DecodedImage, input: VisionInput, plan: RoutingPlan, settings: Any,
    telemetry: tel.VisionTelemetry, *, asset_id: str, page: Any = None,
) -> VisionResult:
    from dataclasses import replace

    if page is None:
        source = input.source
        if input.source_kind == "path" and isinstance(source, str) and source.lower().endswith(".pdf") and pdf_available():
            try:
                page = extract_page_text(source, page_index=int(input.options.get("page", 0)))
            except VisionError:
                page = None
    outcome, result = await analyze_document_page(
        decoded, input, replace(plan, settings=settings), page=page,
        want_tables=bool(input.options.get("tables", True)),
    )
    telemetry.emit(tel.EVENT_DOCUMENT, {
        "page": outcome.page.index, "hasTextLayer": outcome.page.has_text_layer,
        "tables": len(outcome.tables), "financials": len(outcome.financials),
        "confidence": outcome.confidence,
    })
    return build_document_result(outcome, result, asset_id=asset_id, provenance={"source": input.source_kind})


async def _do_compare(
    decoded: DecodedImage, input: VisionInput, plan: RoutingPlan, settings: Any, ctx: VisionContext,
    telemetry: tel.VisionTelemetry, *, asset_id: str,
) -> VisionResult:
    from dataclasses import replace

    other_ref = input.options.get("compare_with")
    if not other_ref:
        raise VisionError(VisionErrorClass.INVALID_INPUT, "compare mode requires options.compare_with (a second image source)")
    other_input = VisionInput(source=str(other_ref), source_kind=input.options.get("compare_kind", input.source_kind))
    other = await resolve_source(other_input)
    other = preprocess(other)
    outcome, result = await compare_images(
        decoded, other, input, replace(plan, settings=settings),
        use_model=bool(input.options.get("use_model", True)),
        threshold=float(input.options.get("diff_threshold", 0.02)),
    )
    telemetry.emit(tel.EVENT_COMPARE, {
        "changed": outcome.changed, "ratio": outcome.changed_pixels_ratio,
        "regions": len(outcome.regions),
    })
    return build_compare_result(outcome, result, asset_id=asset_id, provenance={"source": input.source_kind})


# ── helpers ───────────────────────────────────────────────────────────────────

def _store_asset(
    store: VisionAssetStore, decoded: DecodedImage, input: VisionInput, ctx: VisionContext,
    cfg: VisionConfig, telemetry: tel.VisionTelemetry,
) -> str:
    persist = input.options.get("persist", True)
    if not persist:
        return decoded.asset_id
    expires_at = None
    # Any frame the pre-flight scan (or the caller) flagged sensitive is retained
    # for a bounded time — a secret must not outlive its purpose just because the
    # source was a file rather than a screenshot.
    if input.sensitive:
        import time  # noqa: PLC0415

        expires_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + _SENSITIVE_TTL_SECONDS))
    try:
        asset = store.save(
            decoded, run_id=ctx.run_id, session_id=ctx.session_id,
            source_kind=input.source_kind, source_ref=str(input.source)[:500], expires_at=expires_at,
            owner=ctx.user_id or "local",
        )
        return asset.asset_id
    except VisionError as exc:
        telemetry.emit(tel.EVENT_ERROR, {"stage": "storage", **exc.to_dict()})
        return decoded.asset_id


def _record_evidence(ctx: VisionContext, result: VisionResult) -> None:
    if ctx.evidence_sink is None or not result.ok:
        return
    try:
        ctx.evidence_sink(result)
    except Exception:  # noqa: BLE001 - evidence recording must never break a call
        pass


def _model_info_for(plan: RoutingPlan, ctx: VisionContext) -> Any:
    if ctx.runtime is None or plan.settings is None:
        return None
    try:
        resolution = ctx.runtime.resolve_for_run(plan.settings, task="vision")
        return resolution.model
    except Exception:  # noqa: BLE001
        return None


def _maybe_cache(cache: Any, key: str, result: VisionResult) -> None:
    if not result.ok:
        return
    try:
        cache.put(key, result.to_dict())
    except Exception:  # noqa: BLE001
        pass


def _result_from_cache(payload: dict[str, Any]) -> VisionResult:
    """Rehydrate a VisionResult from a cached dict (best-effort, honest)."""
    from .contracts import OCRSpan

    def _region(value: Any) -> Optional[Region]:
        return Region.from_any(value) if value else None

    observations = [
        VisualObservation(
            text=o.get("text", ""), kind=o.get("kind", "observed"),
            region=_region((o.get("region") or {}) if isinstance(o, dict) else None),
            confidence=o.get("confidence", 0.0), method=o.get("method", "model"),
            source=o.get("source"), details=o.get("details") or {},
        )
        for o in payload.get("observations", [])
        if isinstance(o, dict)
    ]
    text = [
        OCRSpan(text=t.get("text", ""), region=Region.from_any(t.get("bounds") or t.get("bbox")) or Region(),
                confidence=t.get("confidence", 0.0))
        for t in payload.get("text", [])
        if isinstance(t, dict)
    ]
    usage = payload.get("usage") or {}
    return VisionResult(
        ok=payload.get("ok", True), mode=payload.get("mode", "analyze"),
        description=payload.get("description", ""), observations=observations, text=text,
        objects=observations, tables=payload.get("tables", []), chart=payload.get("chart"),
        comparison=payload.get("comparison"), structured=payload.get("structured"),
        confidence=payload.get("confidence", 0.0), provider=payload.get("provider"),
        model=payload.get("model"), backend=payload.get("backend", "cache"),
        usage=VisionUsage(
            input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        ),
        provenance=payload.get("provenance", {}), warnings=payload.get("warnings", []),
        asset_id=payload.get("asset_id"),
    )


def build_asset_store(store: Any, *, cfg: Optional[VisionConfig] = None) -> VisionAssetStore:
    """Construct the asset store bound to the harness memory store."""
    return VisionAssetStore(store, cfg=cfg)


__all__ = [
    "VisionContext", "orchestrate", "build_asset_store", "_result_from_cache",
]
