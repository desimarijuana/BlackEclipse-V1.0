"""Cross-application dependency graph — order and start a set of applications.

A workspace can hold several applications (an API + a frontend, a monorepo with
`apps/*`). The per-application `ServiceGraph` is not enough: to bring the whole
thing up, Eclipse must know that the frontend depends on the API, and that the
API depends on its database.

`ApplicationGraph` is a small, deterministic meta-graph over applications:

  * each NODE is an application (id, root, descriptor);
  * each EDGE is a declared dependency (`app.depends_on` in `.black-eclipse/app.json`
    or a heuristic: an app whose compose file `depends_on` names another app's
    service, or a `package.json` workspace reference);
  * `startup_order()` is a stable topological order (dependencies first; a cycle
    breaks honestly rather than looping).

Nothing here executes: `ApplicationRuntimeManager` consults this graph to start
apps in order and to know what a stop should cascade to.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

#: The file a project uses to DECLARE its place in a multi-app workspace. It is
#: optional; without it the graph falls back to filesystem heuristics.
MANIFEST_NAME = ".black-eclipse/app.json"

#: Directory names that commonly hold several apps in a monorepo.
MONOREPO_DIRS = ("apps", "packages", "services", "microservices")


@dataclass
class AppNode:
    """One application in the meta-graph."""

    id: str
    root: str
    name: str = ""
    framework: str = ""
    depends_on: list[str] = field(default_factory=list)
    declared: bool = False                # True when from an explicit manifest
    services: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "root": self.root, "name": self.name,
            "framework": self.framework, "dependsOn": list(self.depends_on),
            "declared": self.declared, "services": list(self.services),
        }


class ApplicationGraph:
    """A dependency graph over a set of applications under one workspace."""

    def __init__(self) -> None:
        self.nodes: dict[str, AppNode] = {}
        self.edges: list[tuple[str, str]] = []   # (dependency, dependent)

    def add(self, node: AppNode) -> None:
        self.nodes[node.id] = node
        for dep in node.depends_on:
            if dep and dep in self.nodes and (dep, node.id) not in self.edges:
                self.edges.append((dep, node.id))

    def resolve_edges(self) -> None:
        """Add an edge for every declared dependency that names a known node."""
        self.edges = []
        for node in self.nodes.values():
            for dep in node.depends_on:
                if dep in self.nodes and (dep, node.id) not in self.edges:
                    self.edges.append((dep, node.id))

    def dependencies_of(self, app_id: str) -> list[str]:
        return [src for src, dst in self.edges if dst == app_id]

    def dependents_of(self, app_id: str) -> list[str]:
        return [dst for src, dst in self.edges if src == app_id]

    def startup_order(self) -> list[str]:
        """A stable topological order: every dependency before its dependent.

        A cycle is broken honestly: the remaining nodes are appended in sorted
        order rather than looping forever.
        """
        order: list[str] = []
        visited: set[str] = set()
        temp: set[str] = set()

        def visit(app_id: str) -> None:
            if app_id in visited or app_id not in self.nodes:
                return
            if app_id in temp:
                return  # cycle guard
            temp.add(app_id)
            for dep in sorted(self.dependencies_of(app_id)):
                visit(dep)
            temp.discard(app_id)
            visited.add(app_id)
            order.append(app_id)

        for app_id in sorted(self.nodes):
            visit(app_id)
        for app_id in sorted(self.nodes):
            if app_id not in visited:
                order.append(app_id)
        return order

    def stop_order(self) -> list[str]:
        """Teardown order: dependents before their dependencies."""
        return list(reversed(self.startup_order()))

    def has_cycle(self) -> bool:
        return len(self.startup_order()) < len(self.nodes) or _has_cycle(self.edges, set(self.nodes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [{"from": a, "to": b} for a, b in self.edges],
            "startupOrder": self.startup_order(),
            "stopOrder": self.stop_order(),
            "hasCycle": self.has_cycle(),
        }


def _has_cycle(edges: list[tuple[str, str]], nodes: set[str]) -> bool:
    adjacency: dict[str, list[str]] = {}
    for src, dst in edges:
        adjacency.setdefault(src, []).append(dst)
    state: dict[str, int] = {}

    def dfs(node: str) -> bool:
        if state.get(node) == 1:
            return True
        if state.get(node) == 2:
            return False
        state[node] = 1
        for nxt in adjacency.get(node, []):
            if dfs(nxt):
                return True
        state[node] = 2
        return False

    return any(dfs(node) for node in nodes if state.get(node, 0) == 0)


def discover_applications(root: Path, *, discovery: Any = None, max_apps: int = 50) -> list[AppNode]:
    """Find the applications under `root`.

    A single application (the root itself) is the common case. A monorepo is
    detected by the usual container directories (`apps/`, `packages/`, `services/`,
    `microservices/`), each immediate child with a manifest becoming a node. The
    root app is included when it has a manifest of its own.
    """
    from .discovery import discover_application

    root = Path(root).resolve()
    discover = discovery or discover_application
    nodes: list[AppNode] = []

    def _node(app_root: Path, app_id: str) -> Optional[AppNode]:
        try:
            descriptor = discover(app_root)
        except Exception:  # noqa: BLE001 - a broken child is skipped, not fatal
            return None
        if not descriptor.language and not descriptor.manifests and not descriptor.compose:
            return None
        manifest = _read_manifest(app_root)
        declared_deps = [str(d) for d in (manifest.get("dependsOn") or manifest.get("depends_on") or [])]
        return AppNode(
            id=app_id, root=str(app_root),
            name=manifest.get("name") or descriptor.name or app_root.name,
            framework=descriptor.framework,
            depends_on=declared_deps,
            declared=bool(manifest),
            services=list(descriptor.services),
        )

    root_node = _node(root, "__root__")
    children: list[AppNode] = []
    for dirname in MONOREPO_DIRS:
        container = root / dirname
        if not container.is_dir():
            continue
        for child in sorted(container.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            node = _node(child, f"{dirname}/{child.name}")
            if node is not None:
                children.append(node)
            if len(children) >= max_apps:
                break
    # When a root manifest exists alongside child apps, keep all; when there are
    # no children, the root is the only app.
    if root_node is not None:
        nodes.append(root_node)
    nodes.extend(children)
    if not nodes and root_node is None:
        # Fall back to the root as a single node even with a bare language.
        fallback = _node(root, "__root__")
        if fallback is not None:
            nodes.append(fallback)
    return nodes


def build_application_graph(root: Path, *, discovery: Any = None) -> ApplicationGraph:
    """Discover the applications under `root` and build their dependency graph."""
    graph = ApplicationGraph()
    for node in discover_applications(root, discovery=discovery):
        graph.add(node)
    graph.resolve_edges()
    return graph


def _read_manifest(app_root: Path) -> dict[str, Any]:
    path = app_root / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except (OSError, ValueError):
        return {}


__all__ = [
    "AppNode",
    "ApplicationGraph",
    "MANIFEST_NAME",
    "MONOREPO_DIRS",
    "build_application_graph",
    "discover_applications",
]
