"""Hosted registry: index, search, verified download, safe extract, install."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from harness.plugins.registry_client import RegistryError

from plugins_helpers import env


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _plugin_zip(plugin_id: str = "acme", version: str = "1.0.0", tool: str = "ping") -> bytes:
    manifest = (
        f"id: {plugin_id}\nname: {plugin_id}\nversion: {version}\n"
        f"runtime:\n  type: python\n  entrypoint: plugin:Impl\n"
        f"contributes:\n  tools:\n    - name: {tool}\n      description: ping\n"
    )
    plugin_py = (
        "from harness.plugins.sdk import Plugin, tool\n\n\n"
        "class Impl(Plugin):\n"
        f'    @tool(name="{tool}", schema={{}})\n'
        f"    async def {tool}(self, args, ctx):\n        return 'pong'\n\n\n"
        "plugin = Impl\n"
    )
    return _zip_bytes({"plugin.yaml": manifest, "plugin.py": plugin_py})


def _write_registry(root: Path, payload: bytes, *, checksum: str | None,
                    download: str = "acme-1.0.0.zip") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / download).write_bytes(payload)
    index = {"name": "test-registry", "plugins": [{
        "id": "acme", "name": "Acme", "version": "1.0.0", "description": "demo",
        "publisher": "acme-inc", "category": "tools", "trust": "community",
        "checksum": checksum, "downloadUrl": download,
    }]}
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")
    return root


def test_registry_search_and_install(env, tmp_path):
    payload = _plugin_zip()
    checksum = hashlib.sha256(payload).hexdigest()
    registry = _write_registry(tmp_path / "reg", payload, checksum=checksum)
    manager = env.manager

    index = manager.registry_index(str(registry))
    assert index["name"] == "test-registry"
    results = manager.registry_search("acme", source=str(registry))
    assert results and results[0]["id"] == "acme"
    assert results[0]["checksum"] == checksum

    import asyncio

    result = asyncio.run(manager.install_from_registry("acme", source=str(registry), enable=True))
    assert result["ok"] is True
    assert manager.is_active("acme")
    assert env.registry.get("plug_acme_ping") is not None


def test_registry_rejects_checksum_mismatch(env, tmp_path):
    registry = _write_registry(tmp_path / "reg2", _plugin_zip(), checksum="deadbeef")
    manager = env.manager
    import asyncio

    with pytest.raises(RegistryError) as exc:
        asyncio.run(manager.install_from_registry("acme", source=str(registry)))
    assert exc.value.code == "PLUGIN_CHECKSUM_MISMATCH"


def test_registry_rejects_zip_slip(env, tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../evil.txt", "pwned")
        archive.writestr("plugin.yaml", "id: z\nname: z\nversion: 1.0.0\nruntime: {type: python, entrypoint: plugin:Impl}\n")
    payload = buffer.getvalue()
    registry = tmp_path / "reg3"
    registry.mkdir()
    (registry / "z.zip").write_bytes(payload)
    (registry / "index.json").write_text(json.dumps({"plugins": [{
        "id": "z", "name": "z", "version": "1.0.0",
        "checksum": hashlib.sha256(payload).hexdigest(), "downloadUrl": "z.zip",
    }]}), encoding="utf-8")
    import asyncio

    with pytest.raises(RegistryError) as exc:
        asyncio.run(env.manager.install_from_registry("z", source=str(registry)))
    assert exc.value.code == "PLUGIN_PACKAGE_PATH_ESCAPE"
    assert not (registry / "evil.txt").exists()
