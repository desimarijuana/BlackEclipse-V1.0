"""Memory list pagination + exact counts.

The Control Room used to load one capped page and present its length as a total.
These tests pin the contract the paged UI relies on: a stable filter definition
shared by list and count, offset paging, search, and lifecycle totals that are
not derived from a capped list.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-emem-page-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    try:
        for index in range(7):
            svc.write_memory(
                memory_type="semantic",
                content=f"Paged fact number {index} about reporting currency",
                source="explicit_user",
                scope="user",
                scope_id="u1",
                subject=f"subject-{index}",
                created_by="u1",
            )
        yield svc
    finally:
        svc.close()


def test_list_and_count_agree_across_pages(service):
    total = service.store.count_memories(scope="user", scope_id="u1")
    assert total == 7

    first = service.store.list_memories(scope="user", scope_id="u1", limit=3, offset=0)
    second = service.store.list_memories(scope="user", scope_id="u1", limit=3, offset=3)
    third = service.store.list_memories(scope="user", scope_id="u1", limit=3, offset=6)

    assert len(first) == 3
    assert len(second) == 3
    assert len(third) == 1
    assert {m["id"] for m in first} | {m["id"] for m in second} | {m["id"] for m in third} == {
        m["id"] for m in service.store.list_memories(scope="user", scope_id="u1", limit=50)
    }


def test_search_filters_in_the_same_clause_as_count(service):
    assert service.store.count_memories(search="number 3") == 1
    rows = service.store.list_memories(search="number 3", limit=50)
    assert len(rows) == 1
    assert "number 3" in rows[0]["content"]

    assert service.store.count_memories(search="not-a-real-phrase") == 0
    assert service.store.list_memories(search="not-a-real-phrase", limit=50) == []


def test_lifecycle_count_does_not_depend_on_the_list_cap(service):
    assert service.store.count_lifecycle_memories("active") == 7
    page = service.store.list_lifecycle_memories("active", limit=2, offset=4)
    assert len(page) == 2
    # 7 records, so the last page from offset 6 has exactly one row.
    assert len(service.store.list_lifecycle_memories("active", limit=2, offset=6)) == 1


def test_overview_counts_are_exact_not_capped(service):
    counts = service.store.memory_counts()
    assert counts["total"] == 7
    assert counts["byType"]["semantic"] == 7
    assert counts["byStatus"]["active"] == 7
