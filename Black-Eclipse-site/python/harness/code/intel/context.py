"""The agent context engine — the focused slice of code the agent actually needs.

`CodeContextEngine` prevents repository-wide context dumping. For a request
("fix the authentication bug") it:

  1. extracts candidate terms deterministically (no embeddings — the contract is
     explicit that deterministic code intelligence comes first);
  2. finds matching symbols in the index;
  3. expands each with its references, callers/callees and diagnostics;
  4. identifies the related tests;
  5. selects a bounded set of files and returns a COMPACT structured context.

The result is a small packet — file paths, symbol locations, a few focused source
ranges — never the whole repository and never a raw dump. Every entry is bounded.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from .language.detect import detect_language

MAX_CONTEXT_FILES = 12
MAX_CONTEXT_SYMBOLS = 40
MAX_CONTEXT_RANGES = 30
MAX_LINES_PER_RANGE = 40

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is",
    "are", "be", "fix", "bug", "issue", "error", "problem", "please", "make",
    "implement", "add", "change", "update", "where", "how", "does", "what",
    "this", "that", "it", "its", "when", "why", "find", "show", "help", "code",
    "file", "function", "class", "method",
})

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_LOWER_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_MIN_PREFIX = 4


def _expand_term(term: str) -> list[str]:
    """A term plus its camelCase/snake sub-tokens and usable prefixes.

    `AuthService` → auth, service, authservi…; `authentication` → authentication,
    authent, auth — so a query word reaches an identifier that only shares a prefix
    (`authentication` ↔ `AuthService`).
    """
    low = term.lower()
    out: set[str] = {low}
    # Split camelCase / snake_case into sub-words.
    for chunk in re.split(r"[^A-Za-z0-9]+", term):
        for sub in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+", chunk):
            if len(sub) >= 3:
                out.add(sub.lower())
    # A long word also contributes its shorter prefixes as probes (>= _MIN_PREFIX).
    for size in range(_MIN_PREFIX, min(len(low), 8)):
        prefix = low[:size]
        if prefix.isalpha():
            out.add(prefix)
    return [v for v in out if len(v) >= 3]


def _matches(term_variants: list[str], name: str) -> bool:
    """Whether a symbol/file name relates to a query term.

    Deterministic and prefix-aware: an exact substring, or a shared prefix of at
    least `_MIN_PREFIX` characters (`authentication` ↔ `AuthService` share `auth`).
    Bounded so it cannot match on a trivial 1-2 char overlap.
    """
    low = name.lower()
    for variant in term_variants:
        if variant in low or low in variant:
            return True
        # shared prefix
        limit = min(len(variant), len(low), 12)
        common = 0
        while common < limit and variant[common] == low[common]:
            common += 1
        if common >= _MIN_PREFIX:
            return True
    return False


def extract_terms(query: str, *, limit: int = 12) -> list[str]:
    """Deterministic candidate terms (identifiers and content words)."""
    seen: dict[str, None] = {}
    for match in _WORD.finditer(query or ""):
        word = match.group(0)
        lowered = word.lower()
        if lowered in _STOPWORDS:
            continue
        if len(lowered) < 3:
            continue
        seen[word] = None
    return list(seen)[:limit]


class CodeContextEngine:
    def __init__(self, manager: Any) -> None:
        self.manager = manager

    def select(self, query: str, *, max_files: int = MAX_CONTEXT_FILES,
               max_symbols: int = MAX_CONTEXT_SYMBOLS) -> dict[str, Any]:
        terms = extract_terms(query)
        variants: list[str] = []
        for term in terms:
            variants.extend(_expand_term(term))
        matched: dict[str, dict[str, Any]] = {}
        for term in terms:
            # Search each term AND its sub-tokens so an identifier like `AuthService`
            # is reachable from the word "authentication".
            for probe in _expand_term(term):
                for symbol in self.manager.index.find_symbols(probe, limit=30):
                    if _matches([probe, *variants], symbol["name"]):
                        matched.setdefault(symbol["id"], symbol)
            for symbol in self.manager.index.find_symbols(term, limit=30):
                matched.setdefault(symbol["id"], symbol)
        matched = {k: v for k, v in matched.items() if _matches(variants, v["name"])}
        # Also allow a file-path match to seed symbol selection for a term.
        for row in self.manager.index.file_rows(limit=10_000):
            if any(v in row["rel"].lower() for v in variants if len(v) >= _MIN_PREFIX):
                for symbol in self.manager.index.find_symbols("", file=row["rel"], limit=40):
                    matched.setdefault(symbol["id"], symbol)
            if len(matched) >= max_symbols * 2:
                break

        symbols = list(matched.values())
        file_scores: dict[str, int] = {}
        for symbol in symbols:
            file_scores[symbol["file"]] = file_scores.get(symbol["file"], 0) + 1
        # Also score files whose path relates to a term (prefix-aware), and score
        # symbol files by the relevance of the matched name.
        for row in self.manager.index.file_rows(limit=5_000):
            if any(v in row["rel"].lower() for v in variants if len(v) >= _MIN_PREFIX):
                file_scores[row["rel"]] = file_scores.get(row["rel"], 0) + 2
        for symbol in symbols:
            if _matches(variants, symbol["name"]):
                file_scores[symbol["file"]] = file_scores.get(symbol["file"], 0) + 1

        tests: set[str] = set()
        for symbol in symbols[:10]:
            related = find_related_tests(self.manager, symbol=symbol["name"])
            for test in related.get("tests", []):
                tests.add(test["file"])
                file_scores[test["file"]] = file_scores.get(test["file"], 0) + 1

        ranked_files = sorted(file_scores, key=lambda f: (-file_scores[f], f))[:max_files]
        selected_symbols = [s for s in symbols if s["file"] in ranked_files][:max_symbols]

        ranges: list[dict[str, Any]] = []
        for symbol in selected_symbols:
            if len(ranges) >= MAX_CONTEXT_RANGES:
                break
            ranges.append({
                "file": symbol["file"], "line": symbol["line"],
                "kind": symbol["kind"], "name": symbol["name"],
                "preview": self.manager._line_context(symbol["file"], symbol["line"]),
            })
        diagnostics = []
        for rel in ranked_files:
            try:
                cached = self.manager.diagnostics.cached(rel)
            except Exception:  # noqa: BLE001
                cached = []
            diagnostics.extend({"file": rel, **d.to_dict()} for d in cached[:10])

        return {
            "status": "ok",
            "engine": "context",
            "query": query,
            "terms": terms,
            "files": ranked_files,
            "fileCount": len(ranked_files),
            "symbols": [
                {"name": s["name"], "kind": s["kind"], "file": s["file"],
                 "line": s["line"], "signature": s.get("signature", "")}
                for s in selected_symbols
            ],
            "symbolCount": len(selected_symbols),
            "ranges": ranges,
            "diagnostics": diagnostics[:40],
            "tests": sorted(tests)[:12],
            "callPaths": self._call_paths(selected_symbols[:8]),
        }

    def _call_paths(self, symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
        paths: list[dict[str, Any]] = []
        for symbol in symbols:
            callers = self.manager.index.callers_of(symbol["name"])[:3]
            callees = self.manager.index.callees_of(symbol["name"])[:3]
            if callers or callees:
                paths.append({
                    "symbol": symbol["name"],
                    "callers": [c["caller_name"] or c["caller"] for c in callers],
                    "callees": [c["callee_name"] or c["callee"] for c in callees],
                })
        return paths[:10]


def find_related_tests(manager: Any, *, symbol: Optional[str] = None, file: Optional[str] = None) -> dict[str, Any]:
    """Deterministic related-test discovery: a test imports or names the symbol/file.

    Not a test runner — it identifies WHICH tests are relevant so the agent can run
    them through the existing terminal subsystem. Conventional test paths
    (`test_*.py`, `*.test.ts`, `*_test.go`, `tests/`, `__tests__/`) plus a
    dependency/reference match.
    """
    names: list[str] = []
    if symbol:
        names.append(symbol)
        candidates = manager._resolve_symbols(symbol)
        if candidates:
            file = file or candidates[0]["file"]
    if file:
        names.append(Path(file).stem)

    tests: dict[str, dict[str, Any]] = {}
    for row in manager.index.file_rows(limit=10_000):
        rel = row["rel"]
        if not _looks_like_test(rel):
            continue
        if file and _same_area(rel, file):
            tests[rel] = {"file": rel, "reason": "same area"}
            continue
        for name in names:
            if not name:
                continue
            if manager.index.find_references(name, limit=5) and any(
                ref["file"] == rel for ref in manager.index.find_references(name, limit=200)
            ):
                tests[rel] = {"file": rel, "reason": f"references {name}"}
                break
    return {"status": "ok", "engine": "index", "symbol": symbol, "file": file,
            "tests": list(tests.values())[:20], "count": len(tests)}


def _looks_like_test(rel: str) -> bool:
    lowered = rel.lower()
    name = Path(rel).name.lower()
    return (
        name.startswith("test_") or "_test." in name or name.endswith(".test.ts")
        or name.endswith(".test.tsx") or name.endswith(".test.js")
        or name.endswith(".spec.ts") or name.endswith(".spec.js")
        or "/tests/" in f"/{lowered}" or "/__tests__/" in f"/{lowered}"
        or lowered.startswith("tests/") or lowered.startswith("test/")
    )


def _same_area(test_rel: str, source_rel: str) -> bool:
    source_dir = str(Path(source_rel).parent)
    test_dir = str(Path(test_rel).parent)
    source_stem = Path(source_rel).stem.replace(".test", "").replace("_test", "")
    test_stem = Path(test_rel).stem.replace("test_", "").replace(".test", "").replace("_test", "")
    if source_stem and source_stem.lower() in Path(test_rel).name.lower():
        return True
    # A sibling tests/ directory next to the source package.
    return bool(source_dir) and (source_dir in test_dir or Path(source_dir).name in test_dir)


__all__ = [
    "CodeContextEngine",
    "extract_terms",
    "find_related_tests",
]
