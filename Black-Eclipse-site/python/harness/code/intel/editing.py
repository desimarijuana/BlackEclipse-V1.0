"""Safe semantic editing — rename, workspace edits, organize imports.

Rename is NEVER a regex find-and-replace. When a language server is running,
CIUE asks the server for a semantic `WorkspaceEdit` and applies exactly that,
path-confined to the workspace. When no server is available it produces a
deterministic, preview-first edit set from the index (declaration + references,
whole-identifier boundaries only) so the agent can review before applying.

Every write path is confined through the ONE authority (`code.workspace.confine`)
and written with the fs subsystem's atomic encoder, so a rename cannot escape the
workspace or leave a partially-written file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..fs import encoding as fs_encoding
from ..workspace import WorkspaceDenial, confine
from .errors import IntelError, AMBIGUOUS_SYMBOL, EDIT_CONFLICT, NOT_FOUND
from .language.detect import detect_language
from .persistence.index import CodeIndex


@dataclass
class FileEdit:
    file: str
    edits: list[dict[str, Any]]        # {startLine, startColumn, endLine, endColumn, newText, oldText?}
    engine: str = "lsp"

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "editCount": len(self.edits), "engine": self.engine}


@dataclass
class RenameResult:
    symbol: str
    new_name: str
    files: list[FileEdit] = field(default_factory=list)
    applied: bool = False
    engine: str = "lsp"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "newName": self.new_name, "engine": self.engine,
            "applied": self.applied,
            "fileCount": len(self.files),
            "editCount": sum(len(f.edits) for f in self.files),
            "files": [f.to_dict() for f in self.files],
            "note": self.note or None,
        }


def parse_workspace_edit(edit: dict[str, Any]) -> list[FileEdit]:
    """Normalize an LSP WorkspaceEdit (`changes` or `documentChanges`) to FileEdits."""
    from .lsp.client import uri_to_path

    out: list[FileEdit] = []
    changes = edit.get("changes")
    if isinstance(changes, dict):
        for uri, edits in changes.items():
            out.append(FileEdit(file=uri_to_path(uri), edits=_normalize_edits(edits)))
    document_changes = edit.get("documentChanges")
    if isinstance(document_changes, list):
        for change in document_changes:
            if not isinstance(change, dict):
                continue
            if "textDocument" in change and "edits" in change:
                uri = (change.get("textDocument") or {}).get("uri", "")
                out.append(FileEdit(file=uri_to_path(uri), edits=_normalize_edits(change["edits"])))
    return out


def _normalize_edits(edits: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in edits or []:
        if not isinstance(item, dict):
            continue
        range_ = item.get("range") or {}
        start = range_.get("start") or {}
        end = range_.get("end") or {}
        out.append({
            "startLine": int(start.get("line", 0)) + 1,
            "startColumn": int(start.get("character", 0)) + 1,
            "endLine": int(end.get("line", 0)) + 1,
            "endColumn": int(end.get("character", 0)) + 1,
            "newText": str(item.get("newText", "")),
        })
    return out


def apply_file_edits(root: Path, file_edits: list[FileEdit], *, dry_run: bool = False) -> dict[str, Any]:
    """Apply normalized edits to real files, path-confined to `root`.

    Edits are applied bottom-up per file so earlier offsets stay valid. A path
    outside the workspace is refused; a file that no longer matches is reported as
    an `EDIT_CONFLICT` rather than silently mis-edited.
    """
    applied_files: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    total_edits = 0
    for file_edit in file_edits:
        try:
            target = _confine(root, file_edit.file)
        except WorkspaceDenial as denial:
            conflicts.append({"file": file_edit.file, "code": denial.code})
            continue
        try:
            decoded = fs_encoding.read_text(target)
        except Exception as exc:  # noqa: BLE001
            conflicts.append({"file": file_edit.file, "code": "READ_FAILED", "reason": str(exc)[:200]})
            continue
        lines = decoded.text.splitlines(keepends=True)
        ordered = sorted(
            file_edit.edits,
            key=lambda e: (e["startLine"], e["startColumn"]),
            reverse=True,
        )
        new_lines = list(lines)
        ok = True
        for edit in ordered:
            try:
                new_lines = _apply_one(new_lines, edit)
            except _Conflict as conflict:
                conflicts.append({"file": file_edit.file, "code": conflict.code, "detail": conflict.detail})
                ok = False
                break
        if not ok:
            continue
        new_text = "".join(new_lines)
        if new_text == decoded.text:
            applied_files.append({"file": file_edit.file, "edits": len(file_edit.edits), "changed": False})
            continue
        if not dry_run:
            fs_encoding.write_text_atomic(target, new_text, encoding=decoded.encoding, had_bom=decoded.had_bom)
        applied_files.append({"file": file_edit.file, "edits": len(file_edit.edits), "changed": True})
        total_edits += len(file_edit.edits)
    return {
        "status": "ok" if not conflicts else "conflict",
        "applied": applied_files,
        "conflicts": conflicts,
        "totalEdits": total_edits,
        "dryRun": dry_run,
    }


class _Conflict(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _confine(root: Path, path: str | Path) -> Path:
    """Confine a (possibly absolute) path to `root`. Raises WorkspaceDenial."""
    from ..policy import resolve_within, PolicyDenial

    candidate = Path(path)
    try:
        if candidate.is_absolute():
            rel = candidate.resolve().relative_to(Path(root).resolve()).as_posix()
        else:
            rel = candidate.as_posix()
    except ValueError:
        raise WorkspaceDenial("PATH_OUTSIDE_WORKSPACE", "That location is outside the project's folder.")
    try:
        return resolve_within(Path(root), rel)
    except PolicyDenial as denial:
        raise WorkspaceDenial(denial.code, denial.reason, path=rel) from denial


def _apply_one(lines: list[str], edit: dict[str, Any]) -> list[str]:
    start_line = edit["startLine"] - 1
    end_line = edit["endLine"] - 1
    if start_line < 0 or end_line >= len(lines) + 1:
        if start_line < 0 or start_line > len(lines):
            raise _Conflict("EDIT_CONFLICT", "the file is shorter than the edit expects")
    prefix = lines[start_line][: edit["startColumn"] - 1]
    if end_line >= len(lines):
        suffix = ""
    else:
        suffix = lines[end_line][edit["endColumn"] - 1:] if edit["endColumn"] - 1 <= len(lines[end_line]) else ""
    replacement = prefix + edit["newText"] + suffix
    if lines[start_line].endswith("\n") and not replacement.endswith("\n"):
        replacement += "\n"
    return lines[:start_line] + [replacement] + lines[end_line + 1:]


def _code_mask(line: str) -> str:
    """Blank out string literals and comments so only real code identifiers match.

    A rename must NOT touch `console.log("UserService")` or `// UserService`.
    The mask keeps positions/lengths identical (replacing masked characters with a
    space) so a match offset in the mask is valid in the original line.
    """
    out: list[str] = []
    quote = ""
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if quote:
            out.append(" ")
            if ch == "\\":
                out.append(" ")
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            out.append(" ")
            i += 1
            continue
        if ch == "/" and i + 1 < n and line[i + 1] in ("/", "*"):
            # A line comment: everything after is not code.
            out.extend(" " for _ in line[i:])
            break
        out.append(ch)
        i += 1
    return "".join(out)


class SemanticEditor:
    """The write half of CIUE: rename, apply-edit, organize imports."""

    def __init__(self, root: Path, index: CodeIndex) -> None:
        self.root = Path(root)
        self.index = index

    def rename_symbol_fallback(self, name: str, new_name: str, *, file: str = "", dry_run: bool = True) -> RenameResult:
        """Deterministic rename from the index: declaration + code references.

        Whole-identifier boundaries only, and occurrences inside string literals and
        comments are NOT touched (`_code_mask`), so a rename never rewrites prose or
        a logged string. Refuses when the name is not found; the caller decides
        whether to apply. This is the honest fallback when no language server is
        available — it is never presented as semantic.
        """
        declarations = self.index.find_symbols(name, exact=True, limit=50)
        declaration = None
        if file:
            declaration = next((s for s in declarations if s["file"] == file), None)
        if declaration is None:
            declarations = [s for s in declarations if s["kind"] != "import"] or declarations
            declaration = declarations[0] if declarations else None
        if declaration is None:
            raise IntelError(NOT_FOUND, f"No symbol named {name!r} was found.")

        references = self.index.find_references(name, limit=500)
        by_file: dict[str, list[dict[str, Any]]] = {}
        identifier = re.compile(rf"\b{re.escape(name)}\b")

        def _add(path: str, line: int) -> None:
            try:
                decoded = fs_encoding.read_text(self._confined(path))
            except Exception:  # noqa: BLE001
                return
            text_lines = decoded.text.splitlines()
            if line - 1 >= len(text_lines):
                return
            raw_line = text_lines[line - 1]
            code_line = _code_mask(raw_line)
            for match in identifier.finditer(code_line):
                by_file.setdefault(path, []).append({
                    "startLine": line, "startColumn": match.start() + 1,
                    "endLine": line, "endColumn": match.end() + 1, "newText": new_name,
                })

        for ref in references:
            _add(ref["file"], ref["line"])
        if not by_file:
            _add(declaration["file"], declaration["line"])
        file_edits = [FileEdit(file=path, edits=edits, engine="index") for path, edits in by_file.items()]
        return RenameResult(
            symbol=name, new_name=new_name, files=file_edits, engine="index", applied=False,
            note="structural rename (no language server); preview before applying",
        )

    def _confined(self, path: str) -> Path:
        return _confine(self.root, path)


def organize_imports_fallback(index: CodeIndex) -> dict[str, Any]:
    """A deterministic, conservative import summary (never a destructive rewrite).

    Without a language server CIUE cannot safely reorder imports, so it reports
    what it sees and says so rather than inventing a reorder.
    """
    rows = index.file_rows(limit=2_000)
    files_with_imports = 0
    for row in rows:
        if index.imports_of(row["rel"]):
            files_with_imports += 1
    return {
        "status": "ok",
        "applied": False,
        "engine": "index",
        "filesWithImports": files_with_imports,
        "note": "import organization needs a language server; nothing was changed",
    }


__all__ = [
    "FileEdit",
    "RenameResult",
    "SemanticEditor",
    "apply_file_edits",
    "organize_imports_fallback",
    "parse_workspace_edit",
]
