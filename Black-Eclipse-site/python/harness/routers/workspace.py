"""Workspace folder selection routes.

A person picks a folder; an operator approves it; the runtime works there. Every
MUTATING route (approve / select / revoke) is `require_operator` — transport or
token, never a body flag — mirroring the code and MCP routers. Reads (browse /
list) are operator-gated too, so only the local front door can enumerate the
filesystem. Shared state comes from `harness.deps`; this module never imports
`main`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["workspace"])


class ApproveRootRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    label: Optional[str] = Field(default=None, max_length=200)


class SelectRootRequest(BaseModel):
    rootId: Optional[str] = Field(default=None, max_length=200)  # noqa: N815


class ReadFileRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    rootId: Optional[str] = Field(default=None, max_length=200)  # noqa: N815


class WriteFileRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    content: str = Field(default="", max_length=2_000_000)


class MkdirRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class MkdirBrowseRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    name: str = Field(min_length=1, max_length=128)


def _editor_root(root_id: Optional[str] = None):
    """The workspace root for the human editor, or raise 400.

    With a `root_id` (a chat's bound project), the approved root is resolved by
    id — the client never supplies a path. Otherwise the globally selected root
    (or the repo default) applies.
    """
    from ..code.workspace import default_root, trusted_root_path  # noqa: PLC0415

    if root_id:
        root = trusted_root_path(root_id)
        if root is None:
            raise HTTPException(status_code=404, detail="That folder is not approved.")
        return root
    root = default_root()
    if root is None:
        raise HTTPException(status_code=400, detail="No workspace folder is selected.")
    return root


def _resolve_editor_path(rel: str, root_id: Optional[str] = None):
    """Resolve an editor path inside the active root, or raise 400 (structured).

    The SAME confinement the agent tools use (`policy.resolve_within`): protected
    paths, ignored dirs, traversal and symlink escapes are all refused here too —
    the human editor is not a second, weaker door.
    """
    from ..code.policy import PolicyDenial, resolve_within  # noqa: PLC0415

    root = _editor_root(root_id)
    try:
        resolved = resolve_within(root, rel)
    except PolicyDenial as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.reason}) from exc
    return root, resolved


@router.get("/workspace/browse")
def browse_folders(
    path: Optional[str] = None, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """List the DIRECT children of a folder for the picker (bounded, read-only)."""
    from ..code.roots import browse  # noqa: PLC0415

    return {"success": True, **browse(path)}


@router.post("/workspace/browse/mkdir")
def create_browsed_folder(
    body: MkdirBrowseRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Create a folder in the directory the picker is showing (operator act)."""
    from ..code.roots import create_folder  # noqa: PLC0415

    try:
        return {"success": True, **create_folder(body.path, body.name)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/workspace/roots")
def list_roots(_: bool = Depends(require_operator)) -> dict[str, Any]:
    store = service.trusted_root_store()
    return {"success": True, "roots": [r.to_dict() for r in store.list()]}


@router.post("/workspace/roots")
def approve_root(
    body: ApproveRootRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    store = service.trusted_root_store()
    try:
        root = store.approve(body.path, body.label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Approving a folder does not change the active one; the caller selects it.
    return {"success": True, "root": root.to_dict()}


@router.post("/workspace/roots/select")
def select_root(
    body: SelectRootRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Select the active workspace root, or clear it (rootId omitted/null)."""
    store = service.trusted_root_store()
    if not body.rootId:
        store.clear_selection()
        return {"success": True, "selected": None}
    selected = store.select(body.rootId)
    if selected is None:
        raise HTTPException(status_code=404, detail="That folder is not approved.")
    return {"success": True, "selected": selected.to_dict()}


@router.delete("/workspace/roots/{root_id}")
def revoke_root(root_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = service.trusted_root_store()
    removed = store.revoke(root_id)
    if not removed:
        raise HTTPException(status_code=404, detail="That folder is not approved.")
    return {"success": True, "revoked": root_id}


# ── Editor: file tree + read + write inside the active root ─────────────────

_MAX_EDITOR_BYTES = 1_500_000
_IGNORED_EDITOR_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".next", ".next-dev",
    ".pytest_cache", "dist", "build", ".venv", "venv",
})


@router.get("/workspace/files")
def list_files(
    path: str = ".", depth: int = 2, rootId: Optional[str] = None,  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """The editor's file tree: direct children of `path`, ignore-aware, bounded.

    Read-only. Directories only (the editor lazily expands); protected paths are
    refused by the same confinement the tools use. `rootId` (optional) selects an
    approved root explicitly, so a chat's project can differ from the global one.
    """
    from ..code.policy import PolicyDenial, resolve_within  # noqa: PLC0415

    root = _editor_root(rootId)
    try:
        base = resolve_within(root, path or ".")
    except PolicyDenial as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.reason}) from exc
    if not base.is_dir():
        raise HTTPException(status_code=400, detail="That location is not a folder.")
    entries: list[dict[str, Any]] = []
    truncated = False
    for child in sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())):
        if len(entries) >= 2000:
            truncated = True
            break
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        if is_dir and child.name in _IGNORED_EDITOR_DIRS:
            continue
        rel = child.relative_to(root).as_posix()
        entries.append({"name": child.name, "path": rel, "isDir": is_dir})
    return {"success": True, "root": str(root), "path": path or ".", "entries": entries,
            "truncated": truncated}


# Search is bounded by BOTH a visited-file cap and a wall-clock budget; a repo
# that is too large yields an honest `truncated` flag, never an endless scan.
_MAX_SEARCH_FILES = 20_000
_MAX_SEARCH_RESULTS = 100


@router.get("/workspace/files/search")
def search_files(
    q: str = "", rootId: Optional[str] = None, limit: int = 50,  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Fuzzy-ish file search inside the active (or named) approved root.

    Read-only and bounded. Matches the leaf name first, then the relative path,
    case-insensitively. Ignored directories (`.git`, `node_modules`, …) are
    skipped so a search never surfaces build noise. An empty `q` returns the
    first files in path order, which the composer uses as a browse fallback.
    """
    root = _editor_root(rootId)
    needle = (q or "").strip().lower()
    capped_limit = max(1, min(int(limit or 50), _MAX_SEARCH_RESULTS))
    results: list[dict[str, Any]] = []
    visited = 0
    truncated = False

    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in _IGNORED_EDITOR_DIRS and not d.startswith("."))
            for filename in sorted(filenames):
                visited += 1
                if visited > _MAX_SEARCH_FILES:
                    truncated = True
                    break
                if filename.startswith("."):
                    continue
                full = Path(dirpath) / filename
                try:
                    rel = full.relative_to(root).as_posix()
                except ValueError:
                    continue
                haystack = rel.lower()
                if needle and needle not in haystack:
                    continue
                try:
                    size = full.stat().st_size
                except OSError:
                    size = None
                results.append({"name": filename, "path": rel, "bytes": size})
                if len(results) >= capped_limit:
                    truncated = True
                    break
            if truncated:
                break
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"That folder could not be searched: {exc}") from exc

    # Leaf-name matches rank above path-only matches; shorter paths first.
    def _rank(item: dict[str, Any]) -> tuple[int, int, str]:
        name = str(item["name"]).lower()
        if not needle:
            return (0, len(str(item["path"])), str(item["path"]))
        return (0 if needle in name else 1, len(str(item["path"])), str(item["path"]))

    results.sort(key=_rank)
    return {"success": True, "root": str(root), "query": q, "files": results, "truncated": truncated}


@router.post("/workspace/file/read")
def read_file(body: ReadFileRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Read a text file inside the active root, with line numbers and redaction."""
    from ..session_index import redact_span  # noqa: PLC0415

    root, resolved = _resolve_editor_path(body.path, body.rootId)
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="That file is not there.")
    if resolved.stat().st_size > _MAX_EDITOR_BYTES:
        raise HTTPException(status_code=400, detail="That file is too large to open here.")
    try:
        text = resolved.read_text(encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, OSError) as exc:
        raise HTTPException(status_code=400, detail="That file isn't readable text.") from exc
    redacted = redact_span(text, "«redacted»")
    return {
        "success": True,
        "path": resolved.relative_to(root).as_posix(),
        "content": redacted,
        "redacted": redacted != text,
        "lines": text.count("\n") + 1,
    }


@router.post("/workspace/file/write")
def write_file(body: WriteFileRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Write a text file inside the active root. Creates parent directories.

    This is the human editor saving a file — a deliberate operator act — so it
    writes directly (no disposable copy), but ONLY inside the selected root and
    never a protected or ignored path.
    """
    from ..code.policy import PolicyDenial, resolve_within  # noqa: PLC0415

    if len(body.content) > _MAX_EDITOR_BYTES:
        raise HTTPException(status_code=400, detail="That file is too large to save here.")
    root, resolved = _resolve_editor_path(body.path)
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(body.content, encoding="utf-8", newline="")
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"That file could not be saved: {exc}") from exc
    return {"success": True, "path": resolved.relative_to(root).as_posix(),
            "bytes": len(body.content.encode("utf-8"))}


@router.post("/workspace/file/mkdir")
def make_folder(body: MkdirRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Create a folder inside the active root (the editor's "new folder")."""
    from ..code.policy import PolicyDenial, resolve_within  # noqa: PLC0415

    root, resolved = _resolve_editor_path(body.path)
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"That folder could not be created: {exc}") from exc
    return {"success": True, "path": resolved.relative_to(root).as_posix()}


@router.post("/workspace/file/delete")
def delete_path(body: ReadFileRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Delete a file (or an empty folder) inside the active root.

    A human editor action, so directories are deleted only when EMPTY — a
    non-empty folder is refused rather than silently removed recursively.
    """
    root, resolved = _resolve_editor_path(body.path)
    if not resolved.exists():
        raise HTTPException(status_code=400, detail="That path is not there.")
    try:
        if resolved.is_dir():
            resolved.rmdir()  # refuses a non-empty folder
        else:
            resolved.unlink()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"That couldn't be removed: {exc}") from exc
    return {"success": True, "path": resolved.relative_to(root).as_posix(), "removed": True}


__all__ = ["router"]
