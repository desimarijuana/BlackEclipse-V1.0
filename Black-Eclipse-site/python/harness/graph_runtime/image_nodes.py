"""Image nodes: read images through the ONE vision engine.

These nodes never render and never generate images. They wrap
`harness/vision/orchestrator.orchestrate` (analyze / OCR / chart / ground /
compare) and the content-addressed `VisionAssetStore`.

Honesty rules:

* A result is an OBSERVATION, not evidence: every output carries
  `kind: "observation"`, `verified: false` and the model/provider used.
* A failed or unsupported request fails the node with the engine's reason — it
  never returns a placeholder image or a fabricated reading.
* `image.read_chart` sets `verified: true` only when the engine's own market-data
  check confirmed the reading.
"""

from __future__ import annotations

import base64
import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)

ANALYZE_MODES = ("describe", "answer", "ground", "extract")
BATCH_MODES = ("analyze", "read_chart", "ocr")
COMPARE_MODES = ("pixel", "visual", "both")

MAX_IMAGES = 8
MAX_QUESTIONS = 5
MAX_OBSERVATIONS = 200
MAX_ASSET_JSON = 8_000


class VisionNotConfigured(RuntimeError):
    pass


VisionRunner = Callable[[NodeExecContext, dict[str, Any]], dict[str, Any]]
_store: Any = None
_runner: Optional[VisionRunner] = None


def set_vision_asset_store(store: Any) -> None:
    global _store
    _store = store


def get_vision_asset_store() -> Any:
    return _store


def set_vision_runner(runner: Optional[VisionRunner]) -> None:
    global _runner
    _runner = runner


def _require_store() -> Any:
    if _store is None:
        raise ValueError("the vision asset store is not configured in this graph runtime")
    return _store


def _image_ref(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("assetId", "asset_id", "id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return ""


def _resolve_ref(context: NodeExecContext, *, config_key: str = "assetId") -> str:
    ref = _image_ref(context.inputs.get("image")) or _image_ref(context.inputs.get("a"))
    if not ref:
        configured = context.config.get(config_key)
        ref = configured.strip() if isinstance(configured, str) else ""
    if not ref:
        raise ValueError("no image is attached: upload one in the inspector or wire an Image input")
    return ref


def _owner(context: NodeExecContext) -> str:
    return str(context.user_id or "local")[:120]


def _asset(ref: str, owner: str) -> Any:
    store = _require_store()
    asset = store.get(ref, owner=owner)
    if asset is None:
        raise ValueError(f"image {ref!r} does not exist (it may have been deleted)")
    return asset


def _image_object(asset: Any) -> dict[str, Any]:
    meta = getattr(asset, "metadata", None) or {}
    return {
        "assetId": asset.asset_id,
        "name": str(meta.get("name") or asset.source_ref or asset.asset_id),
        "mime": asset.mime_type,
        "width": asset.width,
        "height": asset.height,
        "bytes": asset.byte_size,
        "sha256": asset.sha256,
    }


def _region(value: Any) -> Optional[list[int]]:
    if value in (None, "", [], [0, 0, 0, 0]):
        return None
    parsed: Any = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text) if text.startswith("[") else [int(p) for p in text.split(",")]
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Region must be [x, y, width, height]") from exc
    if not isinstance(parsed, (list, tuple)) or len(parsed) != 4:
        raise ValueError("Region must be [x, y, width, height]")
    try:
        coords = [int(v) for v in parsed]
    except (TypeError, ValueError) as exc:
        raise ValueError("Region values must be whole numbers") from exc
    if coords[2] <= 0 or coords[3] <= 0:
        return None
    return coords


def _max_observations(context: NodeExecContext) -> int:
    try:
        value = int(context.config.get("maxObservations", 60))
    except (TypeError, ValueError) as exc:
        raise ValueError("Max observations must be a whole number") from exc
    return max(1, min(value, MAX_OBSERVATIONS))


def _run_vision(
    context: NodeExecContext,
    *,
    asset_id: str,
    mode: str,
    question: str = "",
    options: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if _runner is None:
        raise ValueError("the vision engine is not configured in this graph runtime")
    request = {
        "assetId": asset_id,
        "mode": mode,
        "question": question,
        "options": options or {},
        "region": _region(context.config.get("region")),
    }
    return _runner(context, request)


def _observation_meta(result: dict[str, Any], asset_id: str) -> dict[str, Any]:
    return {
        "kind": "observation",
        "verified": False,
        "assetId": asset_id,
        "mode": str(result.get("mode") or ""),
        "provider": result.get("provider"),
        "model": result.get("model"),
        "backend": result.get("backend"),
        "confidence": result.get("confidence"),
        "warnings": list(result.get("warnings") or []),
        "latencyMs": result.get("latency_ms"),
        "usage": result.get("usage") or {},
        "provenance": result.get("provenance") or {},
    }


def _observations(result: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    rows = result.get("observations") or []
    return [row for row in rows[:limit] if isinstance(row, dict)]


def _validate_schema(payload: Any, schema_json: str) -> tuple[Any, Optional[str]]:
    text = (schema_json or "").strip()
    if not text:
        return payload, None
    try:
        schema = json.loads(text)
    except json.JSONDecodeError as exc:
        return payload, f"output schema is not valid JSON: {exc}"
    if not isinstance(schema, dict):
        return payload, "output schema must be a JSON object"
    try:
        from ..vision.analyze import validate_json  # noqa: PLC0415

        valid, error = validate_json(payload if isinstance(payload, dict) else {"value": payload}, schema)
    except Exception as exc:  # noqa: BLE001 - validation is best-effort by contract
        return payload, f"output schema could not be checked: {exc}"
    return payload, None if valid else error


def _parse_extract(result: dict[str, Any]) -> Any:
    structured = result.get("structured")
    if isinstance(structured, dict) and structured:
        return structured
    text = str(result.get("description") or "").strip()
    if not text:
        return None
    try:
        from ..vision.analyze import extract_json  # noqa: PLC0415

        return extract_json(text)
    except Exception:  # noqa: BLE001 - honest null when no object could be read
        return None


def exec_image_attach(context: NodeExecContext) -> dict[str, Any]:
    ref = _resolve_ref(context)
    asset = _asset(ref, _owner(context))
    context.emit(f"image {asset.asset_id} · {asset.width}×{asset.height}")
    return {"image": _image_object(asset), "meta": _image_object(asset)}


def exec_image_analyze(context: NodeExecContext) -> dict[str, Any]:
    ref = _resolve_ref(context)
    _asset(ref, _owner(context))
    mode = str(context.config.get("mode") or "describe").strip().lower()
    if mode not in ANALYZE_MODES:
        raise ValueError(f"unknown image analyze mode {mode!r}")
    question = str(context.inputs.get("question") or context.config.get("question") or "").strip()
    if mode == "answer" and not question:
        raise ValueError("image.analyze needs a question in answer mode")
    schema_json = str(context.config.get("schemaJson") or "").strip()
    vision_mode = "ground" if mode == "ground" else "describe" if mode == "describe" else "analyze"
    prompt = question
    if mode == "extract" and schema_json:
        prompt = (
            "Return ONE JSON object that satisfies this JSON Schema. "
            "Do not wrap it in prose.\nSchema: " + schema_json[:4_000]
        ) + (f"\n\n{question}" if question else "")
    result = _run_vision(context, asset_id=ref, mode=vision_mode, question=prompt)
    meta = _observation_meta(result, ref)
    data: Any = None
    issues: Optional[str] = None
    if mode == "extract":
        data = _parse_extract(result)
        data, issues = _validate_schema(data, schema_json)
        if issues:
            data = None
            meta["schemaIssues"] = issues
    context.emit(
        f"{vision_mode} · {len(result.get('observations') or [])} observation(s)"
        + (" · schema mismatch" if issues else "")
    )
    return {
        "description": str(result.get("description") or ""),
        "observations": _observations(result, _max_observations(context)),
        "data": data,
        "meta": meta,
    }


def exec_image_ocr(context: NodeExecContext) -> dict[str, Any]:
    ref = _resolve_ref(context)
    _asset(ref, _owner(context))
    options: dict[str, Any] = {}
    language = str(context.config.get("language") or "").strip()
    if language:
        options["language"] = language
    result = _run_vision(context, asset_id=ref, mode="ocr", options=options)
    spans = result.get("text") or []
    text = str(result.get("description") or "")
    if not text and spans:
        text = "\n".join(str(span.get("text") or "") for span in spans[:2_000])
    context.emit(f"ocr · {len(spans)} span(s)")
    return {
        "text": text,
        "spans": spans[:2_000],
        "meta": _observation_meta(result, ref),
    }


def exec_image_read_chart(context: NodeExecContext) -> dict[str, Any]:
    ref = _resolve_ref(context)
    _asset(ref, _owner(context))
    question = str(context.inputs.get("question") or context.config.get("question") or "").strip()
    options: dict[str, Any] = {}
    for key in ("symbol", "market", "timeframe"):
        value = context.config.get(key)
        if isinstance(value, str) and value.strip():
            options[key] = value.strip()
    result = _run_vision(context, asset_id=ref, mode="chart", question=question, options=options)
    reading = result.get("chart")
    if not isinstance(reading, dict):
        reading = {}
    verification = reading.get("verification") if isinstance(reading.get("verification"), dict) else {}
    verified = bool(verification.get("available"))
    meta = _observation_meta(result, ref)
    meta["verified"] = verified
    meta["verification"] = verification
    context.emit("chart read" + (" · verified" if verified else " · unverified"))
    return {
        "reading": reading,
        "description": str(result.get("description") or ""),
        "verified": verified,
        "meta": meta,
    }


def exec_image_compare(context: NodeExecContext) -> dict[str, Any]:
    ref = _resolve_ref(context)
    owner = _owner(context)
    _asset(ref, owner)
    other_ref = _image_ref(context.inputs.get("b"))
    if not other_ref:
        configured = context.config.get("compareAssetId")
        other_ref = configured.strip() if isinstance(configured, str) else ""
    if not other_ref:
        raise ValueError("image.compare needs a second image (wire B or pick Compare image)")
    other = _asset(other_ref, owner)
    store = _require_store()
    other_bytes = store.open_bytes(other.asset_id, owner=owner)
    data_uri = f"data:{other.mime_type};base64,{base64.b64encode(other_bytes).decode('ascii')}"
    mode = str(context.config.get("mode") or "both").strip().lower()
    if mode not in COMPARE_MODES:
        raise ValueError(f"unknown compare mode {mode!r}")
    try:
        threshold = float(context.config.get("threshold", 0.02))
    except (TypeError, ValueError) as exc:
        raise ValueError("Threshold must be a number") from exc
    question = str(context.config.get("question") or "").strip()
    result = _run_vision(
        context,
        asset_id=ref,
        mode="compare",
        question=question,
        options={
            "compare_with": data_uri,
            "compare_kind": "base64",
            "use_model": mode in ("visual", "both"),
            "diff_threshold": max(0.0, min(1.0, threshold)),
        },
    )
    comparison = result.get("comparison") if isinstance(result.get("comparison"), dict) else {}
    ratio = comparison.get("changedPixelsRatio")
    try:
        score = 1.0 - max(0.0, min(1.0, float(ratio))) if ratio is not None else 0.0
    except (TypeError, ValueError):
        score = 0.0
    meta = _observation_meta(result, ref)
    meta["compareWith"] = other_ref
    meta["basis"] = "model" if mode == "visual" else "pixel" if mode == "pixel" else "pixel+model"
    context.emit(
        f"compare · {'changed' if comparison.get('changed') else 'no change'}"
        f" · {score:.3f} similarity"
    )
    return {
        "same": not bool(comparison.get("changed")),
        "score": round(score, 4),
        "differences": list(comparison.get("regions") or [])[:50],
        "meta": meta,
    }


def _questions(context: NodeExecContext) -> list[str]:
    raw = context.config.get("questionsJson")
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str) and raw.strip():
        text = raw.strip()
        if text.startswith("["):
            try:
                items = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"questionsJson is not valid JSON: {exc}") from exc
        else:
            items = [line for line in text.splitlines() if line.strip()]
    else:
        items = []
    out = [str(item).strip() for item in items if str(item).strip()]
    if not out:
        raise ValueError("image.batch needs at least one question")
    if len(out) > MAX_QUESTIONS:
        raise ValueError(f"image.batch is bounded to {MAX_QUESTIONS} questions")
    return [q[:2_000] for q in out]


def _batch_refs(context: NodeExecContext) -> list[str]:
    raw = context.inputs.get("images")
    if raw is None:
        configured = context.config.get("assetIds")
        if isinstance(configured, list):
            raw = configured
        elif isinstance(configured, str) and configured.strip():
            text = configured.strip()
            try:
                raw = json.loads(text) if text.startswith("[") else [p for p in re.split(r"[,\n]", text)]
            except json.JSONDecodeError as exc:
                raise ValueError(f"assetIds is not valid JSON: {exc}") from exc
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        raise ValueError("image.batch needs 1-8 images (wire Images or list Asset ids)")
    refs: list[str] = []
    for item in raw:
        ref = _image_ref(item)
        if ref and ref not in refs:
            refs.append(ref)
    if not refs:
        raise ValueError("image.batch received no valid image references")
    try:
        limit = int(context.config.get("maxImages", MAX_IMAGES))
    except (TypeError, ValueError) as exc:
        raise ValueError("Max images must be a whole number") from exc
    limit = max(1, min(limit, MAX_IMAGES))
    if len(refs) > limit:
        raise ValueError(f"image.batch is bounded to {limit} image(s) (got {len(refs)})")
    # A missing image is reported as one failed row by `exec_image_batch`, not
    # as a batch-wide abort; each row validates its own reference.
    return refs


def exec_image_batch(context: NodeExecContext) -> dict[str, Any]:
    refs = _batch_refs(context)
    questions = _questions(context)
    mode = str(context.config.get("mode") or "analyze").strip().lower()
    if mode not in BATCH_MODES:
        raise ValueError(f"unknown batch mode {mode!r}")
    try:
        concurrency = int(context.config.get("concurrency", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("Concurrency must be a whole number") from exc
    concurrency = max(1, min(concurrency, 3))
    schema_json = str(context.config.get("outputSchemaJson") or "").strip()

    def one(pair: tuple[int, str]) -> dict[str, Any]:
        index, ref = pair
        row: dict[str, Any] = {"index": index, "assetId": ref, "name": ref}
        try:
            asset = _asset(ref, _owner(context))
            row["name"] = str((getattr(asset, "metadata", None) or {}).get("name") or ref)
            if mode == "ocr":
                result = _run_vision(context, asset_id=ref, mode="ocr")
                row.update({
                    "ok": True,
                    "description": str(result.get("description") or ""),
                    "observations": [],
                    "text": result.get("text") or [],
                })
            elif mode == "read_chart":
                result = _run_vision(
                    context, asset_id=ref, mode="chart",
                    question="\n".join(questions),
                    options={"symbol": str(context.config.get("symbol") or "").strip()} if context.config.get("symbol") else {},
                )
                row.update({
                    "ok": True,
                    "description": str(result.get("description") or ""),
                    "observations": _observations(result, 60),
                    "reading": result.get("chart") or {},
                })
            else:
                result = _run_vision(
                    context, asset_id=ref, mode="analyze",
                    question="\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions)),
                )
                data = _parse_extract(result) if schema_json else None
                data, issues = _validate_schema(data, schema_json) if schema_json else (None, None)
                row.update({
                    "ok": True,
                    "description": str(result.get("description") or ""),
                    "observations": _observations(result, 60),
                    "data": data,
                })
                if issues:
                    row["schemaIssues"] = issues
            row["meta"] = _observation_meta(result, ref)
        except ValueError as exc:
            row.update({"ok": False, "error": str(exc), "meta": {"kind": "observation", "verified": False}})
        return row

    pairs = list(enumerate(refs))
    if concurrency > 1 and len(pairs) > 1:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(pool.map(one, pairs))
    else:
        results = [one(pair) for pair in pairs]
    failed = [row for row in results if not row.get("ok")]
    if failed and len(failed) == len(results):
        # Zero successes is not a partial batch: fail loudly so a downstream
        # agent never reasons over an empty result set.
        raise ValueError(
            f"all {len(results)} image read(s) failed: "
            + "; ".join(str(row.get("error") or "unknown error") for row in failed[:3])
        )
    summary = {
        "images": len(results),
        "succeeded": len(results) - len(failed),
        "failed": len(failed),
        "questions": len(questions),
        "mode": mode,
    }
    context.emit(
        f"read {summary['succeeded']}/{summary['images']} image(s)"
        + (f" · {summary['failed']} failed" if failed else "")
    )
    return {"results": results, "summary": summary, "failed": failed}


def build_image_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="image.attach", version="1.0.0", label="Image",
            category="media",
            inputs=(),
            outputs=(
                PortDef(id="image", name="Image", type=PortType.IMAGE),
                PortDef(id="meta", name="Meta", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("assetId", "string", "", max_length=80),
                ConfigField("notes", "string", "", max_length=500),
            ),
            capabilities=("image.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            timeout_ms=60_000,
            executor=exec_image_attach,
            metadata={"docs": (
                "Uploads or references one local image (content-addressed). Only the "
                "asset id is saved in the workflow. Image analysis is a model "
                "observation, never verified market evidence."
            )},
        ),
        NodeDef(
            type="image.analyze", version="1.0.0", label="Analyze image",
            category="media",
            inputs=(
                PortDef(id="image", name="Image", type=PortType.IMAGE, optional=True),
                PortDef(id="question", name="Question", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="description", name="Description", type=PortType.STRING),
                PortDef(id="observations", name="Observations", type=PortType.ARRAY),
                PortDef(id="data", name="Data", type=PortType.OBJECT, nullable=True),
                PortDef(id="meta", name="Meta", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("assetId", "string", "", max_length=80),
                ConfigField("mode", "enum", "describe", enum=ANALYZE_MODES),
                ConfigField("question", "string", "", max_length=4_000),
                ConfigField("schemaJson", "string", "", max_length=20_000),
                ConfigField("region", "string", "", max_length=80),
                ConfigField("maxObservations", "integer", 60, minimum=1, maximum=MAX_OBSERVATIONS),
            ),
            capabilities=("image.read", "model.vision"),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=180_000,
            executor=exec_image_analyze,
            metadata={"docs": (
                "One bounded vision read: describe, answer a question, ground elements "
                "with boxes, or extract a JSON object checked against a schema. The "
                "result is an observation (verified: false), never evidence."
            )},
        ),
        NodeDef(
            type="image.ocr", version="1.0.0", label="Read text (OCR)",
            category="media",
            inputs=(PortDef(id="image", name="Image", type=PortType.IMAGE, optional=True),),
            outputs=(
                PortDef(id="text", name="Text", type=PortType.STRING),
                PortDef(id="spans", name="Spans", type=PortType.ARRAY),
                PortDef(id="meta", name="Meta", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("assetId", "string", "", max_length=80),
                ConfigField("language", "string", "", max_length=40),
                ConfigField("region", "string", "", max_length=80),
            ),
            capabilities=("image.read", "model.vision"),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=120_000,
            executor=exec_image_ocr,
            metadata={"docs": "OCR over an uploaded/rendered image, with pixel spans when the engine returns them."},
        ),
        NodeDef(
            type="image.read_chart", version="1.0.0", label="Read chart",
            category="media",
            inputs=(
                PortDef(id="image", name="Image", type=PortType.IMAGE, optional=True),
                PortDef(id="question", name="Question", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="reading", name="Reading", type=PortType.OBJECT),
                PortDef(id="description", name="Description", type=PortType.STRING),
                PortDef(id="verified", name="Verified", type=PortType.BOOLEAN),
                PortDef(id="meta", name="Meta", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("assetId", "string", "", max_length=80),
                ConfigField("question", "string", "", max_length=4_000),
                ConfigField("symbol", "string", "", max_length=40),
                ConfigField("market", "string", "", max_length=20),
                ConfigField("timeframe", "string", "", max_length=40),
            ),
            capabilities=("image.read", "model.vision", "market.read"),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=180_000,
            executor=exec_image_read_chart,
            metadata={"docs": (
                "Reads a chart image (trend, patterns, levels). `verified` is true "
                "only when the engine's own market-data check confirmed the reading."
            )},
        ),
        NodeDef(
            type="image.compare", version="1.0.0", label="Compare images",
            category="media",
            inputs=(
                PortDef(id="a", name="Candidate", type=PortType.IMAGE, optional=True),
                PortDef(id="b", name="Reference", type=PortType.IMAGE, optional=True),
            ),
            outputs=(
                PortDef(id="same", name="Same", type=PortType.BOOLEAN),
                PortDef(id="score", name="Similarity", type=PortType.NUMBER),
                PortDef(id="differences", name="Differences", type=PortType.ARRAY),
                PortDef(id="meta", name="Meta", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("assetId", "string", "", max_length=80),
                ConfigField("compareAssetId", "string", "", max_length=80),
                ConfigField("mode", "enum", "both", enum=COMPARE_MODES),
                ConfigField("threshold", "number", 0.02, minimum=0.0, maximum=1.0),
                ConfigField("question", "string", "", max_length=2_000),
            ),
            capabilities=("image.read", "model.vision"),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=180_000,
            executor=exec_image_compare,
            metadata={"docs": (
                "Pixel diff and/or a model description of what changed between two "
                "images. `same` is pixel-derived; `meta.basis` says which method ran."
            )},
        ),
        NodeDef(
            type="image.batch", version="1.0.0", label="Read image options",
            category="media",
            inputs=(PortDef(id="images", name="Images", type=PortType.ARRAY, optional=True),),
            outputs=(
                PortDef(id="results", name="Results", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
                PortDef(id="failed", name="Failed", type=PortType.ARRAY),
            ),
            config_fields=(
                ConfigField("assetIds", "string", "", max_length=MAX_ASSET_JSON),
                ConfigField("questionsJson", "string", "", max_length=10_000),
                ConfigField("mode", "enum", "analyze", enum=BATCH_MODES),
                ConfigField("concurrency", "integer", 1, minimum=1, maximum=3),
                ConfigField("maxImages", "integer", MAX_IMAGES, minimum=1, maximum=MAX_IMAGES),
                ConfigField("outputSchemaJson", "string", "", max_length=20_000),
                ConfigField("symbol", "string", "", max_length=40),
            ),
            capabilities=("image.read", "model.vision"),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=600_000,
            executor=exec_image_batch,
            metadata={"docs": (
                "Applies the same 1-5 questions to 1-8 candidate images and returns one "
                "row per image. A failed image is a row with ok=false; the batch never "
                "aborts silently. Use it to read each candle option individually."
            )},
        ),
    ]


__all__ = [
    "ANALYZE_MODES",
    "BATCH_MODES",
    "COMPARE_MODES",
    "MAX_IMAGES",
    "build_image_nodes",
    "exec_image_analyze",
    "exec_image_attach",
    "exec_image_batch",
    "exec_image_compare",
    "exec_image_ocr",
    "exec_image_read_chart",
    "get_vision_asset_store",
    "set_vision_asset_store",
    "set_vision_runner",
]
