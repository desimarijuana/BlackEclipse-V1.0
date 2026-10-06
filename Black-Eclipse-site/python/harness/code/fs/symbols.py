"""Symbol and reference search — AST where it exists, regex otherwise.

`extract_symbols` is language-dispatching and EXTENSIBLE: a language with a real
parser uses it (Python uses the stdlib `ast`, no dependency), every other
language falls back to a conservative regex extractor. Adding a language means
adding one function to `_EXTRACTORS`; nothing else changes.

`search_symbols` scans the workspace and returns symbol locations.
`find_references` finds usages of a symbol. When the workspace index is
available, references are answered from the index; otherwise a word-boundary
regex scan is used. The result always names the engine, so the agent knows
whether a hit is semantic or textual.
"""

from __future__ import annotations

import ast
import fnmatch
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from .. import policy
from . import errors as err
from . import resolver as res
from .context import FsContext

MAX_SYMBOL_RESULTS = 500
MAX_QUERY_CHARS = 200
MAX_FILE_BYTES = 2_000_000

# Extension → language tag.
_LANGUAGE_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".go": "go", ".rs": "rust", ".java": "java", ".rb": "ruby", ".php": "php",
    ".cs": "csharp", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
    ".json": "json", ".jsonc": "jsonc", ".toml": "toml",
}

_SYMBOL_KINDS = (
    "function", "method", "class", "interface", "type", "variable",
    "constant", "export", "import",
)


def detect_language(path: str | Path) -> str:
    return _LANGUAGE_BY_EXT.get(Path(path).suffix.lower(), "text")


@dataclass
class Symbol:
    name: str
    kind: str
    path: str
    line: int
    column: int = 1
    signature: str = ""
    exported: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind, "path": self.path,
            "line": self.line, "column": self.column, "signature": self.signature,
            "exported": self.exported,
        }


# ── extractors ──────────────────────────────────────────────────────────────


def _python_symbols(path: str, text: str, language: str = "python") -> list[Symbol]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _regex_symbols(path, text, "python")
    symbols: list[Symbol] = []

    def _decorators(node: ast.AST) -> str:
        names = []
        for deco in getattr(node, "decorator_list", []) or []:
            target = deco.func if isinstance(deco, ast.Call) else deco
            if isinstance(target, ast.Name):
                names.append("@" + target.id)
            elif isinstance(target, ast.Attribute):
                names.append("@" + target.attr)
        return " ".join(names)

    def _signature(node: ast.AST) -> str:
        try:
            args = [a.arg for a in getattr(node, "args", _EMPTY_ARGUMENTS).args]
        except Exception:  # noqa: BLE001
            args = []
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {getattr(node, 'name', '')}({', '.join(args)})"

    def _visit(node: ast.AST, class_depth: int) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "method" if class_depth else "function"
                deco = _decorators(child)
                signature = _signature(child)
                if deco:
                    signature = f"{deco} {signature}"
                symbols.append(Symbol(
                    name=child.name, kind=kind, path=path, line=child.lineno,
                    column=child.col_offset + 1, signature=signature,
                    exported=(not class_depth and not child.name.startswith("_")),
                ))
                _visit(child, class_depth)
            elif isinstance(child, ast.ClassDef):
                symbols.append(Symbol(
                    name=child.name, kind="class", path=path, line=child.lineno,
                    column=child.col_offset + 1, signature=f"class {child.name}",
                    exported=not child.name.startswith("_"),
                ))
                _visit(child, class_depth + 1)
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in child.names]
                for alias in child.names:
                    symbols.append(Symbol(
                        name=alias.asname or alias.name, kind="import", path=path,
                        line=child.lineno, column=child.col_offset + 1,
                        signature=f"import {' '.join(names)}",
                    ))
            elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                for target in targets:
                    for name in _assigned_names(target):
                        kind = "constant" if name.isupper() else "variable"
                        symbols.append(Symbol(
                            name=name, kind=kind, path=path, line=child.lineno,
                            column=child.col_offset + 1,
                            exported=not class_depth and not name.startswith("_"),
                        ))

    _visit(tree, 0)
    return symbols


_EMPTY_ARGUMENTS = ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[])


def _assigned_names(target: ast.AST) -> Iterator[str]:
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            yield from _assigned_names(element)


_TS_FUNC = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)", re.M)
_TS_CLASS = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)", re.M)
_TS_INTERFACE = re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)", re.M)
_TS_TYPE = re.compile(r"^\s*(?:export\s+)?type\s+(\w+)", re.M)
_TS_CONST = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)", re.M)
_TS_IMPORT = re.compile(r"^\s*import\s+(?:(\w+)|{([^}]*)}|\*\s+as\s+(\w+))", re.M)
_TS_EXPORT = re.compile(r"^\s*export\s+(?:default\s+)?", re.M)

# Brace-aware helpers for JS/TS. A line-level scanner is enough: it tracks brace
# depth so a method inside a class body is a `method`, a call at top level is not
# a symbol, and an arrow function assigned to a const IS.
_JS_CLASS_LINE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)(.*)$"
)
_JS_METHOD_LINE = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+|async\s+|get\s+|set\s+)*"
    r"([A-Za-z_$][\w$]*)\s*\("
)
_JS_ARROW_CONST = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*"
    r"(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
)
_JS_FUNC_LINE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)"
)


def _js_heritage(tail: str) -> str:
    """The ` extends X implements Y, Z` clause of a class line, or "".

    Bounded and string-aware so a class body on the same line cannot leak in.
    """
    tail = _strip_js_noise(tail)
    brace = tail.find("{")
    if brace != -1:
        tail = tail[:brace]
    parts: list[str] = []
    for match in re.finditer(r"(?:extends|implements)\s+([A-Za-z_$][\w$.,\s]*)", tail):
        clause = match.group(0).strip().split(None, 1)
        if len(clause) == 2:
            parts.append(f"{clause[0]} {clause[1].strip().rstrip(',')}")
    return (" " + " ".join(parts)) if parts else ""


def _strip_js_noise(line: str) -> str:
    """Remove string literals and line comments so brace/name detection is honest."""
    out: list[str] = []
    quote = ""
    index = 0
    while index < len(line):
        ch = line[index]
        if quote:
            if ch == "\\":
                index += 2
                continue
            if ch == quote:
                quote = ""
            index += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            index += 1
            continue
        if ch == "/" and index + 1 < len(line) and line[index + 1] == "/":
            break
        out.append(ch)
        index += 1
    return "".join(out)


def _js_ts_symbols(path: str, text: str, language: str = "typescript") -> list[Symbol]:
    """A brace-depth line scanner for JS/TS.

    It tracks brace depth so a `foo()` line inside a `class { ... }` body is a
    `method` (and a call at top level is not a symbol), and `const foo = () =>`
    at top level is a `function`. Deliberately conservative: it never guesses a
    name it did not see in declaration position.
    """
    symbols: list[Symbol] = []
    depth = 0
    class_depth: Optional[int] = None  # depth at which the current class body sits
    class_pending = False
    method_words = {
        "if", "for", "while", "switch", "catch", "return", "function", "typeof",
        "new", "do", "else", "try", "finally", "super", "this", "await", "yield",
    }

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_js_noise(raw_line)
        stripped = line.strip()
        if not stripped:
            continue
        exported = bool(_TS_EXPORT.match(line))

        class_match = _JS_CLASS_LINE.match(line)
        if class_match:
            heritage = _js_heritage(class_match.group(2) or "")
            symbols.append(Symbol(name=class_match.group(1), kind="class", path=path,
                                  line=line_no, exported=exported,
                                  signature=f"class {class_match.group(1)}{heritage}"))
            class_pending = True

        func_match = _JS_FUNC_LINE.match(line)
        if func_match:
            symbols.append(Symbol(name=func_match.group(1), kind="function", path=path,
                                  line=line_no, exported=exported))

        arrow_match = _JS_ARROW_CONST.match(line)
        if arrow_match:
            symbols.append(Symbol(name=arrow_match.group(1), kind="function", path=path,
                                  line=line_no, exported=exported))

        interface = re.match(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)", line)
        if interface:
            symbols.append(Symbol(name=interface.group(1), kind="interface", path=path,
                                  line=line_no, exported=exported))
        type_alias = re.match(r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*=", line)
        if type_alias:
            symbols.append(Symbol(name=type_alias.group(1), kind="type", path=path,
                                  line=line_no, exported=exported))

        in_class_body = class_depth is not None and depth == class_depth
        if in_class_body and not class_match and not func_match:
            method = _JS_METHOD_LINE.match(line)
            if method:
                name = method.group(1)
                if name == "constructor":
                    symbols.append(Symbol(name="constructor", kind="method", path=path, line=line_no))
                elif name not in method_words and not stripped.startswith(("//", "*", "@")):
                    symbols.append(Symbol(name=name, kind="method", path=path, line=line_no,
                                          signature=f"method {name}"))

        # Advance depth AFTER classification. A class body starts at the brace on
        # this line (or the next line that carries it).
        opens = line.count("{")
        closes = line.count("}")
        if class_pending and opens:
            class_depth = depth + 1
            class_pending = False
        depth += opens - closes
        if class_depth is not None and depth < class_depth:
            class_depth = None

    for match in _TS_IMPORT.finditer(text):
        name = next((g for g in match.groups() if g), "")
        if name:
            line = text.count("\n", 0, match.start()) + 1
            symbols.append(Symbol(name=name.strip().split(",")[0], kind="import", path=path, line=line))
    return symbols


def _regex_symbols(path: str, text: str, language: str) -> list[Symbol]:
    symbols: list[Symbol] = []

    def _add(pattern: re.Pattern[str], kind: str, *, exported: bool = False) -> None:
        for match in pattern.finditer(text):
            name = next((g for g in match.groups() if g), "")
            if not name:
                continue
            line = text.count("\n", 0, match.start()) + 1
            symbols.append(Symbol(name=name.strip(), kind=kind, path=path, line=line,
                                  exported=exported or bool(_TS_EXPORT.match(match.group(0)))))

    if language in ("typescript", "javascript"):
        return _js_ts_symbols(path, text, language)
    if language in ("go",):
        _add(re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(\w+)", re.M), "function")
        _add(re.compile(r"^\s*type\s+(\w+)\s+struct", re.M), "class")
        _add(re.compile(r"^\s*type\s+(\w+)\s+interface", re.M), "interface")
    elif language in ("rust",):
        _add(re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", re.M), "function")
        _add(re.compile(r"^\s*(?:pub\s+)?(?:struct|enum|union|trait)\s+(\w+)", re.M), "class")
        _add(re.compile(r"^\s*(?:pub\s+)?type\s+(\w+)", re.M), "type")
    elif language in ("java", "csharp"):
        _add(re.compile(r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|final\s+|abstract\s+)*(?:class|interface|enum|record|struct)\s+(\w+)", re.M), "class")
        _add(re.compile(r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|final\s+|abstract\s+|async\s+|override\s+)+[\w<>\[\],.\s]+\s+(\w+)\s*\(", re.M), "method")
    elif language in ("c", "cpp"):
        _add(re.compile(r"^\s*(?:[\w:*&<>\[\]\s]+?)\s+(\w+)\s*\([^;]*\)\s*\{", re.M), "function")
        _add(re.compile(r"^\s*(?:class|struct|enum)\s+(\w+)", re.M), "class")
    else:
        # A language-neutral fallback: functions, classes and top-level consts.
        _add(re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", re.M), "function")
        _add(re.compile(r"^\s*(?:public\s+|private\s+)?(?:static\s+)?(?:class|struct|enum|interface)\s+(\w+)", re.M), "class")
        _add(re.compile(r"^\s*(?:export\s+)?(?:const|static\s+final|let)\s+(\w+)", re.M), "variable")
    for match in _TS_IMPORT.finditer(text):
        name = next((g for g in match.groups() if g), "")
        if name:
            line = text.count("\n", 0, match.start()) + 1
            symbols.append(Symbol(name=name.strip().split(",")[0], kind="import", path=path, line=line))
    return symbols


_EXTRACTORS: dict[str, Callable[[str, str, str], list[Symbol]]] = {
    "python": _python_symbols,
}
_GENERIC = _regex_symbols


def extract_symbols(path: str, text: str, *, language: Optional[str] = None) -> list[Symbol]:
    lang = language or detect_language(path)
    extractor = _EXTRACTORS.get(lang)
    try:
        if extractor is not None:
            return extractor(path, text, lang)
        return _GENERIC(path, text, lang)
    except Exception:  # noqa: BLE001 - a parser failure must not break a search
        return []


# ── workspace scans ─────────────────────────────────────────────────────────


def _scan_files(ctx: FsContext, base: str, *, language: Optional[str], max_files: int = MAX_SYMBOL_RESULTS):
    from . import encoding as enc

    start = res.require_directory(ctx.ws, base or ".")
    seen = 0
    for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames
            if not policy.is_ignored(res.relative(ctx.ws, current / d))
            and not policy.is_protected(res.relative(ctx.ws, current / d))
        ]
        for name in filenames:
            full = current / name
            rel = res.relative(ctx.ws, full)
            if policy.is_ignored(rel) or policy.is_protected(rel):
                continue
            if language and detect_language(rel) != language:
                continue
            if detect_language(rel) == "text":
                continue
            try:
                if full.stat().st_size > MAX_FILE_BYTES or res.is_binary_file(full):
                    continue
                text = enc.read_text(full).text
            except (OSError, err.FsError):
                continue
            yield rel, text
            seen += 1
            if seen >= max_files:
                return


def search_symbols(
    ctx: FsContext,
    query: str,
    *,
    path: str = ".",
    kinds: Optional[list[str]] = None,
    language: Optional[str] = None,
    regex: bool = False,
    case_sensitive: bool = False,
    max_results: int = 100,
) -> dict[str, Any]:
    ctx.require("search", "")
    q = str(query or "")
    if not q:
        raise err.FsError(err.INVALID_PATH, "There was no symbol to look for.")
    if len(q) > MAX_QUERY_CHARS:
        raise err.FsError(err.TOO_LARGE, "That symbol name is too long.")
    bound = max(1, min(int(max_results), MAX_SYMBOL_RESULTS))
    wanted = set(kinds or [])
    try:
        pattern: Optional[re.Pattern[str]] = re.compile(
            q if regex else re.escape(q), 0 if case_sensitive else re.IGNORECASE,
        )
    except re.error as exc:
        raise err.FsError(err.SEARCH_FAILED, f"That pattern isn't valid: {exc}") from None
    results: list[dict[str, Any]] = []
    truncated = False
    for rel, text in _scan_files(ctx, path, language=language):
        for symbol in extract_symbols(rel, text, language=language):
            if wanted and symbol.kind not in wanted:
                continue
            if not pattern.search(symbol.name):
                continue
            results.append(symbol.to_dict())
            if len(results) >= bound:
                truncated = True
                break
        if truncated:
            break
    results.sort(key=lambda s: (s["path"], s["line"]))
    return {
        "status": "ok", "query": q, "engine": "ast+regex",
        "symbols": results, "count": len(results), "truncated": truncated,
    }


def find_references(
    ctx: FsContext,
    symbol: str,
    *,
    path: str = ".",
    glob: Optional[str] = None,
    max_results: int = 200,
    index: Any = None,
    root: Optional[Path] = None,
    refresh_index: bool = True,
) -> dict[str, Any]:
    """Find usages of a symbol. Index-backed when available, else a regex scan.

    The index is a CACHE, never an authority: before it is trusted it is brought
    up to date incrementally (`refresh_index`), so a file created or changed since
    the last indexing pass is never invisible — the §30 "no stale information"
    rule. A refresh failure falls through to the live scan.
    """
    ctx.require("search", "")
    name = str(symbol or "")
    if not name:
        raise err.FsError(err.INVALID_PATH, "There was no symbol to look for.")
    bound = max(1, min(int(max_results), MAX_SYMBOL_RESULTS))
    if index is not None and root is not None:
        try:
            if refresh_index and hasattr(index, "update"):
                # Incremental: only files whose mtime/size/hash changed are re-parsed.
                index.update()
            from_index = index.find_references(name, limit=bound)
            if from_index is not None:
                return {
                    "status": "ok", "symbol": name, "engine": "index",
                    "references": from_index, "count": len(from_index),
                    "truncated": len(from_index) >= bound,
                }
        except Exception:  # noqa: BLE001 - an index miss falls back to a scan
            pass
    word = re.compile(rf"\b{re.escape(name)}\b")
    from . import encoding as enc

    references: list[dict[str, Any]] = []
    truncated = False
    for dirpath, dirnames, filenames in os.walk(res.require_directory(ctx.ws, path or "."), followlinks=False):
        current = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames
            if not policy.is_ignored(res.relative(ctx.ws, current / d))
            and not policy.is_protected(res.relative(ctx.ws, current / d))
        ]
        for filename in filenames:
            full = current / filename
            rel = res.relative(ctx.ws, full)
            if policy.is_ignored(rel) or policy.is_protected(rel):
                continue
            if glob and not fnmatch.fnmatch(rel, glob) and not fnmatch.fnmatch(filename, glob):
                continue
            if detect_language(rel) == "text":
                continue
            try:
                if full.stat().st_size > MAX_FILE_BYTES or res.is_binary_file(full):
                    continue
                text = enc.read_text(full).text
            except (OSError, err.FsError):
                continue
            declaration_lines = {s.line for s in extract_symbols(rel, text) if s.name == name}
            for index_line, text_line in enumerate(text.splitlines()):
                if word.search(text_line):
                    references.append({
                        "path": rel, "line": index_line + 1,
                        "text": text_line.strip()[:200],
                        "definition": (index_line + 1) in declaration_lines,
                    })
                    if len(references) >= bound:
                        truncated = True
                        break
            if truncated:
                break
        if truncated:
            break
    return {
        "status": "ok", "symbol": name, "engine": "regex",
        "references": references, "count": len(references), "truncated": truncated,
    }


__all__ = [
    "MAX_SYMBOL_RESULTS",
    "Symbol",
    "detect_language",
    "extract_symbols",
    "find_references",
    "search_symbols",
]
