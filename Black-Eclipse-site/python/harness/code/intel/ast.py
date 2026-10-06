"""The AST engine — deterministic structure extraction, tree-sitter-aware.

The AST engine is the structural understanding layer. For each file it produces
the unified `CodeSymbol`/`CodeImport`/`CodeDependency` models. It prefers a real
parser where one exists:

  * Python      — the stdlib `ast` module (always available, no dependency);
  * JS/TS       — tree-sitter when installed, else the brace-depth scanner that
                   already lives in `code/fs/symbols.py`;
  * Go/Rust/…   — tree-sitter when installed, else targeted regex patterns.

Crucially, the AST engine does NOT re-implement the per-language extractors that
already exist. It DELEGATES to `code/fs/symbols.extract_symbols` (the reviewed,
extensible extractor table) and normalizes its output into `CodeSymbol`. When
tree-sitter is available it augments the result with precise end positions and
extra kinds. One symbol contract, one source of truth for regex parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..fs import symbols as fs_symbols
from .errors import IntelError, PARSE_FAILED
from .language.detect import detect_language
from .models import (
    CodeDependency,
    CodeImport,
    CodeSymbol,
    make_symbol_id,
)
from .treesitter import TreeSitterEngine

MAX_SYMBOLS_PER_FILE = 4_000


@dataclass
class ParsedFile:
    path: str
    language: str
    symbols: list[CodeSymbol]
    imports: list[CodeImport]
    exports: list[CodeSymbol]
    dependencies: list[CodeDependency]
    routes: list[CodeSymbol]
    models: list[CodeSymbol]
    engine: str
    line_count: int
    error: str = ""

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        return {
            "path": self.path, "language": self.language, "engine": self.engine,
            "lines": self.line_count,
            "symbols": [s.to_dict(compact=compact) for s in self.symbols],
            "imports": [i.to_dict() for i in self.imports],
            "exports": [s.name for s in self.exports],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "routes": [s.name for s in self.routes],
            "models": [s.name for s in self.models],
            "error": self.error or None,
        }


# ── Route / model heuristics (framework-aware, conservative) ────────────────

_ROUTE_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "python": (
        re.compile(r"@(?:app|router|bp|api)\.(get|post|put|delete|patch|route)\(\s*[\"']([^\"']+)"),
        re.compile(r"@(?:app|router)\.(websocket)\(\s*[\"']([^\"']+)"),
    ),
    "typescript": (
        re.compile(r"\b(?:app|router)\.(get|post|put|delete|patch|all)\(\s*['\"`]([^'\"`]+)"),
    ),
    "javascript": (
        re.compile(r"\b(?:app|router)\.(get|post|put|delete|patch|all)\(\s*['\"`]([^'\"`]+)"),
    ),
    "java": (
        re.compile(r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|RequestMapping)\(\s*[\"']?([^\"')]*)"),
    ),
}

_MODEL_PATTERNS: dict[str, re.Pattern[str]] = {
    "python": re.compile(r"^class\s+(\w+)\s*\(([^)]*)\)", re.M),
    "typescript": re.compile(r"^(?:export\s+)?(?:class|interface)\s+(\w+)", re.M),
}

_DB_MODEL_HINT = re.compile(r"(Model|Base|Schema|Entity)\b")


class ASTEngine:
    """Structural parsing for one project. Stateless; safe to share."""

    def __init__(self, project_id: str, *, prefer_treesitter: bool = True, root: Optional[Path] = None) -> None:
        self.project_id = project_id
        self.prefer_treesitter = prefer_treesitter
        self.root = Path(root) if root else None
        self._ts_cache: dict[str, TreeSitterEngine] = {}

    def _treesitter(self, language: str) -> Optional[TreeSitterEngine]:
        if not self.prefer_treesitter:
            return None
        engine = self._ts_cache.get(language)
        if engine is None:
            engine = TreeSitterEngine(language)
            self._ts_cache[language] = engine
        return engine if engine.available else None

    def parse_file(self, rel_path: str, text: str) -> ParsedFile:
        language = detect_language(rel_path)
        lines = text.count("\n") + 1
        try:
            fs_symbols_out = fs_symbols.extract_symbols(rel_path, text, language=language)
        except Exception as exc:  # noqa: BLE001 - a parser failure is data
            return ParsedFile(
                path=rel_path, language=language, symbols=[], imports=[], exports=[],
                dependencies=[], routes=[], models=[], engine="regex",
                line_count=lines, error=f"parse failed: {exc}",
            )

        engine = "ast+regex" if language == "python" else "regex"
        ts = self._treesitter(language)
        ts_spans: dict[str, tuple[int, int, int]] = {}
        if ts is not None:
            try:
                for node in ts.extract_symbols(text):
                    ts_spans[str(node.get("name", ""))] = (
                        int(node.get("startLine", 0)), int(node.get("endLine", 0)),
                        int(node.get("startColumn", 1)),
                    )
                engine = "tree-sitter"
            except Exception:  # noqa: BLE001 - tree-sitter is best-effort
                ts = None

        symbols: list[CodeSymbol] = []
        imports: list[CodeImport] = []
        exports: list[CodeSymbol] = []
        for raw in fs_symbols_out[:MAX_SYMBOLS_PER_FILE]:
            kind = _normalize_kind(raw.kind)
            symbol = CodeSymbol(
                id=make_symbol_id(self.project_id, rel_path, raw.line, raw.column, raw.name),
                name=raw.name, kind=kind, file=rel_path, line=raw.line, column=raw.column,
                language=language, project_id=self.project_id,
                signature=raw.signature or "", exported=bool(raw.exported),
                qualified_name=raw.name,
                engine=engine,
            )
            span = ts_spans.get(raw.name)
            if span and span[0]:
                symbol.end_line = span[1]
            symbols.append(symbol)
            if raw.kind == "import":
                imports.append(CodeImport(module=raw.name, file=rel_path, line=raw.line))
            if raw.exported:
                exports.append(symbol)

        routes = self._extract_routes(rel_path, text, language)
        models = self._extract_models(rel_path, text, language, symbols)
        dependencies = self.extract_dependencies(rel_path, text, language)
        return ParsedFile(
            path=rel_path, language=language, symbols=symbols, imports=imports,
            exports=exports, dependencies=dependencies, routes=routes, models=models,
            engine=engine, line_count=lines,
        )

    def extract_symbols(self, rel_path: str, text: str) -> list[CodeSymbol]:
        return self.parse_file(rel_path, text).symbols

    def extract_imports(self, rel_path: str, text: str) -> list[CodeImport]:
        return self.parse_file(rel_path, text).imports

    def extract_exports(self, rel_path: str, text: str) -> list[CodeSymbol]:
        return self.parse_file(rel_path, text).exports

    def extract_functions(self, rel_path: str, text: str) -> list[CodeSymbol]:
        return [s for s in self.parse_file(rel_path, text).symbols if s.kind in ("function", "method")]

    def extract_classes(self, rel_path: str, text: str) -> list[CodeSymbol]:
        return [s for s in self.parse_file(rel_path, text).symbols if s.kind in ("class", "interface")]

    def extract_types(self, rel_path: str, text: str) -> list[CodeSymbol]:
        return [s for s in self.parse_file(rel_path, text).symbols if s.kind in ("type", "interface", "enum")]

    def extract_routes(self, rel_path: str, text: str) -> list[CodeSymbol]:
        return self._extract_routes(rel_path, text, detect_language(rel_path))

    def extract_database_models(self, rel_path: str, text: str) -> list[CodeSymbol]:
        return self._extract_models(rel_path, text, detect_language(rel_path), [])

    def _extract_routes(self, rel_path: str, text: str, language: str) -> list[CodeSymbol]:
        out: list[CodeSymbol] = []
        for pattern in _ROUTE_PATTERNS.get(language, ()):
            for match in pattern.finditer(text):
                groups = match.groups()
                path = groups[-1] if groups else ""
                method = groups[0].upper() if len(groups) > 1 else "ROUTE"
                line = text.count("\n", 0, match.start()) + 1
                name = f"{method} {path}".strip()
                out.append(CodeSymbol(
                    id=make_symbol_id(self.project_id, rel_path, line, 1, name),
                    name=name, kind="route", file=rel_path, line=line, language=language,
                    project_id=self.project_id, engine="regex",
                ))
        return out[:200]

    def _extract_models(
        self, rel_path: str, text: str, language: str, symbols: list[CodeSymbol],
    ) -> list[CodeSymbol]:
        out: list[CodeSymbol] = []
        if language in _MODEL_PATTERNS:
            if language == "python":
                pattern = _MODEL_PATTERNS["python"]
                for match in pattern.finditer(text):
                    base = match.group(2) or ""
                    if _DB_MODEL_HINT.search(base):
                        line = text.count("\n", 0, match.start()) + 1
                        out.append(CodeSymbol(
                            id=make_symbol_id(self.project_id, rel_path, line, 1, match.group(1)),
                            name=match.group(1), kind="model", file=rel_path, line=line,
                            language=language, project_id=self.project_id,
                            signature=f"class {match.group(1)}({base.strip()})", engine="regex",
                        ))
        return out

    # ── dependency extraction (import resolution) ──────────────────────────────
    def extract_dependencies(self, rel_path: str, text: str, language: str) -> list[CodeDependency]:
        out = self.dependencies(rel_path, text, language)
        return out

    def dependencies(self, rel_path: str, text: str, language: str) -> list[CodeDependency]:
        """Import targets for one file, resolved to workspace files when possible."""
        raw_imports = self._raw_import_targets(text, language)
        out: list[CodeDependency] = []
        for module, line, relative in raw_imports:
            resolved = self._resolve_import(rel_path, module, language, relative)
            out.append(CodeDependency(
                source=rel_path, target=resolved or module,
                kind="import", external=resolved is None, line=line,
            ))
        return out

    def _raw_import_targets(self, text: str, language: str) -> list[tuple[str, int, bool]]:
        out: list[tuple[str, int, bool]] = []
        if language == "python":
            for match in re.finditer(r"^\s*from\s+([.\w]+)\s+import\b", text, re.M):
                module = match.group(1)
                out.append((module, text.count("\n", 0, match.start()) + 1, module.startswith(".")))
            for match in re.finditer(r"^\s*import\s+([.\w]+)", text, re.M):
                out.append((match.group(1), text.count("\n", 0, match.start()) + 1, False))
        elif language in ("typescript", "javascript"):
            for match in re.finditer(r"""^\s*import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]""", text, re.M):
                module = match.group(1)
                out.append((module, text.count("\n", 0, match.start()) + 1, module.startswith(".")))
        elif language == "go":
            for match in re.finditer(r'"([\w./\-]+)"', text):
                out.append((match.group(1), text.count("\n", 0, match.start()) + 1, False))
        elif language == "rust":
            for match in re.finditer(r"^\s*use\s+([\w:]+)", text, re.M):
                out.append((match.group(1).replace("::", "/"), text.count("\n", 0, match.start()) + 1, False))
        elif language == "java":
            for match in re.finditer(r"^\s*import\s+(?:static\s+)?([\w.]+)", text, re.M):
                out.append((match.group(1).replace(".", "/"), text.count("\n", 0, match.start()) + 1, False))
        return out

    def _resolve_import(self, rel_path: str, module: str, language: str, relative: bool) -> Optional[str]:
        """Resolve an import to a workspace-relative file, or None (external).

        Only LOCAL (relative or in-tree) imports resolve. A package import
        (`react`, `fastapi`) is external by construction and never resolved.
        """
        if self.root is None:
            return None
        base = Path(rel_path).parent
        candidates: list[str] = []
        if relative:
            target = self._resolve_relative(base, module, language)
            if target is None:
                return None
            candidates = _module_candidates(target, language)
        else:
            if language in ("typescript", "javascript"):
                if not (module.startswith(".") or module.startswith("/")):
                    # A bare specifier is external unless it is a known tsconfig path
                    # alias we cannot see here — external is the honest answer.
                    return None
            elif language == "python":
                target = module.replace(".", "/")
                candidates = _module_candidates(target, language)
            else:
                return None
        for candidate in candidates:
            try:
                if (self.root / candidate).is_file():
                    return candidate
            except OSError:
                continue
        return None

    def _resolve_relative(self, base: Path, module: str, language: str) -> Optional[str]:
        """Resolve a relative JS/TS import (`./x`, `../pkg/y`) to a base path.

        Each leading `.` consumes one directory level (`.` → same dir, `..` →
        parent); the remaining segments are appended. The extension is added by
        `_module_candidates` (or `/index.ts` for a bare directory).
        """
        parts = module.split("/")
        segments = [p for p in parts if p in (".", "..")]
        rest = [p for p in parts if p not in (".", "..")]
        target = Path(base)
        for segment in segments:
            target = target.parent if segment == ".." else target
        return (target / "/".join(rest)).as_posix()


def _module_candidates(target: str, language: str) -> list[str]:
    if language in ("typescript", "javascript"):
        return [
            target + ".ts", target + ".tsx", target + ".js", target + ".jsx",
            target + "/index.ts", target + "/index.js",
        ]
    if language == "python":
        return [target + ".py", target + "/__init__.py", target]
    return [target]


def _normalize_kind(kind: str) -> str:
    return {
        "function": "function", "method": "method", "class": "class",
        "interface": "interface", "type": "type", "variable": "variable",
        "constant": "constant", "export": "export", "import": "import",
    }.get(kind, "unknown")


__all__ = ["ASTEngine", "MAX_SYMBOLS_PER_FILE", "ParsedFile"]
