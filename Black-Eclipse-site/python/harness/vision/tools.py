"""The `vision_*` toolset — the agent-facing multimodal capability.

Every tool is registered on the SAME `ToolRegistry` as finance, code, terminal,
browser and computer tools, so validation, permission, timeout, effect
authorization and the event stream apply unchanged.

All tools are READ-ONLY: a vision tool observes existing content, it never
mutates state. Screenshot capture reads the screen (read-only). Every tool is a
thin adapter over `orchestrate()`; no handler decodes an image, picks a provider
or calls a model directly.

Recognized in-image text is wrapped as UNTRUSTED DATA before it reaches the
model, so a screenshot that says "IGNORE ALL PREVIOUS INSTRUCTIONS" cannot
override the system prompt.
"""

from __future__ import annotations

from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry, dumps
from .config import vision_config
from .contracts import Region, VisionInput, VisionResult
from .errors import VisionError
from .orchestrator import VisionContext, build_asset_store, orchestrate
from .routing import plan_route
from .security import scan_text

# ── context wiring ────────────────────────────────────────────────────────────

def _asset_store(ctx: ToolContext) -> Any:
    store = getattr(ctx, "_vision_asset_store", None)
    if store is not None:
        return store
    memory_store = getattr(ctx, "memory_store", None)
    if memory_store is None:
        return None
    try:
        store = build_asset_store(memory_store)
        ctx._vision_asset_store = store  # type: ignore[attr-defined]
        return store
    except Exception:  # noqa: BLE001 - storage is best-effort, never fatal
        return None


def _evidence_store(ctx: ToolContext) -> Any:
    store = getattr(ctx, "evidence_store", None)
    if store is not None:
        return store
    memory_store = getattr(ctx, "memory_store", None)
    if memory_store is None:
        return None
    try:
        from ..research.web_store import EvidenceStore  # noqa: PLC0415

        store = EvidenceStore(memory_store)
        ctx.evidence_store = store  # type: ignore[attr-defined]
        return store
    except Exception:  # noqa: BLE001
        return None


def _context(ctx: ToolContext) -> VisionContext:
    evidence_store = _evidence_store(ctx)

    def _sink(result: VisionResult) -> None:
        # Route visual observations into the Evidence Engine and the run's
        # source collector (the same Sources surface web research uses).
        try:
            from .evidence import record_result_evidence  # noqa: PLC0415

            ids = record_result_evidence(evidence_store, result)
            sink = getattr(ctx, "source_sink", None)
            if sink is not None and ids:
                sink.add_web_source(
                    url=f"image://{result.asset_id or 'unknown'}",
                    title=f"Vision ({result.mode})",
                    source_type="image", tier="unknown",
                    retrieved_at=result.provenance.get("retrievedAt"),
                    ok=True, evidence_id=ids[0],
                )
        except Exception:  # noqa: BLE001
            pass

    return VisionContext(
        run_settings=getattr(ctx, "model_settings", None),
        emitter=getattr(ctx, "emitter", None),
        bridge=getattr(ctx, "data_bridge", None),
        asset_store=_asset_store(ctx),
        run_id=getattr(ctx, "run_id", None),
        user_id=getattr(ctx, "user_id", None),
        evidence_sink=_sink,
    )


def infer_kind(source: str, declared: Optional[str]) -> str:
    if declared:
        return declared
    text = (source or "").strip()
    lowered = text.lower()
    if lowered.startswith("data:"):
        return "base64"
    if lowered.startswith(("http://", "https://")):
        return "url"
    # A long, separator-free token that decodes to a known image is in-memory
    # image bytes. A real path is unlikely to base64-decode to image magic.
    if len(text) >= 64 and " " not in text and "\n" not in text and _decodes_to_image(text):
        return "base64"
    return "path"


def _decodes_to_image(text: str) -> bool:
    import base64 as _b64  # noqa: PLC0415

    from .image import sniff_mime  # noqa: PLC0415

    try:
        # A path never decodes to image magic; base64 image data does.
        data = _b64.b64decode(text[:64] + "==", validate=True)
    except Exception:  # noqa: BLE001
        try:
            data = _b64.b64decode(text[:64] + "==", validate=False)
        except Exception:  # noqa: BLE001
            return False
    return sniff_mime(data) is not None


def _region(value: Any) -> Optional[Region]:
    return Region.from_any(value) if value else None


def _build_input(args: dict[str, Any], *, default_mode: str, default_kind: Optional[str] = None) -> VisionInput:
    source = str(args.get("source") or "").strip()
    kind = infer_kind(source, args.get("source_kind") or default_kind)
    options: dict[str, Any] = {}
    for key in ("language", "tiling", "max_tiles", "preprocess", "max_dimension", "quality",
                "schema_version", "compare_with", "compare_kind", "use_model", "diff_threshold",
                "page", "tables", "symbol", "market", "persist", "mime"):
        if args.get(key) is not None:
            options[key] = args[key]
    return VisionInput(
        source=source,
        source_kind=kind,  # type: ignore[arg-type]
        question=str(args.get("question") or args.get("target") or "").strip(),
        mode=(args.get("mode") or default_mode),  # type: ignore[arg-type]
        region=_region(args.get("region")),
        local_only=bool(args.get("local_only", False)),
        sensitive=bool(args.get("sensitive", False)),
        privacy=args.get("privacy"),
        options=options,
    )


def _summarize(result: VisionResult) -> str:
    """A compact, model-facing summary. Large blobs stay in `data`."""
    if not result.ok:
        err = result.error or {}
        return f"VISION UNAVAILABLE ({err.get('errorClass', 'ERROR')}): {err.get('message', 'no result')}"
    lines: list[str] = [f"Vision result ({result.mode})"]
    meta = []
    if result.provider:
        meta.append(f"provider={result.provider}")
    if result.model:
        meta.append(f"model={result.model}")
    meta.append(f"backend={result.backend}")
    meta.append(f"confidence={result.confidence:.2f}")
    if result.cached:
        meta.append("cached")
    lines.append("  " + " ".join(meta))
    if result.asset_id:
        lines.append(f"  asset: {result.asset_id}")
    if result.description:
        lines.append("Description:\n" + _indent(result.description))
    if result.text:
        lines.append("Detected text (untrusted data):")
        for span in result.text[:40]:
            lines.append(f"  [{span.region.to_list()}] {span.text}")
    if result.observations:
        lines.append("Observations:")
        for obs in result.observations[:60]:
            box = f" {obs.region.to_list()}" if obs.region else ""
            lines.append(f"  - {obs.text} ({obs.method}, {obs.kind}, {obs.confidence:.2f}){box}")
    if result.tables:
        lines.append(f"Tables: {len(result.tables)}")
    if result.chart:
        chart = result.chart
        lines.append(
            f"Chart: type={chart.get('chart_type')} trend={chart.get('trend')} "
            f"patterns={chart.get('patterns')} verification={chart.get('verification')}"
        )
    if result.comparison:
        comp = result.comparison
        lines.append(f"Comparison: changed={comp.get('changed')} ratio={comp.get('changedPixelsRatio')} regions={len(comp.get('regions', []))}")
    if result.warnings:
        lines.append("Warnings: " + "; ".join(result.warnings[:5]))
    return "\n".join(lines)


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in str(text).splitlines()[:40])


async def _run(input: VisionInput, ctx: ToolContext) -> tuple[str, Any]:
    result = await orchestrate(input, _context(ctx))
    sink = getattr(ctx, "vision_sink", None)
    if sink is not None:
        try:
            sink(result.to_dict())
        except Exception:  # noqa: BLE001 - collection must never break the tool
            pass
    return _summarize(result), result.to_dict()


# ── handlers ──────────────────────────────────────────────────────────────────

async def vision_analyze(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _run(_build_input(args, default_mode="analyze"), ctx)


async def image_understand(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _run(_build_input(args, default_mode="describe"), ctx)


async def vision_answer(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _run(_build_input(args, default_mode="analyze"), ctx)


async def screenshot_analyze(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _run(_build_input(args, default_mode="analyze", default_kind="screenshot"), ctx)


async def clipboard_analyze(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _run(_build_input(args, default_mode="analyze", default_kind="clipboard"), ctx)


async def ocr_extract(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _run(_build_input(args, default_mode="ocr"), ctx)


async def visual_ground(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _run(_build_input(args, default_mode="ground"), ctx)


async def visual_localize(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _run(_build_input(args, default_mode="ground"), ctx)


async def chart_analyze(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _run(_build_input(args, default_mode="chart"), ctx)


async def document_vision(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _run(_build_input(args, default_mode="document"), ctx)


async def visual_compare(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not args.get("compare_with"):
        return ("compare_with (a second image source) is required.", {"status": "ERROR", "error": "compare_with required"})
    return await _run(_build_input(args, default_mode="compare"), ctx)


async def image_diff(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    args = {**args, "use_model": False}
    return await _run(_build_input(args, default_mode="compare"), ctx)


async def screen_compare(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    input = _build_input(args, default_mode="compare", default_kind="screenshot")
    return await _run(input, ctx)


async def image_metadata(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Deterministic metadata only — no model, no analysis."""
    from .image import read_file, decode_base64
    from .load import resolve_source  # noqa: F401

    source = str(args.get("source") or "").strip()
    kind = infer_kind(source, args.get("source_kind"))
    try:
        if kind == "base64":
            decoded = decode_base64(source)
        elif kind == "path":
            decoded = read_file(source)
        elif kind == "url":
            from .fetch import fetch_url  # noqa: PLC0415

            decoded = await fetch_url(source)
        else:
            decoded = await resolve_source(VisionInput(source=source, source_kind=kind))  # type: ignore[arg-type]
    except VisionError as exc:
        return (f"IMAGE UNAVAILABLE ({exc.error_class.value}): {exc.message}", exc.to_dict())
    data = {
        "type": "image_metadata",
        "ok": True,
        "asset_id": decoded.asset_id,
        "sha256": decoded.sha256,
        "mimeType": decoded.mime_type,
        "width": decoded.width,
        "height": decoded.height,
        "byteSize": decoded.byte_size,
        "metadata": decoded.metadata,
    }
    return (
        f"Image {decoded.width}x{decoded.height} {decoded.mime_type} ({decoded.byte_size} bytes), sha256={decoded.sha256[:16]}…",
        data,
    )


async def vision_capabilities(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Report what vision can actually do right now (honest, no model call)."""
    from .ocr import ocr_available
    from .capabilities import capabilities_for_settings
    from .documents import pdf_capabilities

    cfg = vision_config()
    run_caps = capabilities_for_settings(getattr(ctx, "model_settings", None), task="vision")
    plan = plan_route(VisionInput(source="", source_kind="path"), run_settings=getattr(ctx, "model_settings", None))
    gen_caps = capabilities_for_settings(getattr(ctx, "model_settings", None), task="image_generation")
    data = {
        "type": "vision_capabilities",
        "enabled": cfg.enabled,
        "nativeVision": run_caps.native_vision,
        "runModel": run_caps.to_dict(),
        "route": plan.to_dict(),
        "ocrAvailable": ocr_available(cfg),
        "ocrBackend": cfg.ocr_backend,
        "pdf": pdf_capabilities(),
        "imageGeneration": gen_caps.vision.value if hasattr(gen_caps, "vision") else None,
        "imageGenerationSupported": bool(getattr(gen_caps, "vision", None) and gen_caps.vision.value == "supported"),
        "privacyMode": cfg.privacy_mode,
        "limits": {
            "maxImageBytes": cfg.max_image_bytes, "maxPixels": cfg.max_pixels,
            "maxDimension": cfg.max_dimension, "maxTiles": cfg.max_tiles,
        },
    }
    text = (
        f"Vision enabled={cfg.enabled}, native model vision={run_caps.native_vision}, "
        f"route={plan.kind} ({plan.reason}); OCR={data['ocrAvailable']}, "
        f"PDF raster={data['pdf'].get('rasterization')}, image generation={data['imageGenerationSupported']}."
    )
    return text, data


async def vision_asset_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    store = _asset_store(ctx)
    if store is None:
        return ("No vision asset store is available.", {"status": "unavailable"})
    run_id = str(args.get("run_id") or getattr(ctx, "run_id", "") or "")
    assets = store.list_for_run(run_id) if run_id else []
    data = {"type": "vision_assets", "count": len(assets), "assets": [a.to_dict() for a in assets]}
    return f"{len(assets)} vision asset(s) recorded for this run.", data


async def image_generate(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Generate an image from a text prompt (external, paid — approval-gated)."""
    from .generate import generate_image

    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        return ("A prompt is required.", {"status": "ERROR", "error": "prompt required"})
    try:
        generated = await generate_image(
            getattr(ctx, "model_settings", None), prompt,
            size=str(args.get("size") or "1024x1024"),
            model=args.get("model"),
        )
    except VisionError as exc:
        return (f"IMAGE GENERATION UNAVAILABLE ({exc.error_class.value}): {exc.message}", exc.to_dict())

    asset_id = generated.decoded.asset_id
    store = _asset_store(ctx)
    if store is not None:
        try:
            asset = store.save(generated.decoded, run_id=getattr(ctx, "run_id", None),
                               source_kind="generated", source_ref=prompt[:200])
            asset_id = asset.asset_id
        except VisionError:
            pass
    data = {"ok": True, "mode": "generate", **generated.to_dict(), "assetId": asset_id}
    sink = getattr(ctx, "vision_sink", None)
    if sink is not None:
        try:
            sink(data)
        except Exception:  # noqa: BLE001
            pass
    return (f"Generated a {generated.decoded.width}x{generated.decoded.height} image (asset {asset_id}).", data)


async def vision_remember(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Persist a useful visual observation to durable memory (via the gate)."""
    from .memory import remember_visual
    from .contracts import VisionResult

    payload = args.get("result")
    if not isinstance(payload, dict):
        return ("A vision result is required.", {"status": "ERROR", "error": "result required"})
    try:
        result = _result_from_dict(payload)
    except Exception as exc:  # noqa: BLE001
        return (f"Could not read the vision result: {exc}", {"status": "ERROR", "error": str(exc)})
    try:
        outcome = remember_visual(
            result, ctx, subject=args.get("subject"),
            content=args.get("content"), scope=str(args.get("scope") or "general"),
            confidence=float(args.get("confidence", 0.7) or 0.7),
        )
    except VisionError as exc:
        return (f"MEMORY NOT SAVED — {exc.message}", {"saved": False, "error": exc.to_dict()})
    if outcome.get("saved"):
        return (f"Visual observation remembered (id={outcome.get('id')}, asset {outcome.get('assetId')}).", outcome)
    if outcome.get("action") == "suggest":
        return (
            "MEMORY NOT SAVED — recorded as a suggestion; the user must confirm. Do not claim it was remembered.",
            outcome,
        )
    return (f"MEMORY NOT SAVED — {outcome.get('reason') or outcome.get('action')}", outcome)


def _result_from_dict(payload: dict[str, Any]) -> Any:
    """Rehydrate a minimal VisionResult from the dict a prior tool returned."""
    from .contracts import OCRSpan, Region, VisionResult, VisionUsage, VisualObservation

    def _region(value: Any) -> Optional[Region]:
        return Region.from_any(value) if value else None

    observations = [
        VisualObservation(
            text=str(o.get("text", "")), kind=o.get("kind", "observed"),
            region=_region(o.get("region")), confidence=float(o.get("confidence", 0.0) or 0.0),
            method=o.get("method", "model"),
        )
        for o in (payload.get("observations") or []) if isinstance(o, dict)
    ]
    text = [
        OCRSpan(text=str(t.get("text", "")), region=_region(t.get("bounds")) or Region(),
                confidence=float(t.get("confidence", 0.0) or 0.0))
        for t in (payload.get("text") or []) if isinstance(t, dict)
    ]
    usage = payload.get("usage") or {}
    return VisionResult(
        ok=bool(payload.get("ok", True)), mode=payload.get("mode", "analyze"),
        description=payload.get("description", ""), observations=observations,
        objects=observations, text=text, tables=payload.get("tables") or [],
        chart=payload.get("chart"), comparison=payload.get("comparison"),
        confidence=float(payload.get("confidence", 0.0) or 0.0),
        provider=payload.get("provider"), model=payload.get("model"),
        asset_id=payload.get("asset_id"), provenance=payload.get("provenance") or {},
        usage=VisionUsage(
            input_tokens=usage.get("input_tokens", 0) or 0,
            output_tokens=usage.get("output_tokens", 0) or 0,
            total_tokens=usage.get("total_tokens", 0) or 0,
        ),
    )


# ── schemas ────────────────────────────────────────────────────────────────────

_STR = {"type": "string"}
_INT = {"type": "integer"}
_NUM = {"type": "number"}
_BOOL = {"type": "boolean"}
_REGION = {
    "type": "array", "items": {"type": "integer"},
    "description": "Region of interest [x, y, width, height] in image pixels.",
}


def _obj(props: dict[str, Any], required: Optional[list[str]] = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


_SOURCE = {**_STR, "description": "Image source: a local path, an http(s) URL, or a data URI."}
_SCHEMAS: dict[str, dict[str, Any]] = {
    "vision_analyze": _obj({
        "source": _SOURCE, "source_kind": {**_STR, "enum": ["path", "url", "base64", "screenshot", "clipboard"]},
        "question": _STR, "mode": {**_STR, "enum": ["analyze", "describe"]},
        "region": _REGION, "local_only": _BOOL, "sensitive": _BOOL, "persist": _BOOL,
    }, ["source"]),
    "image_understand": _obj({"source": _SOURCE, "source_kind": _STR, "question": _STR, "region": _REGION}, ["source"]),
    "vision_answer": _obj({"source": _SOURCE, "question": _STR, "source_kind": _STR}, ["source", "question"]),
    "screenshot_analyze": _obj({"question": _STR, "region": _REGION, "mode": _STR, "local_only": _BOOL}, []),
    "clipboard_analyze": _obj({"question": _STR, "region": _REGION, "mode": _STR}, []),
    "ocr_extract": _obj({"source": _SOURCE, "source_kind": _STR, "region": _REGION, "language": _STR}, ["source"]),
    "visual_ground": _obj({"source": _SOURCE, "target": _STR, "source_kind": _STR, "region": _REGION}, ["source", "target"]),
    "visual_localize": _obj({"source": _SOURCE, "target": _STR, "source_kind": _STR, "region": _REGION}, ["source", "target"]),
    "chart_analyze": _obj({
        "source": _SOURCE, "source_kind": _STR, "question": _STR,
        "symbol": {**_STR, "description": "Instrument symbol to verify against deterministic market data."},
        "market": _STR,
    }, ["source"]),
    "document_vision": _obj({
        "source": _SOURCE, "source_kind": _STR, "question": _STR,
        "page": {**_INT, "description": "Zero-based page index for a PDF."},
        "tables": _BOOL,
    }, ["source"]),
    "visual_compare": _obj({
        "source": _SOURCE, "compare_with": {**_STR, "description": "Second image source to compare against."},
        "compare_kind": _STR, "question": _STR, "diff_threshold": _NUM,
    }, ["source", "compare_with"]),
    "image_diff": _obj({"source": _SOURCE, "compare_with": _STR, "diff_threshold": _NUM}, ["source", "compare_with"]),
    "screen_compare": _obj({
        "source": _SOURCE, "compare_with": _STR, "question": _STR,
    }, ["source", "compare_with"]),
    "image_metadata": _obj({"source": _SOURCE, "source_kind": _STR}, ["source"]),
    "vision_capabilities": _obj({}),
    "vision_asset_list": _obj({"run_id": _STR}),
    "image_generate": _obj({
        "prompt": {**_STR, "description": "A description of the image to generate."},
        "size": {**_STR, "description": "Image size, e.g. 1024x1024."},
        "model": {**_STR, "description": "An image-generation model id, when the endpoint needs one."},
    }, ["prompt"]),
    "vision_remember": _obj({
        "result": {"type": "object", "description": "The vision result object to remember."},
        "subject": _STR, "content": _STR,
        "scope": {**_STR, "enum": ["user", "general", "market", "task"]},
        "confidence": _NUM,
    }, ["result"]),
}

_TOOLS: list[tuple[str, str, Any, int]] = [
    ("vision_analyze", "Analyze an image (path/URL/data-URI/screenshot/clipboard) and answer a question about what is visible. Native-first: the run's own multimodal model is used when it can see images, else an auxiliary vision model.", vision_analyze, 60_000),
    ("image_understand", "Describe an image in detail: subject, layout, text, and notable elements.", image_understand, 60_000),
    ("vision_answer", "Answer a specific question about an image (visual question answering).", vision_answer, 60_000),
    ("screenshot_analyze", "Capture the current screen and analyze it. Optionally restrict to a region [x,y,w,h].", screenshot_analyze, 60_000),
    ("clipboard_analyze", "Analyze the image currently on the OS clipboard.", clipboard_analyze, 60_000),
    ("ocr_extract", "Extract text and per-word bounding boxes from an image using a deterministic OCR engine (no model). Returns text, confidence and coordinates.", ocr_extract, 60_000),
    ("visual_ground", "Locate a described element (e.g. 'the Continue button') in an image and return its bounding box, centre and confidence. Used by computer-use targeting.", visual_ground, 90_000),
    ("visual_localize", "Alias of visual_ground: return the coordinates of a named element in an image.", visual_localize, 90_000),
    ("chart_analyze", "Interpret a chart's visual structure (type, trend, patterns, drawn zones). When a symbol is given, the visual trend is verified against deterministic market data.", chart_analyze, 90_000),
    ("document_vision", "Understand a document page (PDF/image): text layer, OCR, tables and figures. Deterministic extraction first, vision for interpretation.", document_vision, 120_000),
    ("visual_compare", "Compare two images (before/after, UI regression, revisions). Returns changed regions plus a description of what changed.", visual_compare, 90_000),
    ("image_diff", "Deterministic pixel diff between two images — changed regions only, no model.", image_diff, 30_000),
    ("screen_compare", "Capture the screen and compare it against another image source.", screen_compare, 90_000),
    ("image_metadata", "Return image metadata (dimensions, MIME, sha256, EXIF summary) without analyzing it.", image_metadata, 20_000),
    ("vision_capabilities", "Report what the vision subsystem can do right now: native model vision, OCR/PDF availability, routing and limits.", vision_capabilities, 10_000),
    ("vision_asset_list", "List the image assets recorded for the current run.", vision_asset_list, 10_000),
    ("vision_remember", "Persist a useful visual observation to durable memory (via the memory decision gate; sensitive/ephemeral results get a TTL).", vision_remember, 10_000),
    ("image_generate", "Generate an image from a text prompt through an image-generation model. External and paid; requires approval and a model that declares image-generation support.", image_generate, 120_000),
]

#: Tools whose real-world effect is external (a paid provider call, a network
#: fetch). They are registered with `permission="external_action"` so the run's
#: effect authorizer gates them — the same single-use approval the rest of the
#: harness uses.
_EXTERNAL_TOOLS = frozenset({"image_generate"})


def register_vision_tools(registry: ToolRegistry) -> list[str]:
    """Register the vision toolset. Returns the names added."""
    added: list[str] = []
    for name, description, handler, timeout in _TOOLS:
        if registry.get(name) is not None:
            continue
        external = name in _EXTERNAL_TOOLS
        registry.register(ToolDefinition(
            name=name,
            description=description,
            input_schema=_SCHEMAS[name],
            handler=handler,
            permission="external_action" if external else "read",
            risk="medium" if external else "low",
            timeout_ms=timeout,
            output_schema=None,
            effect="external_action" if external else None,
        ))
        added.append(name)
    return added


__all__ = ["register_vision_tools"]
