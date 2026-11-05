"""Vision assets are owner-scoped for multi-user deployments."""

from __future__ import annotations

import base64

from harness.persistence import AgentMemoryStore
from harness.vision.image import decode_bytes
from harness.vision.storage import VisionAssetStore

# 1x1 transparent PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _store(tmp_path) -> VisionAssetStore:
    return VisionAssetStore(AgentMemoryStore(str(tmp_path / "agent-memory.db")))


def test_same_image_is_scoped_per_owner_and_local_keeps_the_legacy_id(tmp_path):
    store = _store(tmp_path)
    decoded = decode_bytes(PNG, source="a.png", expected_mime="image/png")

    local = store.save(decoded, owner="local")
    alice = store.save(decoded, owner="alice")
    bob = store.save(decoded, owner="bob")

    assert local.asset_id == decoded.asset_id  # backward compatible
    assert alice.asset_id != bob.asset_id
    assert alice.asset_id.startswith(decoded.asset_id)
    assert store.get(alice.asset_id, owner="alice").owner_id == "alice"
    assert store.get(bob.asset_id, owner="bob").owner_id == "bob"
    assert store.get(alice.asset_id, owner="bob") is None
    assert store.open_bytes(alice.asset_id, owner="bob") is None
    assert store.open_bytes(alice.asset_id, owner="alice") == PNG


def test_reanalysis_does_not_overwrite_the_uploaded_name(tmp_path):
    store = _store(tmp_path)
    decoded = decode_bytes(PNG, source="candle-option-A.png", expected_mime="image/png")
    first = store.save(
        decoded, owner="local", source_kind="upload", source_ref="candle-option-A.png",
        metadata={"name": "candle-option-A.png"},
    )
    # What the vision orchestrator does after reading the image: save the same
    # bytes with a raw-bytes source. The descriptive name must survive.
    second = store.save(decoded, owner="local", source_kind="bytes", source_ref=str(PNG))
    assert second.asset_id == first.asset_id
    assert second.source_ref == "candle-option-A.png"
    assert second.source_kind == "upload"
    assert second.metadata.get("name") == "candle-option-A.png"


def test_delete_and_list_are_owner_scoped(tmp_path):
    store = _store(tmp_path)
    decoded = decode_bytes(PNG, source="a.png", expected_mime="image/png")
    alice = store.save(decoded, owner="alice", run_id="run-a")
    store.save(decoded, owner="bob", run_id="run-b")

    assert store.delete(alice.asset_id, owner="bob") is False
    assert store.get(alice.asset_id, owner="alice") is not None
    assert [a.asset_id for a in store.list_for_run("run-a", owner="alice")] == [alice.asset_id]
    assert store.list_for_run("run-a", owner="bob") == []
    assert store.delete(alice.asset_id, owner="alice") is True
