"""Structural search — find code by shape (functions, classes, routes, imports).

Text search, structural search and semantic search are distinct and must not be
conflated:

  * **text** — `code.search.search_text` (ripgrep + fallback) finds exact text;
  * **structural** — this module finds code by SHAPE: every function, every class,
    every route, a signature matching a pattern. It runs on the AST engine, not on
    text matching;
  * **semantic** — LSP/index definitions/references/implementations.

`StructuralSearch` filters the index's symbols by kind, name pattern and language,
so a query like "all classes" or "routes with /users" is a structural question
answered without scanning source text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from .models import SYMBOL_KINDS
from .persistence.index import CodeIndex


@dataclass
class StructuralQuery:
    kinds: list[str]
    name_pattern: str = ""
    language: Optional[str] = None
    file: Optional[str] = None
    exact: bool = False
    limit: int = 200

    def to_dict(self) -> dict[str, Any]:
        return {
            "kinds": self.kinds, "namePattern": self.name_pattern,
            "language": self.language, "file": self.file, "exact": self.exact,
        }


class StructuralSearch:
    def __init__(self, index: CodeIndex) -> None:
        self.index = index

    def search(self, query: StructuralQuery) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        kinds = query.kinds or ["function", "class", "method", "interface", "type", "route"]
        pattern: Optional[re.Pattern[str]] = None
        if query.name_pattern:
            try:
                pattern = re.compile(query.name_pattern, re.IGNORECASE)
            except re.error:
                pattern = re.compile(re.escape(query.name_pattern), re.IGNORECASE)
        for kind in kinds:
            for symbol in self.index.find_symbols(
                query.name_pattern if query.exact else "",
                kind=kind, language=query.language, file=query.file, limit=query.limit,
            ):
                if pattern is not None and not query.exact and not pattern.search(symbol["name"]):
                    continue
                results.append(symbol)
                if len(results) >= query.limit:
                    break
            if len(results) >= query.limit:
                break
        return {
            "status": "ok", "engine": "ast+index", "query": query.to_dict(),
            "symbols": results, "count": len(results),
        }

    def find_routes(self, *, file: Optional[str] = None, pattern: str = "", limit: int = 200) -> dict[str, Any]:
        return self.search(StructuralQuery(kinds=["route"], name_pattern=pattern, file=file, limit=limit))

    def find_by_kind(self, kind: str, *, language: Optional[str] = None, limit: int = 200) -> dict[str, Any]:
        if kind not in SYMBOL_KINDS:
            return {"status": "ok", "engine": "ast+index", "symbols": [], "count": 0, "note": "unknown kind"}
        return self.search(StructuralQuery(kinds=[kind], language=language, limit=limit))


__all__ = ["StructuralQuery", "StructuralSearch"]
