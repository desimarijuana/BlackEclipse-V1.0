"""The dependency graph engine (file → file, module → module, service → service).

Built from the index's `dependencies` rows. It answers direct and transitive
dependency questions without a second parse, collapses cycles for the transitive
walk, and always names whether an edge is internal (a workspace file) or external
(a package import).
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Optional

from .models import CodeDependency
from .persistence.index import CodeIndex

MAX_TRANSITIVE = 500
MAX_DEPTH = 8


class DependencyGraph:
    """A directed dependency graph over one project's files."""

    def __init__(self, index: CodeIndex) -> None:
        self.index = index
        self._forward: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._reverse: dict[str, list[str]] = defaultdict(list)
        self._load()

    def _load(self) -> None:
        for row in self.index.file_rows(limit=100_000):
            source = row["rel"]
            for dep in self.index.dependencies_of(source):
                target = dep["target"]
                self._forward[source].append({
                    "target": target, "kind": dep["kind"],
                    "external": bool(dep["external"]), "line": dep["line"],
                })
                if not dep["external"]:
                    self._reverse[target].append(source)

    def rebuild(self) -> None:
        self._forward.clear()
        self._reverse.clear()
        self._load()

    # ── queries ───────────────────────────────────────────────────────────────
    def get_dependencies(self, rel: str) -> list[dict[str, Any]]:
        return list(self._forward.get(rel, []))

    def get_dependents(self, rel: str) -> list[str]:
        return sorted(set(self._reverse.get(rel, [])))

    def dependencies_for_symbol(self, symbol_id: str) -> list[dict[str, Any]]:
        row = self.index.symbol_by_id(symbol_id)
        if row is None:
            return []
        return self.get_dependencies(row["file"])

    def dependents_for_symbol(self, symbol_id: str) -> list[str]:
        row = self.index.symbol_by_id(symbol_id)
        if row is None:
            return []
        return self.get_dependents(row["file"])

    def transitive_dependencies(self, rel: str, *, max_depth: int = MAX_DEPTH) -> list[str]:
        """Every internal file reachable from `rel` (cycle-safe, bounded)."""
        seen: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(rel, 0)])
        while queue and len(seen) < MAX_TRANSITIVE:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for edge in self._forward.get(current, ()):
                if edge["external"]:
                    continue
                target = edge["target"]
                if target in seen or target == rel:
                    continue
                seen.add(target)
                queue.append((target, depth + 1))
        return sorted(seen)

    def to_dict(self, *, max_nodes: int = 2_000) -> dict[str, Any]:
        """A bounded node/edge graph for the `code_get_dependency_graph` tool."""
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for row in self.index.file_rows(limit=max_nodes):
            rel = row["rel"]
            outgoing = self._forward.get(rel, [])
            nodes.append({
                "id": rel, "language": row["language"],
                "symbols": int(row["symbols"]),
                "dependencies": len(outgoing),
                "dependents": len(self._reverse.get(rel, [])),
            })
            for edge in outgoing:
                if edge["external"]:
                    continue
                edges.append({"from": rel, "to": edge["target"], "kind": edge["kind"]})
        return {"nodes": nodes, "edges": edges[:20_000], "nodeCount": len(nodes), "edgeCount": len(edges)}


__all__ = ["DependencyGraph", "MAX_DEPTH", "MAX_TRANSITIVE"]
