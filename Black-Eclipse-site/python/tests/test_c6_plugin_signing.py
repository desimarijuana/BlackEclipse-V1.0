"""C6: plugin install signature + review gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.events import EventBus
from harness.persistence import AgentMemoryStore
from harness.plugins.errors import PluginError
from harness.plugins.loader import checksum
from harness.plugins.manager import PluginManager
from harness.plugins import signing
from harness.plugins.manifest import parse_manifest
from harness.tools import ToolRegistry

KEY = "plugin-signing-key-long-enough"
BUNDLED = Path(__file__).resolve().parents[1] / "harness" / "plugins" / "bundled"


def _manifest_data(plugin_id: str = "signed-plugin") -> dict:
    return {
        "id": plugin_id,
        "name": plugin_id,
        "version": "1.0.0",
        "runtime": {"type": "python", "entrypoint": "plugin:Impl"},
        "permissions": [],
        "contributes": {"tools": []},
    }


def _write_plugin(root: Path, plugin_id: str = "signed-plugin") -> Path:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "plugin.json").write_text(json.dumps(_manifest_data(plugin_id)), encoding="utf-8")
    (src / "plugin.py").write_text("class Impl:\n    pass\n\nplugin = Impl\n", encoding="utf-8")
    return src


def _manager(root: Path) -> PluginManager:
    store = AgentMemoryStore(str(root / "agent-memory.db"))
    return PluginManager(
        store, ToolRegistry(), EventBus(), None,
        plugins_dir=root / "plugins", bundled_dir=BUNDLED,
    )


def test_a_signature_roundtrips_and_binds_the_digest(tmp_path):
    src = _write_plugin(tmp_path)
    manifest = parse_manifest(json.loads((src / "plugin.json").read_text()))
    digest = checksum(src)
    signature = signing.sign_manifest(manifest, digest, key=KEY)
    assert signing.verify_signature(manifest, digest, signature, key=KEY)
    assert not signing.verify_signature(manifest, "0" * 64, signature, key=KEY)
    assert not signing.verify_signature(manifest, digest, signature, key="another-key-long-enough")


def test_the_sidecar_is_excluded_from_the_content_digest(tmp_path):
    src = _write_plugin(tmp_path)
    before = checksum(src)
    (src / "plugin.sig").write_text("hmac-sha256:deadbeef", encoding="utf-8")
    assert checksum(src) == before


def test_install_requires_a_signature_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv(signing.REQUIRE_SIGNATURE_ENV, "1")
    monkeypatch.setenv(signing.SIGNING_KEY_ENV, KEY)
    src = _write_plugin(tmp_path)
    manager = _manager(tmp_path)
    with pytest.raises(PluginError) as exc:
        __import__("asyncio").run(manager.install(src, operator=True))
    assert exc.value.code == "PLUGIN_SIGNATURE_INVALID"


def test_a_valid_signature_is_recorded_and_installs(tmp_path, monkeypatch):
    monkeypatch.setenv(signing.REQUIRE_SIGNATURE_ENV, "1")
    monkeypatch.setenv(signing.SIGNING_KEY_ENV, KEY)
    src = _write_plugin(tmp_path)
    manifest = parse_manifest(json.loads((src / "plugin.json").read_text()))
    (src / "plugin.sig").write_text(
        signing.sign_manifest(manifest, checksum(src), key=KEY), encoding="utf-8",
    )
    manager = _manager(tmp_path)
    result = __import__("asyncio").run(manager.install(src, operator=True))
    assert result["plugin"]["verification"] == "signature"


def test_a_tampered_package_loses_its_signature(tmp_path, monkeypatch):
    monkeypatch.setenv(signing.REQUIRE_SIGNATURE_ENV, "1")
    monkeypatch.setenv(signing.SIGNING_KEY_ENV, KEY)
    src = _write_plugin(tmp_path)
    manifest = parse_manifest(json.loads((src / "plugin.json").read_text()))
    (src / "plugin.sig").write_text(
        signing.sign_manifest(manifest, checksum(src), key=KEY), encoding="utf-8",
    )
    (src / "plugin.py").write_text("class Impl:\n    pass\n# tampered\n", encoding="utf-8")
    manager = _manager(tmp_path)
    with pytest.raises(PluginError) as exc:
        __import__("asyncio").run(manager.install(src, operator=True))
    assert exc.value.code == "PLUGIN_SIGNATURE_INVALID"
    # A refused install leaves no package behind.
    assert not (tmp_path / "plugins" / "signed-plugin").exists()


def test_requiring_signatures_without_a_key_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv(signing.REQUIRE_SIGNATURE_ENV, "1")
    monkeypatch.delenv(signing.SIGNING_KEY_ENV, raising=False)
    src = _write_plugin(tmp_path)
    manager = _manager(tmp_path)
    with pytest.raises(PluginError) as exc:
        __import__("asyncio").run(manager.install(src, operator=True))
    assert exc.value.code == "PLUGIN_SIGNING_UNAVAILABLE"


def test_review_is_mandatory_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv(signing.REQUIRE_REVIEW_ENV, "1")
    monkeypatch.delenv(signing.REQUIRE_SIGNATURE_ENV, raising=False)
    src = _write_plugin(tmp_path)
    manager = _manager(tmp_path)
    with pytest.raises(PluginError) as exc:
        __import__("asyncio").run(manager.install(src, operator=False))
    assert exc.value.code == "PLUGIN_REVIEW_REQUIRED"

    result = __import__("asyncio").run(manager.install(src, operator=True))
    assert result["plugin"]["status"] == "INSTALLED"


# ── Ed25519 public-key publisher signatures (C6.10) ─────────────────────────
SEED = bytes.fromhex(
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
)
PUBLIC = bytes.fromhex(
    "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
)
RFC_SIGNATURE = bytes.fromhex(
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
)


def test_ed25519_matches_the_rfc_8032_vector():
    from harness.plugins import ed25519

    assert ed25519.public_key(SEED) == PUBLIC
    assert ed25519.sign(SEED, b"") == RFC_SIGNATURE
    assert ed25519.verify(PUBLIC, b"", RFC_SIGNATURE)
    assert not ed25519.verify(PUBLIC, b"x", RFC_SIGNATURE)
    tampered = bytearray(RFC_SIGNATURE)
    tampered[0] ^= 1
    assert not ed25519.verify(PUBLIC, b"", bytes(tampered))


def test_an_ed25519_signed_plugin_installs(tmp_path, monkeypatch):
    monkeypatch.setenv(signing.REQUIRE_SIGNATURE_ENV, "1")
    monkeypatch.delenv(signing.SIGNING_KEY_ENV, raising=False)
    monkeypatch.setenv(signing.TRUSTED_KEYS_ENV, PUBLIC.hex())
    src = _write_plugin(tmp_path)
    manifest = parse_manifest(json.loads((src / "plugin.json").read_text()))
    (src / "plugin.sig").write_text(
        signing.sign_manifest_ed25519(manifest, checksum(src), seed_hex=SEED.hex()),
        encoding="utf-8",
    )
    manager = _manager(tmp_path)
    result = __import__("asyncio").run(manager.install(src, operator=True))
    assert result["plugin"]["verification"] == "signature"


def test_an_unknown_ed25519_key_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv(signing.REQUIRE_SIGNATURE_ENV, "1")
    monkeypatch.delenv(signing.SIGNING_KEY_ENV, raising=False)
    other = bytes.fromhex("11" * 32)
    monkeypatch.setenv(signing.TRUSTED_KEYS_ENV, other.hex())
    src = _write_plugin(tmp_path)
    manifest = parse_manifest(json.loads((src / "plugin.json").read_text()))
    (src / "plugin.sig").write_text(
        signing.sign_manifest_ed25519(manifest, checksum(src), seed_hex=SEED.hex()),
        encoding="utf-8",
    )
    manager = _manager(tmp_path)
    with pytest.raises(PluginError) as exc:
        __import__("asyncio").run(manager.install(src, operator=True))
    assert exc.value.code == "PLUGIN_SIGNATURE_INVALID"


def test_ed25519_without_trusted_keys_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv(signing.REQUIRE_SIGNATURE_ENV, "1")
    monkeypatch.delenv(signing.SIGNING_KEY_ENV, raising=False)
    monkeypatch.delenv(signing.TRUSTED_KEYS_ENV, raising=False)
    src = _write_plugin(tmp_path)
    manifest = parse_manifest(json.loads((src / "plugin.json").read_text()))
    (src / "plugin.sig").write_text(
        signing.sign_manifest_ed25519(manifest, checksum(src), seed_hex=SEED.hex()),
        encoding="utf-8",
    )
    manager = _manager(tmp_path)
    with pytest.raises(PluginError) as exc:
        __import__("asyncio").run(manager.install(src, operator=True))
    assert exc.value.code == "PLUGIN_SIGNING_UNAVAILABLE"
