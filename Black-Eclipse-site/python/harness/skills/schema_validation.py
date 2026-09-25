"""Full JSON Schema validation for skill manifests and outputs.

The manifest declares `inputSchema`/`outputSchema` as JSON Schema objects. Input
validation reuses the runtime's pydantic builder (`tools._args_model`) for tool
call compatibility, but a skill OUTPUT is model-authored prose-or-JSON and must
be checked against the DECLARED schema completely — nested object types, array
item types, enums, numeric bounds (`minimum`/`maximum`/`exclusive*`),
`minLength`/`maxLength`, `pattern`, `additionalProperties` and required fields.
A top-level `required` check alone is not validation.

`jsonschema` is already present transitively (via the `mcp` SDK) and is declared
in `python/requirements.txt`. There is no second schema library: the manifest
itself is still validated by pydantic; this module only adds standards-compliant
validation of the JSON Schema documents those manifests contain.
"""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - import guard mirrors the runtime's resilience style
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError
    from jsonschema.validators import validator_for

    _JSONSCHEMA_AVAILABLE = True
except Exception:  # noqa: BLE001 - a missing validator must degrade, not crash
    Draft202012Validator = None  # type: ignore[assignment]
    SchemaError = Exception  # type: ignore[assignment,misc]
    validator_for = None  # type: ignore[assignment]
    _JSONSCHEMA_AVAILABLE = False


def jsonschema_available() -> bool:
    return _JSONSCHEMA_AVAILABLE


def check_schema_structural(schema: Any) -> tuple[bool, list[str]]:
    """A dependency-free structural check of a schema document.

    Used where the runtime can proceed without the full validator (skill INPUT
    validation, which is pydantic-based). It verifies only that the document is
    an object schema, never that nested keywords are valid — so it must not be
    used to claim a schema was fully validated.
    """
    if schema is None:
        return True, []
    if not isinstance(schema, dict):
        return False, [f"schema must be a JSON object, got {type(schema).__name__}"]
    schema_type = schema.get("type", "object")
    if schema_type != "object":
        return False, ["top-level schema type must be 'object'"]
    if "properties" in schema and not isinstance(schema["properties"], dict):
        return False, ["properties must be an object"]
    return True, []


def check_schema(schema: Any) -> tuple[bool, list[str]]:
    """Validate that `schema` is itself a well-formed JSON Schema.

    Returns `(ok, errors)`. Empty/missing schemas are accepted (a skill may be
    manifest-only or have no output schema). A malformed schema is a hard config
    error with an actionable message — never silently ignored.

    FAILS CLOSED when the validator is unavailable: a declared schema cannot be
    verified without `jsonschema`, so returning "ok" would let an unverifiable
    schema be enabled and later report partial validation as full.
    """
    if schema is None:
        return True, []
    if not _JSONSCHEMA_AVAILABLE:
        return False, [
            "full JSON Schema validation requires the 'jsonschema' package "
            "(install the Python runtime: npm run setup:python)"
        ]
    structural_ok, structural_errors = check_schema_structural(schema)
    if not structural_ok:
        return False, structural_errors
    try:
        validator_cls = validator_for(schema, default=Draft202012Validator)  # type: ignore[arg-type]
        validator_cls.check_schema(schema)
        return True, []
    except SchemaError as exc:
        location = "/".join(str(p) for p in getattr(exc, "absolute_path", []) or [])
        where = f" at {location}" if location else ""
        return False, [f"invalid JSON Schema{where}: {exc.message}"]
    except Exception as exc:  # noqa: BLE001 - a malformed schema must be reported
        return False, [f"invalid JSON Schema: {exc}"]


def validate_output(schema: Any, instance: Any) -> tuple[bool, list[str]]:
    """Validate a parsed skill output `instance` against its declared `schema`.

    Returns `(ok, errors)`. `errors` are human-readable `path: message` strings so
    a caller/operator can see exactly which nested field failed. Never raises.
    """
    if schema is None:
        return True, []
    ok, schema_errors = check_schema(schema)
    if not ok:
        return False, [f"declared output schema is invalid: {e}" for e in schema_errors]
    # `check_schema` already failed closed when `jsonschema` is unavailable, so
    # reaching here means full validation is possible. There is deliberately no
    # "required-fields only" fallback: partial validation must never be reported
    # as full validation.
    try:
        validator_cls = validator_for(schema, default=Draft202012Validator)  # type: ignore[arg-type]
        validator = validator_cls(schema)
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    except Exception as exc:  # noqa: BLE001 - a validator failure is a validation failure
        return False, [f"output validation error: {exc}"]
    if not errors:
        return True, []
    messages: list[str] = []
    for error in errors[:20]:
        path = "/".join(str(p) for p in error.absolute_path)
        prefix = f"{path}: " if path else ""
        messages.append(f"{prefix}{error.message}")
    return False, messages


__all__ = ["check_schema", "check_schema_structural", "jsonschema_available", "validate_output"]
