"""Learning journey graph: derived, bounded, scope-respecting, no writes."""

from __future__ import annotations

import pytest

from harness.eclipse_memory import EclipseMemoryService
from harness.learning_graph import build_learning_journey


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


def test_empty_graph_is_valid(service):
    graph = build_learning_journey(service.store)
    assert graph["nodes"] == []
    assert graph["stats"]["nodeCount"] == 0


def test_memory_nodes_are_projected(service):
    service.write_memory(memory_type="preference", content="I prefer concise answers", source="explicit_user", scope="user", scope_id="u1")
    graph = build_learning_journey(service.store, scope_id="u1")
    assert any(n["kind"] == "memory" for n in graph["nodes"])
    assert graph["stats"]["byKind"].get("memory") == 1


def test_graph_never_writes(service):
    service.write_memory(memory_type="preference", content="stable fact", source="explicit_user", scope="user", scope_id="u1")
    before = service.store.list_memories(limit=100)
    build_learning_journey(service.store)
    after = service.store.list_memories(limit=100)
    assert len(before) == len(after)


def test_supersession_edge(service):
    first = service.write_memory(memory_type="preference", content="I prefer detailed answers", source="explicit_user", scope="user", scope_id="u1")
    second = service.write_memory(memory_type="preference", content="I prefer concise answers", source="explicit_user", scope="user", scope_id="u1")
    # Create the supersession link directly (the graph projects the stored link,
    # independent of the conflict heuristic that decides when one is created).
    service.store.supersede_memory(first["id"], second["id"])
    graph = build_learning_journey(service.store, scope_id="u1")
    assert any(e["relation"] == "superseded_by" for e in graph["edges"])
    assert any(n["id"] == first["id"] for n in graph["nodes"])


def test_scope_isolation_hides_other_user_items(service):
    service.write_memory(memory_type="preference", content="belongs to u1", source="explicit_user", scope="user", scope_id="u1")
    service.write_memory(memory_type="preference", content="belongs to u2", source="explicit_user", scope="user", scope_id="u2")
    graph = build_learning_journey(service.store, scope_id="u1")
    labels = " ".join(n["label"] for n in graph["nodes"])
    assert "belongs to u2" not in labels


def test_status_filter(service):
    m = service.write_memory(memory_type="preference", content="will be archived", source="explicit_user", scope="user", scope_id="u1")
    service.store.archive_memory(m["id"])
    active_only = build_learning_journey(service.store, scope_id="u1", statuses=["active"])
    assert not any(n["id"] == m["id"] for n in active_only["nodes"])
    archived = build_learning_journey(service.store, scope_id="u1", statuses=["archived"])
    assert any(n["id"] == m["id"] for n in archived["nodes"])


def test_journey_reports_freshness(service):
    service.write_memory(memory_type="preference", content="I prefer concise answers", source="explicit_user", scope="user", scope_id="u1")
    graph = build_learning_journey(service.store, scope_id="u1")
    assert graph["generatedAt"]
    assert graph["watermark"]
    # The watermark is at least as old as the read time (ISO 8601 sortable).
    assert graph["watermark"] <= graph["generatedAt"]


def test_journey_freshness_empty_is_honest(service):
    graph = build_learning_journey(service.store)
    assert graph["generatedAt"]
    assert graph["watermark"] == graph["generatedAt"]
