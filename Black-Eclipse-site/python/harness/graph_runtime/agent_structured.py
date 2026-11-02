"""Structured model calls for the classify / extract / summarize / critique nodes.

Each function is ONE bounded model call that returns strict JSON validated against
a small schema. They never call tools, never persist anything and never touch
another subsystem: the graph owns ordering and effects, and the node executor
owns the contract (allowed label, verdict set, extraction validity).

Model credentials arrive as `ModelSettings`, resolved by the front door and held
in memory for the run only.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..model_runtime import get_runtime
from ..schemas import ModelSettings

MAX_TEXT = 40_000
MAX_LABELS = 30
LABEL_MAX = 80
VERDICTS = ("supported", "weak", "contradicted")

CLASSIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "maxLength": LABEL_MAX},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "scores": {"type": "object"},
    },
    "required": ["label", "confidence"],
    "additionalProperties": False,
}

EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "data": {"type": "object"},
    },
    "required": ["data"],
    "additionalProperties": False,
}

SUMMARIZE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "maxLength": 8_000},
        "keyPoints": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
    },
    "required": ["summary"],
    "additionalProperties": False,
}

CRITIQUE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "issues": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
    },
    "required": ["verdict"],
    "additionalProperties": False,
}


def normalize_labels(raw: Any) -> list[str]:
    """Parse the inspector's comma list into a bounded, de-duplicated set."""
    if isinstance(raw, list):
        parts = [str(item) for item in raw]
    else:
        parts = str(raw or "").split(",")
    labels: list[str] = []
    seen: set[str] = set()
    for part in parts:
        label = part.strip()
        if not label:
            continue
        if len(label) > LABEL_MAX:
            raise ValueError(f"label {label[:20]!r}… exceeds {LABEL_MAX} characters")
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
    if len(labels) > MAX_LABELS:
        raise ValueError(f"declare at most {MAX_LABELS} labels")
    return labels


def _bounded(value: Any, field: str) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.strip()
    if not text:
        raise ValueError(f"{field} is empty; nothing to send to the model")
    if len(text) > MAX_TEXT:
        raise ValueError(f"{field} exceeds {MAX_TEXT} characters; shorten it before this node")
    return text


async def _generate(
    *,
    task: str,
    system: str,
    payload: dict[str, Any],
    schema: dict[str, Any],
    model_settings: Optional[dict[str, Any]],
    timeout_s: float = 90.0,
) -> dict[str, Any]:
    if not model_settings:
        raise ValueError(
            "model settings are unavailable for this run; start it as an operator "
            "run with a configured model provider"
        )
    try:
        settings = ModelSettings(**model_settings)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid model settings: {exc}") from exc

    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

    response = await get_runtime().generate(
        settings=settings,
        messages=[
            SystemMessage(content=system),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ],
        task=task,
        response_schema=schema,
        timeout_s=timeout_s,
        temperature=0.0,
    )
    structured = (response.decision or {}).get("structured") or {}
    if not structured.get("ok"):
        reason = structured.get("validationError") or "the model returned no valid JSON"
        raise ValueError(f"{task} was not a valid response: {reason}")
    value = structured.get("value")
    if not isinstance(value, dict):
        raise ValueError(f"{task} did not return a JSON object")
    return value


async def classify_json(
    *, text: str, labels: list[str], instructions: str,
    model_settings: Optional[dict[str, Any]],
) -> dict[str, Any]:
    body = _bounded(text, "text")
    if len(labels) < 2:
        raise ValueError("declare at least two labels to classify into")
    system = (
        "Classify the supplied text into EXACTLY ONE of the declared labels. "
        "Return ONLY the strict JSON object the schema describes. "
        "`confidence` is your calibrated probability for the chosen label (0-1); "
        "`scores` may map labels to probabilities. Do not invent labels outside "
        "the declared set, and do not explain."
    )
    return await _generate(
        task="graph_classify",
        system=system,
        payload={"labels": labels, "instructions": instructions, "text": body},
        schema=CLASSIFY_SCHEMA,
        model_settings=model_settings,
        timeout_s=60.0,
    )


async def extract_json(
    *, text: str, schema: dict[str, Any], instructions: str,
    model_settings: Optional[dict[str, Any]],
) -> dict[str, Any]:
    body = _bounded(text, "text")
    system = (
        "Extract the requested fields from the supplied text into one JSON object. "
        "Return ONLY the strict JSON object the schema describes, with `data` "
        "holding the extracted object. Use null for a field that the text does "
        "not state; never guess a value that is absent from the text."
    )
    payload: dict[str, Any] = {"instructions": instructions, "text": body}
    if schema:
        payload["targetSchema"] = schema
    return await _generate(
        task="graph_extract",
        system=system,
        payload=payload,
        schema=EXTRACT_SCHEMA,
        model_settings=model_settings,
        timeout_s=120.0,
    )


async def summarize_json(
    *, text: Any, max_words: int, style: str,
    model_settings: Optional[dict[str, Any]],
) -> dict[str, Any]:
    body = _bounded(text, "text")
    limit = max(10, min(int(max_words), 2_000))
    bullet = style == "bullets"
    system = (
        f"Summarize the supplied material in at most {limit} words. "
        + ("Also list 3-8 key points." if bullet else "Use a short prose summary only.")
        + " Never add a fact that is not in the material; if it is ambiguous, say so."
        " Return ONLY the strict JSON object the schema describes."
    )
    return await _generate(
        task="graph_summarize",
        system=system,
        payload={"maxWords": limit, "style": style, "text": body},
        schema=SUMMARIZE_SCHEMA,
        model_settings=model_settings,
        timeout_s=120.0,
    )


async def critique_json(
    *, finding: str, evidence: Any, rubric: str,
    model_settings: Optional[dict[str, Any]],
) -> dict[str, Any]:
    body = _bounded(finding, "finding")
    system = (
        "Judge whether the finding is supported by the supplied evidence. "
        "`verdict` MUST be exactly one of: supported, weak, contradicted. "
        "`score` is 0-1 support strength; `issues` lists concrete problems "
        "(missing evidence, overreach, contradiction). Do not rewrite the finding "
        "and do not add facts. Return ONLY the strict JSON object the schema describes."
    )
    payload: dict[str, Any] = {"finding": body, "rubric": rubric}
    if evidence is not None:
        payload["evidence"] = evidence
    return await _generate(
        task="graph_critique",
        system=system,
        payload=payload,
        schema=CRITIQUE_SCHEMA,
        model_settings=model_settings,
        timeout_s=90.0,
    )


# ── Contract checks owned by the NODE (no model involved) ─────────────────────

_PRIMITIVES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
    "null": (type(None),),
}


def validate_extraction(value: Any, schema: dict[str, Any]) -> tuple[bool, list[str]]:
    """Structural check of an extracted object against a small JSON Schema subset.

    Supports `type`, `required`, `properties` (one level deep) and `items` for
    arrays. Anything outside that subset is IGNORED rather than silently claimed
    as validated — the node reports `valid` only for what it actually checked.
    """
    if not isinstance(schema, dict) or not schema:
        return True, []
    if not isinstance(value, dict):
        return False, ["the extracted value is not a JSON object"]
    issues: list[str] = []
    required = schema.get("required")
    if isinstance(required, list):
        for key in required:
            if isinstance(key, str) and key not in value:
                issues.append(f"missing required field {key!r}")
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for key, spec in properties.items():
            if key not in value or not isinstance(spec, dict):
                continue
            expected = spec.get("type")
            if not isinstance(expected, str) or expected not in _PRIMITIVES:
                continue
            if not isinstance(value[key], _PRIMITIVES[expected]):
                issues.append(f"field {key!r} should be {expected}")
            elif expected == "array" and isinstance(spec.get("items"), dict):
                item_type = spec["items"].get("type")
                if item_type in _PRIMITIVES:
                    bad = [
                        index for index, item in enumerate(value[key])
                        if not isinstance(item, _PRIMITIVES[item_type])
                    ]
                    if bad:
                        issues.append(f"field {key!r} has {len(bad)} item(s) that are not {item_type}")
    return (not issues), issues


__all__ = [
    "CLASSIFY_SCHEMA",
    "CRITIQUE_SCHEMA",
    "EXTRACT_SCHEMA",
    "MAX_LABELS",
    "MAX_TEXT",
    "SUMMARIZE_SCHEMA",
    "VERDICTS",
    "classify_json",
    "critique_json",
    "extract_json",
    "normalize_labels",
    "summarize_json",
    "validate_extraction",
]
