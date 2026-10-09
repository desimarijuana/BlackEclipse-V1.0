"""Artifact store + service tests: persistence, filtering, versioning,
lifecycle, collections, idempotency and reconciliation."""

from __future__ import annotations

import base64

import pytest

from harness.artifacts import ArtifactService, ArtifactStore, LocalArtifactStorage
from harness.artifacts.model import (
    AddVersionInput,
    ArtifactCategory,
    ArtifactStatus,
    BulkActionInput,
    CollectionInput,
    ListArtifactsQuery,
    RegisterArtifactInput,
    UpdateArtifactInput,
)
from harness.artifacts.service import ArtifactError
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def env(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    astore = ArtifactStore(store)
    service = ArtifactService(astore, LocalArtifactStorage(tmp_path / "files"))
    yield store, astore, service
    store.close()


def _register(service, name="report.csv", data=b"a,b\n1,2\n", **kw):
    return service.register_bytes(data, name=name, **kw)


def test_register_and_get(env):
    _, _, service = env
    artifact = _register(service, tags=["finance"])
    fetched = service.get(artifact.id)
    assert fetched.name == "report.csv"
    assert fetched.category is ArtifactCategory.DATASET
    assert fetched.mime_type == "text/csv"
    assert fetched.checksum and len(fetched.checksum) == 64
    assert fetched.tags == ["finance"]
    assert fetched.status is ArtifactStatus.ACTIVE
    assert fetched.storage_key and fetched.storage_key.endswith("report.csv")


def test_empty_file_is_valid(env):
    _, _, service = env
    artifact = _register(service, name="empty.txt", data=b"")
    assert artifact.size_bytes == 0


def test_idempotency_key_returns_same_artifact(env):
    _, _, service = env
    first = _register(service, idempotency_key="k1")
    second = _register(service, idempotency_key="k1")
    assert first.id == second.id
    page = service.list(ListArtifactsQuery())
    assert page.total == 1


def test_list_search_sort_pagination(env):
    _, _, service = env
    for i in range(5):
        _register(service, name=f"file{i}.txt", data=f"body {i}".encode())
    page = service.list(ListArtifactsQuery(q="file0"))
    assert page.total == 1
    page_all = service.list(ListArtifactsQuery(limit=2, offset=0, sort="name"))
    assert len(page_all.artifacts) == 2
    assert page_all.total == 5
    assert page_all.has_more is True
    names = [a.name for a in page_all.artifacts]
    assert names == sorted(names)


def test_unknown_sort_rejected(env):
    with pytest.raises(Exception):
        ListArtifactsQuery(sort="drop table")


def test_versions_preserve_original(env):
    _, _, service = env
    artifact = _register(service, name="v.txt", data=b"first")
    updated = service.add_version(
        artifact.id, AddVersionInput(content_base64=base64.b64encode(b"second").decode())
    )
    assert updated.version_number == 2
    versions = service.list_versions(artifact.id)
    assert [v.version_number for v in versions] == [2, 1]
    handle, _ = service.open_content(artifact.id)
    assert handle.read() == b"second"
    handle2, _ = service.open_content(artifact.id, version=1)
    assert handle2.read() == b"first"


def test_lifecycle_archive_restore_delete(env):
    _, _, service = env
    artifact = _register(service)
    assert service.archive(artifact.id).status is ArtifactStatus.ARCHIVED
    assert service.list(ListArtifactsQuery()).total == 0
    assert service.list(ListArtifactsQuery(include_archived=True)).total == 1
    assert service.restore(artifact.id).status is ArtifactStatus.ACTIVE
    assert service.delete(artifact.id).status is ArtifactStatus.DELETED
    assert service.purge(artifact.id) is True
    with pytest.raises(ArtifactError):
        service.get(artifact.id)


def test_purge_requires_soft_delete(env):
    _, _, service = env
    artifact = _register(service)
    with pytest.raises(ArtifactError) as exc:
        service.purge(artifact.id)
    assert exc.value.code == "ARTIFACT_NOT_DELETED"


def test_update_tags_and_favorite(env):
    _, _, service = env
    artifact = _register(service)
    updated = service.update(
        artifact.id, UpdateArtifactInput(name="renamed.txt", tags=["a", "b"], favorite=True)
    )
    assert updated.name == "renamed.txt"
    assert set(updated.tags) == {"a", "b"}
    assert updated.favorite is True
    # Replacing tags removes the previous ones.
    again = service.update(artifact.id, UpdateArtifactInput(tags=["c"]))
    assert again.tags == ["c"]


def test_bulk_partial_failure_reported(env):
    _, _, service = env
    a = _register(service, name="a.txt")
    b = _register(service, name="b.txt")
    result = service.bulk(BulkActionInput(artifact_ids=[a.id, "missing"], action="archive"))
    assert a.id in result["succeeded"]
    assert result["failed"][0]["artifactId"] == "missing"
    assert service.get(b.id, touch=False).status is ArtifactStatus.ACTIVE


def test_collections_and_membership(env):
    _, _, service = env
    parent = service.create_collection(CollectionInput(name="parent"))
    child = service.create_collection(CollectionInput(name="child", parent_id=parent.id))
    assert child.parent_id == parent.id
    artifact = _register(service)
    service.move(artifact.id, child.id)
    assert child.id in service.get(artifact.id).collection_ids
    listed = {c.name for c in service.list_collections()}
    assert listed == {"parent", "child"}
    # A collection with an unknown parent is refused.
    with pytest.raises(ArtifactError) as exc:
        service.create_collection(CollectionInput(name="orphan", parent_id="nope"))
    assert exc.value.code == "ARTIFACT_COLLECTION_NOT_FOUND"


def test_reconcile_recovers_missing(env):
    _, astore, service = env
    artifact = _register(service)
    # Delete the underlying object out from under the catalog.
    service.storage.delete(artifact.storage_key)
    report = service.reconcile()
    assert artifact.id in report["missing"]
    assert service.get(artifact.id).status is ArtifactStatus.MISSING
    # Re-registering the same bytes under a new id does not resurrect the old row.
    restored = _register(service, name="restored.txt")
    assert restored.id != artifact.id


def test_stats(env):
    _, _, service = env
    _register(service, name="x.txt")
    _register(service, name="y.png", data=b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    stats = service.stats()
    assert stats["total"] == 2
    assert stats["byStatus"]["ACTIVE"] == 2


def test_cleanup_expired_purges_past_retention(env):
    _, _, service = env
    artifact = _register(service)
    service.delete(artifact.id)
    # A retention deadline in the past makes the soft-deleted row purgeable.
    service._store.update_fields(artifact.id, {"retentionUntil": "2000-01-01T00:00:00+00:00"})
    result = service.cleanup_expired()
    assert artifact.id in result["purged"]
    with pytest.raises(ArtifactError):
        service.get(artifact.id)


def test_cleanup_expired_keeps_recent_deletions(env):
    _, _, service = env
    artifact = _register(service)
    service.delete(artifact.id)
    result = service.cleanup_expired(grace_days=30)
    assert artifact.id in result["skipped"]
    assert service.get(artifact.id).status is ArtifactStatus.DELETED


def test_persists_across_store_restart(tmp_path):
    db = tmp_path / "agent-memory.db"
    files = tmp_path / "files"
    store1 = AgentMemoryStore(str(db))
    service1 = ArtifactService(ArtifactStore(store1), LocalArtifactStorage(files))
    artifact = service1.register_bytes(b"persisted-bytes", name="p.txt")
    store1.close()
    # Reopen with a fresh connection (a process restart) on the SAME paths.
    store2 = AgentMemoryStore(str(db))
    service2 = ArtifactService(ArtifactStore(store2), LocalArtifactStorage(files))
    fetched = service2.get(artifact.id)
    assert fetched.name == "p.txt"
    handle, _ = service2.open_content(artifact.id)
    assert handle.read() == b"persisted-bytes"
    store2.close()
