"""Scoped local write node (Phase 5).

The first general write primitive. It is deliberately narrow:

- a write belongs to a NAMED scope, never an absolute path chosen by the graph;
- the scope's root is configured by the operator (`HARNESS_GRAPH_WRITE_ROOTS`),
  with a safe default `workspace` root under `.black-eclipse/workspace`;
- `path` is relative, `..` and absolute paths are refused, and the resolved
  target (following symlinks) must stay inside the scope root;
- the payload is capped, and a normal write is atomic (temp file + replace).

The compiler still refuses a write in a test run; an operator run grants only
the scopes it explicitly confirmed.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_BYTES = 8 * 1024 * 1024


def write_roots() -> dict[str, Path]:
    """The operator-configured scope map. `workspace` always exists."""
    roots: dict[str, Path] = {
        "workspace": Path.cwd() / ".black-eclipse" / "workspace",
    }
    raw = os.environ.get("HARNESS_GRAPH_WRITE_ROOTS", "").strip()
    if raw:
        try:
            configured = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("HARNESS_GRAPH_WRITE_ROOTS must be a JSON object") from exc
        if not isinstance(configured, dict):
            raise ValueError("HARNESS_GRAPH_WRITE_ROOTS must be a JSON object")
        for name, value in configured.items():
            key = str(name or "").strip()
            if not key or not str(value or "").strip():
                continue
            roots[key] = Path(str(value)).expanduser()
    return roots


def resolve_target(scope: str, relative_path: str) -> tuple[Path, Path]:
    """Resolve a relative path inside a named scope, or raise a clear error."""
    roots = write_roots()
    root = roots.get(scope)
    if root is None:
        raise ValueError(
            f"unknown write scope {scope!r}; configured scopes: {', '.join(sorted(roots))}"
        )
    raw = str(relative_path or "").strip()
    if not raw:
        raise ValueError("a write needs a relative path")
    candidate_path = Path(raw)
    if candidate_path.is_absolute():
        raise ValueError("the write path must be relative to its scope")
    if ".." in candidate_path.parts:
        raise ValueError("the write path cannot contain '..'")
    root = root.expanduser().resolve()
    target = (root / candidate_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"the write path escapes the {scope!r} scope")
    return root, target


def _content_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        data = value
    elif isinstance(value, str):
        data = value.encode("utf-8")
    else:
        data = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError(f"the write payload exceeds {MAX_BYTES} bytes")
    return data


def exec_file_write(context: NodeExecContext) -> dict[str, Any]:
    scope = str(context.config.get("scope") or "workspace").strip()
    path_value = context.inputs.get("path") or context.config.get("path") or ""
    content = context.inputs.get("content")
    if content is None:
        content = context.config.get("content", "")
    data = _content_bytes(content)
    root, target = resolve_target(scope, str(path_value))
    if target == root:
        raise ValueError("the write path must name a file, not the scope root")
    if target.exists() and target.is_dir():
        raise ValueError("the write path names a directory")

    target.parent.mkdir(parents=True, exist_ok=True)
    # Re-check after creating parents: a symlinked directory could otherwise
    # redirect the write outside the root.
    if target.resolve() != target or root not in target.parents:
        raise ValueError(f"the write path escapes the {scope!r} scope")

    append = bool(context.config.get("append", False))
    if append:
        with target.open("ab") as handle:
            handle.write(data)
    else:
        temp = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            temp.write_bytes(data)
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)

    relative = target.relative_to(root).as_posix()
    context.emit(f"wrote {relative} ({len(data)} bytes) in scope {scope}")
    return {"path": relative, "bytes": len(data), "scope": scope}


def build_write_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="file.write", version="1.0.0", label="Write file",
            category="data",
            inputs=(
                PortDef(id="content", name="Content", type=PortType.ANY),
                PortDef(id="path", name="Path", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="path", name="Path", type=PortType.STRING),
                PortDef(id="bytes", name="Bytes", type=PortType.NUMBER),
                PortDef(id="scope", name="Scope", type=PortType.STRING),
            ),
            config_fields=(
                ConfigField("scope", "string", "workspace", max_length=80),
                ConfigField("path", "string", "", max_length=500),
                ConfigField("append", "boolean", False),
            ),
            capabilities=("file.write",),
            side_effects=SideEffect.WRITE,
            allowed_modes=_ALL,
            executor=exec_file_write,
            timeout_ms=30_000,
            metadata={"docs": (
                "Writes one payload inside a named, operator-configured scope. "
                "Relative paths only; '..', absolute paths and symlink escapes are "
                "refused; 8 MB cap; normal writes are atomic. Requires an operator "
                "run that granted this scope; a test run never writes."
            )},
        ),
    ]


__all__ = ["build_write_nodes", "exec_file_write", "resolve_target", "write_roots"]
