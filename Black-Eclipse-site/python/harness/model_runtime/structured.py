"""Structured output: validate, repair, retry, fall back (spec §28).

The model is never trusted to return clean JSON. This manager parses a response,
validates it against a JSON Schema (using the already-installed `jsonschema`),
and on failure asks the model once to repair the payload before the runtime
moves to a fallback model. Validation failure is a normalized
`structured_output_error`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .errors import ErrorClass, ModelError

try:  # jsonschema is a harness dependency (python/requirements.txt)
    import jsonschema as _jsonschema
except Exception:  # noqa: BLE001 - degrade to structural checks only
    _jsonschema = None


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@dataclass
class StructuredResult:
    ok: bool
    value: Optional[Any] = None
    raw_text: str = ""
    error: Optional[ModelError] = None
    repaired: bool = False
    attempts: int = 1
    validation_error: Optional[str] = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "value": self.value,
            "repaired": self.repaired,
            "attempts": self.attempts,
            "error": self.error.to_dict() if self.error else None,
            "validationError": self.validation_error,
        }


def extract_json(text: str) -> Optional[Any]:
    """Best-effort JSON extraction: fenced block, then the outermost object/array."""
    if not text:
        return None
    stripped = text.strip()
    fences = _JSON_FENCE.findall(stripped)
    candidates = list(fences) + [stripped]
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        for open_ch, close_ch in (("{", "}"), ("[", "]")):
            start = candidate.find(open_ch)
            end = candidate.rfind(close_ch)
            if start != -1 and end > start:
                try:
                    return json.loads(candidate[start:end + 1])
                except json.JSONDecodeError:
                    continue
    return None


class SchemaValidator:
    """Validate a value against a JSON Schema, or a structural fallback."""

    def validate(self, value: Any, schema: Optional[dict[str, Any]]) -> Optional[str]:
        """Return an error string, or None when valid."""
        if schema is None:
            return None
        if _jsonschema is not None:
            try:
                _jsonschema.validate(instance=value, schema=schema)
                return None
            except _jsonschema.ValidationError as exc:  # type: ignore[attr-defined]
                return str(exc.message)
            except _jsonschema.SchemaError as exc:  # type: ignore[attr-defined]
                return f"invalid schema: {exc.message}"
        # Fallback: type/shape only.
        expected = schema.get("type")
        if expected == "object" and not isinstance(value, dict):
            return "expected an object"
        if expected == "array" and not isinstance(value, list):
            return "expected an array"
        required = schema.get("required")
        if expected == "object" and isinstance(value, dict) and required:
            missing = [k for k in required if k not in value]
            if missing:
                return f"missing required keys: {', '.join(missing)}"
        return None


class StructuredOutputManager:
    """Parse + validate + repair + retry (spec §28)."""

    def __init__(self, *, max_repair_attempts: int = 1) -> None:
        self._validator = SchemaValidator()
        self._max_repair_attempts = max_repair_attempts

    @property
    def validator(self) -> SchemaValidator:
        return self._validator

    def parse_and_validate(
        self,
        text: str,
        schema: Optional[dict[str, Any]],
    ) -> StructuredResult:
        value = extract_json(text)
        if value is None:
            return StructuredResult(
                ok=False,
                raw_text=text,
                validation_error="response was not valid JSON",
                error=ModelError(
                    error_class=ErrorClass.STRUCTURED_OUTPUT_ERROR,
                    message="the model did not return valid JSON",
                ),
            )
        error = self._validator.validate(value, schema)
        if error is None:
            return StructuredResult(ok=True, value=value, raw_text=text)
        return StructuredResult(
            ok=False,
            value=value,
            raw_text=text,
            validation_error=error,
            error=ModelError(
                error_class=ErrorClass.STRUCTURED_OUTPUT_ERROR,
                message=f"structured output failed validation: {error}",
            ),
        )

    def repair_prompt(self, text: str, schema: Optional[dict[str, Any]], error: str) -> str:
        schema_text = json.dumps(schema, sort_keys=True) if schema else "{}"
        return (
            "The previous answer was not valid JSON for the required schema. "
            "Return ONLY corrected JSON, with no prose or code fences.\n\n"
            f"Schema: {schema_text}\n"
            f"Validation error: {error}\n"
            f"Previous answer:\n{text}"
        )

    @property
    def max_repair_attempts(self) -> int:
        return self._max_repair_attempts


__all__ = [
    "SchemaValidator",
    "StructuredOutputManager",
    "StructuredResult",
    "extract_json",
]
