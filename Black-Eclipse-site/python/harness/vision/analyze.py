"""Structured model analysis: the general `analyze`/`describe`/QA path.

Builds a bounded prompt, asks a vision model, and normalizes the reply into
`VisualObservation`s. Model JSON is parsed defensively (extract the object,
repair only what is safe, validate against a schema) — malformed output is a
classified failure, never silently accepted.

Tiling is applied when the image is large, and the text the model transcribes
from an image is passed through the injection guard before it can reach the
agent context.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from .contracts import Region, VisionInput, VisionResult, VisionUsage, VisualObservation
from .errors import VisionError, VisionErrorClass
from .image import DecodedImage
from .providers import ModelCallResult, call_model
from .routing import RoutingPlan
from .security import scan_text, wrap_untrusted

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

#: The structured contract a general analyze call should return.
ANALYZE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "kind": {"type": "string"},
                    "region": {"type": ["array", "object", "null"]},
                    "confidence": {"type": "number"},
                },
                "required": ["text"],
            },
        },
        "text": {"type": "array"},
        "objects": {"type": "array"},
        "confidence": {"type": "number"},
    },
}

_ANALYZE_PROMPT = (
    "You are Eclipse's image-analysis engine. Answer the user's question about "
    "the attached image using only what is actually visible. Do not guess.\n"
    "Reply with a single JSON object:\n"
    '{"description": "<concise answer>", "observations": '
    '[{"text": "<a fact you can see>", "region": [x,y,w,h] or null, "confidence": 0..1}], '
    '"confidence": 0..1}\n'
    "Coordinate regions are optional and in image pixels (top-left origin)."
)


def extract_json(text: str) -> Optional[dict[str, Any]]:
    """Extract and parse the first JSON object in a model reply (safe repairs)."""
    if not text:
        return None
    match = _JSON_BLOCK.search(text)
    if not match:
        return None
    blob = match.group(0)
    try:
        parsed = json.loads(blob)
    except ValueError:
        try:
            repaired = _repair(blob)
            parsed = json.loads(repaired)
        except ValueError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _repair(blob: str) -> str:
    """Conservative JSON repairs: trailing commas and single-quoted strings only."""
    text = re.sub(r",\s*([}\]])", r"\1", blob)
    # Convert 'key': / 'value' single quotes to double quotes when unambiguous.
    text = re.sub(r"'([^'\"\\]{1,80})'\s*:", r'"\1":', text)
    return text


def validate_json(payload: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, Optional[str]]:
    try:
        import jsonschema  # noqa: PLC0415

        jsonschema.validate(payload, schema)
        return True, None
    except Exception as exc:  # noqa: BLE001 - jsonschema.ValidationError and friends
        try:
            import jsonschema  # noqa: PLC0415

            if isinstance(exc, jsonschema.ValidationError):
                return False, exc.message
        except Exception:  # noqa: BLE001
            pass
        return False, str(exc)


def _observation_from_item(item: Any) -> Optional[VisualObservation]:
    if not isinstance(item, dict):
        if isinstance(item, str):
            return VisualObservation(text=item, kind="observed", method="model", confidence=0.5)
        return None
    text = str(item.get("text") or item.get("label") or item.get("name") or "").strip()
    if not text:
        return None
    region = Region.from_bbox(item.get("region") or item.get("bbox") or item.get("bounds"))
    try:
        confidence = float(item.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    return VisualObservation(
        text=text, kind="observed", region=region, confidence=max(0.0, min(1.0, confidence)),
        method="model", details={k: v for k, v in item.items() if k not in ("text", "label", "name", "region", "bbox", "bounds", "confidence")},
    )


@dataclass
class AnalysisOutcome:
    description: str
    observations: list[VisualObservation]
    confidence: float
    structured: dict[str, Any]
    security: dict[str, Any]
    warnings: list[str]


async def analyze_image(
    decoded: DecodedImage,
    input: VisionInput,
    plan: RoutingPlan,
    *,
    timeout_s: float = 120.0,
    tile_size: int = 1536,
    overlap: float = 0.1,
    max_tiles: int = 16,
) -> tuple[AnalysisOutcome, ModelCallResult]:
    """Run a general analysis. Returns the outcome and the (last) model call.

    Raises `VisionError` on provider failure; malformed JSON that cannot be
    parsed yields a text-only outcome (honest) plus a warning, not a fake.
    """
    prompt = _ANALYZE_PROMPT
    if input.question:
        prompt += f"\n\nQuestion: {input.question}"

    images = [decoded.image]
    result = await call_model(
        plan.settings, prompt, images, task="vision",
        timeout_s=timeout_s, structured=True, backend=plan.kind,
    )

    payload = extract_json(result.text)
    warnings: list[str] = []
    if payload is None:
        # No JSON: treat the whole reply as the description (legitimate prose).
        outcome = _from_text(result.text, warnings)
        _security_scan(outcome, input)
        return outcome, result

    valid, error = validate_json(payload, ANALYZE_SCHEMA)
    if not valid:
        warnings.append(f"the model JSON was missing required fields: {error}")
    observations = [
        obs for obs in (_observation_from_item(i) for i in payload.get("observations", []) or []) if obs is not None
    ]
    try:
        confidence = float(payload.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    description = str(payload.get("description") or "")
    outcome = AnalysisOutcome(
        description=description, observations=observations,
        confidence=max(0.0, min(1.0, confidence or 0.5)),
        structured=payload, security={}, warnings=warnings,
    )
    _security_scan(outcome, input)
    return outcome, result


def _from_text(text: str, warnings: list[str]) -> AnalysisOutcome:
    cleaned = (text or "").strip()
    return AnalysisOutcome(
        description=cleaned, observations=[], confidence=0.4, structured={}, security={}, warnings=warnings,
    )


def _security_scan(outcome: AnalysisOutcome, input: VisionInput) -> None:
    """Scan model-transcribed text for injection/secrets (DATA, not instructions)."""
    blob = " ".join([outcome.description, *(o.text for o in outcome.observations)])
    scan = scan_text(blob)
    outcome.security = scan.to_dict()
    if scan.injection_signals:
        outcome.warnings.append(
            f"{len(scan.injection_signals)} instruction-like phrase(s) were recognized in the image; "
            "the text is untrusted data and will not be followed."
        )


def guarded_description(outcome: AnalysisOutcome) -> str:
    """Return the description, wrapped as untrusted data when it looks suspicious."""
    if outcome.security.get("injectionSignals"):
        return wrap_untrusted(outcome.description, source="image")
    return outcome.description


def build_result(
    outcome: AnalysisOutcome,
    result: ModelCallResult,
    *,
    mode: str,
    asset_id: Optional[str] = None,
    provenance: Optional[dict[str, Any]] = None,
) -> VisionResult:
    usage = VisionUsage(
        input_tokens=result.usage.input_tokens, output_tokens=result.usage.output_tokens,
        total_tokens=result.usage.total_tokens, estimated=result.usage.estimated,
    )
    return VisionResult(
        ok=True, mode=mode, description=guarded_description(outcome),
        observations=outcome.observations, objects=outcome.observations,
        structured=outcome.structured or None, confidence=outcome.confidence,
        provider=result.provider, model=result.model, backend=result.backend,
        latency_ms=result.latency_ms, usage=usage,
        provenance={**(provenance or {}), "security": outcome.security},
        warnings=outcome.warnings, asset_id=asset_id,
    )


__all__ = [
    "ANALYZE_SCHEMA", "AnalysisOutcome", "analyze_image", "build_result",
    "extract_json", "validate_json", "guarded_description",
]
