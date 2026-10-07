"""Cross-application graph + workspace start/stop — tests.

A temporary monorepo with two apps whose dependency is declared in
`.black-eclipse/app.json`, using a fake discovery and a fake runtime manager so no
real process starts. The topological order, the honest cycle handling and the
ordered start/stop are asserted directly.
"""

from __future__ import annotations

from pathlib import Path

from harness.execution.application.app_graph import (
    AppNode,
    ApplicationGraph,
    build_application_graph,
)
from harness.execution.application.models import ApplicationState
from harness.execution.application.workspace_ops import start_workspace, stop_workspace
from harness.execution.application.models import RuntimeHandle


def test_graph_orders_dependencies_first():
    graph = ApplicationGraph()
    graph.add(AppNode(id="web", root="/w", depends_on=["api"]))
    graph.add(AppNode(id="api", root="/a", depends_on=["db"]))
    graph.add(AppNode(id="db", root="/d"))
    graph.resolve_edges()
    order = graph.startup_order()
    assert order.index("db") < order.index("api") < order.index("web")
    assert graph.stop_order() == list(reversed(order))
    assert graph.has_cycle() is False


def test_graph_breaks_a_cycle_honestly():
    graph = ApplicationGraph()
    graph.add(AppNode(id="a", root="/a", depends_on=["b"]))
    graph.add(AppNode(id="b", root="/b", depends_on=["a"]))
    graph.resolve_edges()
    order = graph.startup_order()
    assert sorted(order) == ["a", "b"]  # both present, no infinite loop
    assert graph.has_cycle() is True


def test_build_graph_from_a_declared_monorepo(tmp_path):
    from harness.execution.application.discovery import discover_application

    for name, deps in (("api", []), ("web", ["api"])):
        app = tmp_path / "apps" / name
        app.mkdir(parents=True)
        (app / "package.json").write_text('{"name":"%s","scripts":{"dev":"node x.js"}}' % name, encoding="utf-8")
        (app / ".black-eclipse").mkdir()
        (app / ".black-eclipse" / "app.json").write_text(
            '{"name":"%s","dependsOn":%s}' % (name, deps), encoding="utf-8",
        )
    graph = build_application_graph(tmp_path, discovery=discover_application)
    ids = set(graph.nodes)
    assert "apps/api" in ids and "apps/web" in ids
    order = graph.startup_order()
    assert order.index("apps/api") < order.index("apps/web")


def test_build_graph_single_app(tmp_path):
    from harness.execution.application.discovery import discover_application

    (tmp_path / "package.json").write_text('{"name":"solo","scripts":{"dev":"node x.js"}}', encoding="utf-8")
    graph = build_application_graph(tmp_path, discovery=discover_application)
    assert "__root__" in graph.nodes
    assert graph.startup_order() == ["__root__"]


# ── workspace start/stop through a fake manager ───────────────────────────────────


class _FakeManager:
    def __init__(self, tmp_path) -> None:
        self._runtimes: dict[str, RuntimeHandle] = {}
        self._tmp = tmp_path
        self.started: list[str] = []
        self.stopped: list[str] = []

    def start(self, root, **kwargs):
        self.started.append(str(root))
        handle = RuntimeHandle(runtime_id=f"rt_{len(self.started)}", application_id="app",
                               state=ApplicationState.RUNNING)
        from harness.execution.application.models import ApplicationDescriptor

        handle.descriptor = ApplicationDescriptor(name=Path(root).name, path=str(root))
        self._runtimes[handle.runtime_id] = handle
        return handle

    def stop(self, runtime_id, **kwargs):
        self.stopped.append(runtime_id)
        return {"status": "ok", "runtimeId": runtime_id}


def test_start_workspace_orders_apps(tmp_path):
    for name, deps in (("api", []), ("web", ["api"])):
        app = tmp_path / "apps" / name
        app.mkdir(parents=True)
        (app / "package.json").write_text('{"name":"%s","scripts":{"dev":"node x.js"}}' % name, encoding="utf-8")
        (app / ".black-eclipse").mkdir()
        (app / ".black-eclipse" / "app.json").write_text('{"name":"%s","dependsOn":%s}' % (name, deps), encoding="utf-8")
    manager = _FakeManager(tmp_path)
    result = start_workspace(manager, tmp_path, install=False)
    assert result["status"] == "ok"
    assert result["startupOrder"].index("apps/api") < result["startupOrder"].index("apps/web")
    # The API's own folder was started, not the root.
    assert any(p.endswith("apps\\api") or p.endswith("apps/api") for p in manager.started)


def test_stop_workspace_is_reverse_order(tmp_path):
    for name, deps in (("api", []), ("web", ["api"])):
        app = tmp_path / "apps" / name
        app.mkdir(parents=True)
        (app / "package.json").write_text('{"name":"%s","scripts":{"dev":"node x.js"}}' % name, encoding="utf-8")
        (app / ".black-eclipse").mkdir()
        (app / ".black-eclipse" / "app.json").write_text('{"name":"%s","dependsOn":%s}' % (name, deps), encoding="utf-8")
    manager = _FakeManager(tmp_path)
    start_workspace(manager, tmp_path, install=False)
    result = stop_workspace(manager, tmp_path)
    assert result["status"] == "ok"
    # web (dependent) stops before api (dependency).
    assert result["stopOrder"].index("apps/web") < result["stopOrder"].index("apps/api")
