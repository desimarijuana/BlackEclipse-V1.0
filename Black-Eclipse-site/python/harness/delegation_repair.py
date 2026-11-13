"""Bounded JSON-Schema validation for delegated output (W7).

The schema is DATA, not code: it is size/depth bounded, remote ``$ref`` targets
are refused (no surprise-network/SSRF surface), and validation never coerces a
value. A child that misses the schema gets at most one repair turn; the raw text
is always preserved by the caller.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

MAX_SCHEMA_BYTES = 16_384
MAX_SCHEMA_DEPTH = 12
MAX_ERRORS = 10
MAX_ERROR_CHARS = 500

_REMOTE_REF = re.compile(r"^\s*(https?:|file:|ftp:)", re.IGNORECASE)
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _walk_depth(value: Any, depth: int = 0) -> int:
    if depth > MAX_SCHEMA_DEPTH:
        return depth
    if isinstance(value, dict):
        return max([depth] + [_walk_depth(v, depth + 1) for v in value.values()])
    if isinstance(value, list):
        return max([depth] + [_walk_depth(v, depth + 1) for v in value])
    return depth


def schema_error(schema: Any) -> Optional[str]:
    """A plain refusal reason for an unusable schema, or None."""
    if schema is None:
        return None
    if not isinstance(schema, dict):
        return "the output schema must be a JSON object"
    try:
        encoded = json.dumps(schema, separators=(",", ":"))
    except (TypeError, ValueError):
        return "the output schema is not valid JSON"
    if len(encoded.encode("utf-8")) > MAX_SCHEMA_BYTES:
        return f"the output schema is larger than {MAX_SCHEMA_BYTES} bytes"
    if _walk_depth(schema) > MAX_SCHEMA_DEPTH:
        return f"the output schema is nested more than {MAX_SCHEMA_DEPTH} levels"
    for ref in _iter_refs(schema):
        if _REMOTE_REF.match(ref):
            return "the output schema may not use a remote $ref"
    return None


def _iter_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            refs.append(ref)
        for child in value.values():
            refs.extend(_iter_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_iter_refs(child))
    return refs


def parse_json_output(raw: str) -> Any:
    """Best-effort JSON extraction from a child's answer.

    Accepts a bare JSON value, a fenced JSON block, or JSON surrounded by prose
    (first balanced object/array). Returns ``None`` when no JSON is present.
    """
    text = _FENCE.sub("", str(raw or "").strip())
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass
    # First object or array in the text. Bounded scan; never evaluates anything.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start < 0:
            continue
        end = text.rfind(closer)
        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except (TypeError, ValueError):
                continue
    return None


def validate_output(raw: str, schema: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Validate a child's raw answer against a schema.

    Returns ``{"valid": bool|None, "text": validated-or-raw, "errors": [...]}``.
    ``valid`` is None when no schema was requested. A schema that is itself
    unusable is a refusal, not a pass.
    """
    if schema is None:
        return {"valid": None, "text": str(raw or ""), "errors": []}
    problem = schema_error(schema)
    if problem is not None:
        return {"valid": False, "text": str(raw or ""), "errors": [problem]}
    parsed = parse_json_output(raw)
    if parsed is None:
        return {
            "valid": False,
            "text": str(raw or ""),
            "errors": ["the answer was not JSON"],
        }
    try:
        import jsonschema  # noqa: PLC0415

        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(parsed), key=lambda e: list(e.absolute_path))
    except Exception as exc:  # noqa: BLE001 - a bad schema is a refusal
        return {
            "valid": False,
            "text": str(raw or ""),
            "errors": [f"the output schema could not be checked: {exc}"[:MAX_ERROR_CHARS]],
        }
    if not errors:
        return {
            "valid": True,
            "text": json.dumps(parsed, ensure_ascii=False),
            "errors": [],
        }
    messages = []
    for error in errors[:MAX_ERRORS]:
        location = "/".join(str(part) for part in error.absolute_path) or "(root)"
        messages.append(f"{location}: {error.message}"[:MAX_ERROR_CHARS])
    return {"valid": False, "text": str(raw or ""), "errors": messages}


def repair_prompt(schema: dict[str, Any], raw: str, errors: list[str]) -> str:
    """The single bounded repair instruction.

    The child gets the schema, its own answer and the validation errors, and is
    told to return only corrected JSON. It never sees a tool list on this run.
    """
    return (
        "Your previous answer did not satisfy the required JSON schema.\n"
        "Return ONLY corrected JSON. Do not add prose, tools or explanations.\n\n"
        "SCHEMA:\n"
        + json.dumps(schema, ensure_ascii=False)[:8_000]
        + "\n\nYOUR PREVIOUS ANSWER:\n"
        + str(raw or "")[:8_000]
        + "\n\nVALIDATION ERRORS:\n- "
        + "\n- ".join(errors[:MAX_ERRORS])
    )


__all__ = [
    "MAX_ERRORS",
    "MAX_SCHEMA_BYTES",
    "MAX_SCHEMA_DEPTH",
    "parse_json_output",
    "repair_prompt",
    "schema_error",
    "validate_output",
]
