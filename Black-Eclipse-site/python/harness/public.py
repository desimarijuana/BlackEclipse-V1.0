"""The PUBLIC API of the Eclipse harness (Round 3 / W10, ADR-H298).

**Why this module exists.** Everything the harness can do was reachable only
from inside this repository. The runtime - the agents, the tools, the
providers, the events, the persistence - was one big importable package with
no declared surface, so another harness could not use it without reading the
source to find out what was safe to touch.

This module is that declaration. It is the whole public surface, and it is
deliberately small:

- `AgenticService` - the runtime, for a caller that wants to run an agent.
- `ToolRegistry` and `ToolDefinition` - the tool surface, for a caller that
  wants to build or inspect tools.
- `RunRequest` / `RunInput` / `RunResult` / `ModelSettings` - the run
  contract.
- `export_tool_schemas` - the portable tool manifest.

**The honesty contract, and it is the point of the export.** A tool is
exported with its PERMISSION and its EFFECT CLASS, or it is not exported at
all. A consumer inherits Eclipse's honesty: it can see that a tool writes, or
that it reaches the network, before it binds it. A tool whose effect is
undeclared is not published - because a consumer cannot honour a rule it
cannot read, and a tool that cannot be classified is a tool nobody should
call.

**What the package does NOT carry.** No app data, no vault, no credentials, no
database. The published package is the RUNTIME; the data belongs to the
installation that runs it. The packaging test asserts that.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from .schemas import ModelSettings, RunInput, RunRequest, RunResult
from .service import AgenticService
from .tools import ToolDefinition, ToolRegistry

#: The version of the declared public API surface (see `__all__`). It changes
#: only when the shape changes; the package version is `harness.__version__`.
HARNESS_API_VERSION = "1.0.0"

#: The manifest version. A consumer can rely on the SHAPE, and this changes
# only when the shape changes.
TOOL_MANIFEST_VERSION = "1"

#: The effect classes a tool may declare. A tool with a write-ish permission
#: and an effect OUTSIDE this vocabulary is not published.
PUBLISHABLE_EFFECTS = ("read", "write", "external_action")


def export_tool_schemas(registry: Optional[ToolRegistry] = None) -> list[dict[str, Any]]:
    """The portable tool manifest: every publishable tool, with its contract.

    The shape is the MCP tool-manifest shape (name / description /
    inputSchema) PLUS the parts a consumer needs to bind a tool safely:
    `permission`, `effect`, `risk`, `version`, and the deprecation fields.

    A tool is NOT exported when its effect is undeclared and its permission is
    not "read" - a write-ish tool with no effect class cannot be honoured by a
    consumer, so it is withheld rather than published ambiguously.
    """
    reg = registry if registry is not None else _default_registry()
    exported: list[dict[str, Any]] = []
    for tool in sorted(reg.list(), key=lambda t: t.name):
        if getattr(tool, "dynamic", False):
            # A per-model predictor is state, not surface: including it would make
            # the manifest (and its digest) depend on the database contents.
            continue
        permission = str(getattr(tool, "permission", "") or "")
        effect = getattr(tool, "effect", None)
        if permission != "read" and (not effect or effect not in PUBLISHABLE_EFFECTS):
            # Unclassifiable and not plainly read-only: withheld.
            continue
        exported.append({
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema,
            "permission": permission,
            "effect": effect,
            "risk": str(getattr(tool, "risk", "") or ""),
            "version": str(getattr(tool, "version", "") or "1.0.0"),
            "deprecated": bool(getattr(tool, "deprecated", False)),
            "replacement": getattr(tool, "replacement", None),
        })
    return exported


def tool_manifest(registry: Optional[ToolRegistry] = None) -> dict[str, Any]:
    """The whole manifest, with its version and its digest.

    The digest is over the CANONICAL manifest, so a consumer can tell whether
    two installations offer the same tool surface.
    """
    tools = export_tool_schemas(registry)
    canonical = json.dumps(tools, sort_keys=True, separators=(",", ":"))
    return {
        "manifestVersion": TOOL_MANIFEST_VERSION,
        "toolCount": len(tools),
        "digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16],
        "tools": tools,
    }


def _default_registry() -> ToolRegistry:
    """The registry the runtime actually uses."""
    from .service import AgenticService as _Service  # noqa: PLC0415

    return _Service().registry


__all__ = [
    "AgenticService",
    "HARNESS_API_VERSION",
    "ModelSettings",
    "PUBLISHABLE_EFFECTS",
    "RunInput",
    "RunRequest",
    "RunResult",
    "TOOL_MANIFEST_VERSION",
    "ToolDefinition",
    "ToolRegistry",
    "export_tool_schemas",
    "tool_manifest",
]
