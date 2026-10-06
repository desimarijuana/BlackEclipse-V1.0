"""The diagnostics engine — syntax, type and lint diagnostics, normalized.

Three sources, one normalized `CodeDiagnostic` vocabulary:

  1. **LSP** (`textDocument/publishDiagnostics` pushed, or `textDocument/diagnostic`
     pulled) — the richest, when a language server is running;
  2. **Structural** (`code/fs/verify.validate_syntax`) — a cheap, deterministic
     syntax check that always works, even with no language server;
  3. **Indexed** — the last published LSP diagnostics persisted for a file, so the
     diagnostic feedback loop survives across runs.

The engine is the seam the edit→diagnostics→fix loop reads: after a change the
manager re-runs the structural check immediately and (best-effort) the LSP check,
records the result in the index, and returns it. It never fabricates a clean bill
of health — "no diagnostics available" is distinct from "no problems".
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from ..fs import verify as fs_verify
from .language.detect import detect_language
from .models import CodeDiagnostic, severity_from_lsp
from .persistence.index import CodeIndex


def structural_diagnostics(rel_path: str, text: str, *, language: Optional[str] = None) -> list[CodeDiagnostic]:
    """A deterministic syntax check for one file. Never raises."""
    lang = language or detect_language(rel_path)
    try:
        result = fs_verify.validate_syntax(text, language=lang, path=rel_path)
    except Exception:  # noqa: BLE001 - a checker failure is not a diagnostic
        return []
    if getattr(result, "valid", True):
        return []
    return [CodeDiagnostic(
        message=str(getattr(result, "error", "") or "syntax error"),
        severity="error", file=rel_path, line=int(getattr(result, "line", 0) or 1),
        column=1, source=str(getattr(result, "checker", "") or "syntax"), code="SYNTAX",
    )]


def normalize_lsp_diagnostics(rel_path: str, raw: Iterable[dict[str, Any]]) -> list[CodeDiagnostic]:
    """Normalize LSP `Diagnostic[]` into the unified model."""
    out: list[CodeDiagnostic] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        start = (item.get("range") or {}).get("start") or {}
        end = (item.get("range") or {}).get("end") or {}
        related = []
        for rel in item.get("relatedInformation") or []:
            loc = (rel or {}).get("location") or {}
            if isinstance(loc, dict):
                related.append({
                    "message": str((rel or {}).get("message", ""))[:300],
                    "uri": loc.get("uri", ""),
                })
        code = item.get("code")
        out.append(CodeDiagnostic(
            message=str(item.get("message", "")),
            severity=severity_from_lsp(item.get("severity")),
            file=rel_path,
            line=int(start.get("line", 0)) + 1,
            column=int(start.get("character", 0)) + 1,
            end_line=int(end.get("line", 0)) + 1,
            end_column=int(end.get("character", 0)) + 1,
            source=str(item.get("source", "lsp")),
            code=str(code.get("value") if isinstance(code, dict) else (code or "")),
            related=related,
        ))
    return out


def summarize(diagnostics: list[CodeDiagnostic]) -> dict[str, int]:
    counts = {"error": 0, "warning": 0, "information": 0, "hint": 0}
    for diag in diagnostics:
        counts[diag.severity] = counts.get(diag.severity, 0) + 1
    return counts


class DiagnosticsEngine:
    """Collect, normalize and persist diagnostics for a project."""

    def __init__(self, index: CodeIndex) -> None:
        self.index = index

    def for_file(self, rel_path: str, text: str, *, lsp: Optional[list[dict[str, Any]]] = None) -> list[CodeDiagnostic]:
        """Merge structural + (optional) LSP diagnostics for one file, deduped."""
        diagnostics: list[CodeDiagnostic] = []
        if lsp:
            diagnostics.extend(normalize_lsp_diagnostics(rel_path, lsp))
        # Always add the structural check: it catches a broken file the server
        # has not published for yet (e.g. right after an edit).
        diagnostics.extend(structural_diagnostics(rel_path, text))
        return _dedupe(diagnostics)

    def record(self, rel_path: str, diagnostics: list[CodeDiagnostic]) -> None:
        try:
            self.index.set_diagnostics(rel_path, [d.to_dict() for d in diagnostics])
        except Exception:  # noqa: BLE001 - persistence is best-effort
            pass

    def cached(self, rel_path: str) -> list[CodeDiagnostic]:
        from .models import CodeDiagnostic as _D

        out: list[_D] = []
        for row in self.index.diagnostics_for(rel_path):
            out.append(_D(
                message=row["message"], severity=row["severity"], file=row["rel"],
                line=row["line"], column=row["col"], source=row["source"], code=row["code"],
            ))
        return out


def _dedupe(diagnostics: list[CodeDiagnostic]) -> list[CodeDiagnostic]:
    seen: set[tuple[str, int, int, str]] = set()
    out: list[CodeDiagnostic] = []
    for diag in diagnostics:
        key = (diag.file, diag.line, diag.column, diag.message[:60])
        if key in seen:
            continue
        seen.add(key)
        out.append(diag)
    return out


__all__ = [
    "DiagnosticsEngine",
    "normalize_lsp_diagnostics",
    "structural_diagnostics",
    "summarize",
]
