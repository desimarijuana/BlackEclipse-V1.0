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

# Providers (OpenAI, and several OpenAI-compatible gateways) accept function
# names up to 64 characters; exceeding it fails at the WIRE, not at registration.
# The assembled `mcp__<server>__<tool>` name is clamped to this, with a stable
# digest suffix, so an over-long pair is a labelled diagnostic here instead of a
# runtime failure. The delimiter form is unchanged; clamping is a last resort.
MAX_ECLIPSE_TOOL_NAME = 64

EFFECT_SOURCE_DECLARED = "declared"
EFFECT_SOURCE_ANNOTATION = "annotation"
EFFECT_SOURCE_ASSUMED = "assumed"

# Tokens that suggest a tool WRITES. Used only to FLAG a possible mismatch for an
# operator to acknowledge — never to infer an effect (inferring from a name would
# auto-activate a tool on a guess, which is worse). A read-named tool can still
# be a trap (`API-move-page` has no write-looking token), and a write-named tool
# can be a read (`API-post-search`), so the name is an untrusted hint either way.
WRITE_SHAPED_TOKENS = (
    "create", "delete", "update", "patch", "move", "post", "append", "set",
    "remove", "write", "archive",
)


def writes_like_name(name: str) -> bool:
    """Whether a tool NAME contains a write-ish token (a possible mismatch).

    A pure, untrusted signal. It never decides an effect; it only lets the
    operator be warned when a tool marked `read` has a write-shaped name.
    """
    lowered = (name or "").lower()
    return any(token in lowered for token in WRITE_SHAPED_TOKENS)


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

    The delimiter is a DOUBLE underscore (`mcp__<server>__<tool>`), matching
    Claude Code / Codex / OpenCode. This disambiguates the server/tool boundary
    when either component itself contains an underscore, so `mcp__a__b_c` and
    `mcp__a_b__c` are distinct without a digest.

    `taken` maps an existing Eclipse name to the identity that owns it
    (`(server_id, tool_name)`). When the sanitized base is already owned by a
    DIFFERENT identity, a stable digest is appended (the genuine-collision
    last resort). Raises `ValueError` only if even the digested name is owned by
    a different identity.
    """
    raw = f"mcp__{sanitize_component(server_id)}__{sanitize_component(tool_name)}"
    base = _clamp_name(raw, server_id, tool_name)
    taken = taken or {}
    owner = taken.get(base)
    if owner is None or owner == (server_id, tool_name):
        return base
    # A collision (or clamping brought two identities together): append the
    # stable identity digest, itself clamped.
    digested = _clamp_name(f"{base}_{identity_digest(server_id, tool_name)}", server_id, tool_name)
    owner = taken.get(digested)
    if owner is None or owner == (server_id, tool_name):
        return digested
    raise ValueError(
        f"MCP tool name collision for {server_id!r}/{tool_name!r}: "
        f"{digested!r} is already owned by a different identity"
    )


def _clamp_name(name: str, server_id: str, tool_name: str) -> str:
    """Clamp an assembled name to `MAX_ECLIPSE_TOOL_NAME`, adding a stable digest.

    A name at or under the limit is returned byte-identical. An over-long name is
    truncated and a short identity digest appended, so the result is unique and
    still `mcp__...`-shaped. The digest makes the truncation collision-resistant.
    """
    if len(name) <= MAX_ECLIPSE_TOOL_NAME:
        return name
    suffix = "_" + identity_digest(server_id, tool_name)
    keep = MAX_ECLIPSE_TOOL_NAME - len(suffix)
    return f"{name[:keep]}{suffix}"


def is_valid_tool_name(name: str) -> bool:
    return bool(name) and bool(_NAME_RE.match(name))


def name_was_clamped(server_id: str, tool_name: str) -> bool:
    """Whether `namespace_tool` would truncate this identity (for a diagnostic)."""
    raw = f"mcp__{sanitize_component(server_id)}__{sanitize_component(tool_name)}"
    return len(raw) > MAX_ECLIPSE_TOOL_NAME


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
      1. an operator-declared effect in the server config (`declared`) — the ONLY
         trusted source;
      2. MCP annotations, which are server-provided and UNTRUSTED;
      3. otherwise `unknown` (`assumed`).

    Annotations only ever DEGRADE trust or inform the operator's review:
      * `destructive_hint=True`  → `external_action` (never activatable here);
      * `read_only_hint=False`   → `write` (never activatable here);
      * `read_only_hint=True`    → `read` **pending explicit confirmation
        (see `manager`)** — the hint alone must NOT activate a tool, because a
        server can lie. Activation additionally requires the operator to declare
        the effect or confirm the catalog digest;
      * any other combination     → `unknown`.

    The returned `effect_source` is `"declared"` | `"annotation"` | `"assumed"`
    so the manager/UI can require confirmation for annotation-sourced effects.
    """
    if declared in ("read", "write", "external_action", "unknown"):
        return declared, EFFECT_SOURCE_DECLARED  # type: ignore[return-value]

    read_only = getattr(annotations, "read_only_hint", None)
    destructive = getattr(annotations, "destructive_hint", None)
    if destructive is True:
        return "external_action", EFFECT_SOURCE_ANNOTATION
    if read_only is False:
        return "write", EFFECT_SOURCE_ANNOTATION
    if read_only is True:
        return "read", EFFECT_SOURCE_ANNOTATION
    return "unknown", EFFECT_SOURCE_ASSUMED


__all__ = [
    "sanitize_component",
    "identity_digest",
    "namespace_tool",
    "is_valid_tool_name",
    "name_was_clamped",
    "MAX_ECLIPSE_TOOL_NAME",
    "normalize_input_schema",
    "bound_description",
    "classify_effect",
    "writes_like_name",
    "WRITE_SHAPED_TOKENS",
    "SchemaError",
    "EFFECT_SOURCE_DECLARED",
    "EFFECT_SOURCE_ANNOTATION",
    "EFFECT_SOURCE_ASSUMED",
]
