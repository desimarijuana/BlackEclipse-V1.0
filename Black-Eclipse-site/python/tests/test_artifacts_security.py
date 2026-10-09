"""Artifact security tests — path confinement, owner isolation, unsafe names."""

from __future__ import annotations

import os

import pytest

from harness.artifacts import ArtifactService, ArtifactStore, LocalArtifactStorage
from harness.artifacts.model import ListArtifactsQuery, RegisterArtifactInput
from harness.artifacts.service import ArtifactError
from harness.artifacts.storage import StorageError
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def env(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    service = ArtifactService(ArtifactStore(store), LocalArtifactStorage(tmp_path / "files"))
    yield service
    store.close()


def test_source_path_traversal_denied(env):
    with pytest.raises(ArtifactError) as exc:
        env.register(
            RegisterArtifactInput(source_path="../../../../etc/hosts", name="hosts"),
        )
    assert exc.value.code == "ARTIFACT_SOURCE_DENIED"


def test_storage_key_traversal_denied(env):
    with pytest.raises(StorageError) as exc:
        env.storage.open("../../escape.txt")
    assert exc.value.code == "ARTIFACT_PATH_DENIED"


def test_absolute_source_outside_roots_denied(env):
    outside = os.path.abspath(os.path.join(os.environ.get("SystemRoot", "/tmp"), "somefile.txt"))
    with pytest.raises(ArtifactError):
        env.register(RegisterArtifactInput(source_path=outside, name="x"))


def test_owner_isolation(env):
    artifact = env.register_bytes(b"secret", name="s.txt", owner_id="alice")
    with pytest.raises(ArtifactError) as exc:
        env.get(artifact.id, owner_id="bob")
    assert exc.value.code == "ARTIFACT_NOT_FOUND"
    page = env.list(ListArtifactsQuery(), owner_id="bob")
    assert page.total == 0
    page_alice = env.list(ListArtifactsQuery(), owner_id="alice")
    assert page_alice.total == 1


def test_malicious_filename_is_sanitized(env):
    artifact = env.register_bytes(b"data", name="../../evil\u0000name.txt")
    # The display name is preserved, but the storage key never contains separators
    # beyond the intended owner/date prefix.
    parts = artifact.storage_key.split("/", 3)
    assert ".." not in artifact.storage_key
    assert "\x00" not in artifact.storage_key
    assert artifact.storage_key.endswith(".txt")
    assert len(parts) >= 4


def test_download_denied_for_other_owner(env):
    artifact = env.register_bytes(b"secret", name="s.txt", owner_id="alice")
    with pytest.raises(ArtifactError):
        env.open_content(artifact.id, owner_id="bob")
