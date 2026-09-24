"""MCP tool identity, namespacing and schema normalization (Phase 5A/5B).

The existing `ToolRegistry` allows only `[A-Za-z0-9_]` in a tool name. An MCP
server may use any string. This module:

  * produces a namespaced Eclipse tool name from `(server_id, original tool
    name)` that satisfies the registry's rule;
  * is collision-resistant: if two distinct server/tool identities sanitize to
    the same name, a stable digest is appended (or the collision is rejected) —
    never silently merged;
  * preserves the original server/tool names for events and metadata;
  * validates a discovered JSON input schema before a tool is allowed near the
    registry, so a malformed schema is a diagnostic, not a crash.

Tool descriptions/schemas from a server are UNTRUSTED text. They are bounded
here and never interpreted as instructions.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional

from .config import MAX_TOOL_DESCRIPTION_CHARS, MAX_TOOL_SCHEMA_CHARS

# The registry rule, mirrored so a name is valid before it reaches `register`.
_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_]")

EFFECT_SOURCE_DECLARED = "declared"
EFFECT_SOURCE_ANNOTATION = "annotation"
EFFECT_SOURCE_ASSUMED = "assumed"


def sanitize_component(value: str) -> str:
    """Map a server/tool name onto `[A-Za-z0-9_]`, collapsing runs of others."""
    cleaned = _SANITIZE_RE.sub("_", value or "")
    return cleaned or "unnamed"


def identity_digest(server_id: str, tool_name: str) -> str:
    """A stable, short digest of the canonical (server, tool) identity.

    SHA-256 over a NUL-joined canonical string, so two distinct identities can
    never share it and it is identical across processes (unlike `hash()`).
    """
    canonical = f"{server_id}\x00{tool_name}".encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:8]


def namespace_tool(
    server_id: str,
    tool_name: str,
    *,
    taken: Optional[dict[str, tuple[str, str]]] = None,
) -> str:
    """Return a valid, collision-resistant Eclipse tool name.

    `taken` maps an existing Eclipse name to the identity that owns it
    (`(server_id, tool_name)`). When the sanitized base is already owned by a
    DIFFERENT identity, a stable digest is appended. Raises `ValueError` only if
    even the digested name is owned by a different identity (practically
    impossible for distinct inputs, but deterministic rather than silent).
    """
    base = f"mcp_{sanitize_component(server_id)}_{sanitize_component(tool_name)}"
    taken = taken or {}
    owner = taken.get(base)
    if owner is None or owner == (server_id, tool_name):
        return base
    digested = f"{base}_{identity_digest(server_id, tool_name)}"
    owner = taken.get(digested)
    if owner is None or owner == (server_id, tool_name):
        return digested
    raise ValueError(
        f"MCP tool name collision for {server_id!r}/{tool_name!r}: "
        f"{digested!r} is already owned by a different identity"
    )


def is_valid_tool_name(name: str) -> bool:
    return bool(name) and bool(_NAME_RE.match(name))


class SchemaError(ValueError):
    """A discovered input schema is malformed or unsupported."""


def normalize_input_schema(raw: Any) -> dict[str, Any]:
    """Validate and bound a discovered MCP input schema.

    Accepts a JSON-Schema object describing an object. The registry's argument
    model understands `object` with `properties` whose values declare a
    primitive `type` (string/number/integer/boolean/object/array), an optional
    `enum`, and `required`. A schema outside that shape is rejected so the tool
    is skipped with a safe diagnostic instead of crashing service startup.
    """
    if not isinstance(raw, dict):
        raise SchemaError("input schema is not an object")
    try:
        serialized = json.dumps(raw, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"input schema is not JSON-serializable: {exc}") from exc
    if len(serialized) > MAX_TOOL_SCHEMA_CHARS:
        raise SchemaError(f"input schema exceeds {MAX_TOOL_SCHEMA_CHARS} characters")

    schema_type = raw.get("type")
    # Some servers omit `type` but supply `properties`; accept that, reject a
    # schema that clearly describes a non-object.
    if schema_type is not None and schema_type != "object":
        raise SchemaError(f"unsupported input schema type {schema_type!r} (only 'object')")

    properties = raw.get("properties") or {}
    if not isinstance(properties, dict):
        raise SchemaError("input schema 'properties' must be an object")
    required = raw.get("required") or []
    if not isinstance(required, list) or any(not isinstance(r, str) for r in required):
        raise SchemaError("input schema 'required' must be a list of strings")
    for name, spec in properties.items():
        if not isinstance(name, str) or not name:
            raise SchemaError("input schema property names must be non-empty strings")
        if not isinstance(spec, dict):
            raise SchemaError(f"property {name!r} must be an object")
        declared = spec.get("type")
        if isinstance(declared, list):
            # e.g. ["string", "null"] — accept a single non-null primitive.
            non_null = [t for t in declared if t != "null"]
            if len(non_null) != 1:
                raise SchemaError(f"property {name!r} has an unsupported union type {declared!r}")
            declared = non_null[0]
        if declared is not None and declared not in (
            "string", "number", "integer", "boolean", "object", "array",
        ):
            raise SchemaError(f"property {name!r} has an unsupported type {declared!r}")
        enum = spec.get("enum")
        if enum is not None and (not isinstance(enum, list) or any(isinstance(v, (dict, list)) for v in enum)):
            raise SchemaError(f"property {name!r} has an unsupported enum")

    # Return a normalized copy: object type, bounded properties only.
    normalized = {
        "type": "object",
        "properties": {k: dict(v) for k, v in properties.items()},
        "required": [r for r in required if r in properties],
    }
    if len(json.dumps(normalized, ensure_ascii=False)) > MAX_TOOL_SCHEMA_CHARS:
        raise SchemaError("normalized schema exceeds the size bound")
    return normalized


def bound_description(description: Any) -> str:
    """Bound a server-supplied description; never treat it as instructions."""
    text = description if isinstance(description, str) else ""
    if len(text) > MAX_TOOL_DESCRIPTION_CHARS:
        return text[:MAX_TOOL_DESCRIPTION_CHARS] + "…"
    return text


def classify_effect(
    *,
    original_name: str,
    declared: Optional[str],
    annotations: Any,
) -> tuple[str, str]:
    """Decide a tool's effect class and how it was decided.

    Precedence:
      1. an operator-declared effect in the server config (`declared`);
      2. MCP `annotations.read_only_hint` / `destructive_hint` (`annotation`);
      3. otherwise `unknown` (`assumed`).

    Only `read` is activatable in this slice. A tool the server does not mark
    read-only is NOT assumed safe.
    """
    if declared in ("read", "write", "external_action", "unknown"):
        return declared, EFFECT_SOURCE_DECLARED  # type: ignore[return-value]

    read_only = getattr(annotations, "read_only_hint", None)
    destructive = getattr(annotations, "destructive_hint", None)
    if destructive is True:
        return "external_action", EFFECT_SOURCE_ANNOTATION
    if read_only is True:
        return "read", EFFECT_SOURCE_ANNOTATION
    # An explicit `read_only_hint=False` is a positive signal of a non-read tool.
    if read_only is False:
        return "write", EFFECT_SOURCE_ANNOTATION
    return "unknown", EFFECT_SOURCE_ASSUMED


__all__ = [
    "sanitize_component",
    "identity_digest",
    "namespace_tool",
    "is_valid_tool_name",
    "normalize_input_schema",
    "bound_description",
    "classify_effect",
    "SchemaError",
    "EFFECT_SOURCE_DECLARED",
    "EFFECT_SOURCE_ANNOTATION",
    "EFFECT_SOURCE_ASSUMED",
]
