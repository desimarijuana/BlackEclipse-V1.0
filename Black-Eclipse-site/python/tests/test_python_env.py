"""The managed analysis package environment: approval, lock, import, removal."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.code import sandbox as sandbox_mod
from harness.code.execution import AnalysisRequest, interpreter_path, run_analysis
from harness.python_env import paths, provisioner
from harness.python_env.authorizers import make_python_env_authorizer
from harness.python_env.tools import register_python_env_tools
from harness.tools import ToolRegistry


def _has_runner() -> bool:
    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        return False
    return bool(interpreter_path())


def _fake_package(target: Path, name: str = "demo_pkg", version: str = "1.0.0") -> None:
    package = target / name
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("VALUE = 42\n", encoding="utf-8")
    dist = target / f"{name}-{version}.dist-info"
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        encoding="utf-8",
    )
    (dist / "top_level.txt").write_text(f"{name}\n", encoding="utf-8")
    (dist / "RECORD").write_text(
        f"{name}/__init__.py,,\n{dist.name}/METADATA,,\n{dist.name}/top_level.txt,,\n",
        encoding="utf-8",
    )


def test_specs_are_plain_names_not_urls_or_paths():
    cleaned, error = provisioner.normalize_specs(["quantstats>=0.0.26"])
    assert error == "" and cleaned == ["quantstats>=0.0.26"]
    for bad in ("https://example.com/x.whl", "../local", "/tmp/x", "git+https://x"):
        _cleaned, error = provisioner.normalize_specs([bad])
        assert error


def test_install_writes_the_lock(monkeypatch, tmp_path: Path):
    def fake_run(argv, *, cwd, env, timeout_s):
        _fake_package(Path(cwd))
        return subprocess.CompletedProcess(argv, 0, "installed", "")

    monkeypatch.setattr(provisioner, "_run_pip", fake_run)
    result = provisioner.install(["demo_pkg"], interpreter="python", root=tmp_path)
    assert result.ok
    assert result.packages[0]["name"] == "demo_pkg"
    assert paths.installed_modules(tmp_path) == ["demo_pkg"]
    lock = paths.read_lock(tmp_path)
    assert lock["packages"][0]["version"] == "1.0.0"
    assert paths.lock_digest(tmp_path)


def test_remove_deletes_the_package_and_updates_the_lock(tmp_path: Path):
    target = paths.site_packages(tmp_path)
    target.mkdir(parents=True)
    _fake_package(target)
    paths.write_lock(paths.installed_packages(tmp_path), tmp_path)
    result = provisioner.remove(["demo_pkg"], root=tmp_path)
    assert result.ok and result.removed == ["demo_pkg"]
    assert not (target / "demo_pkg").exists()
    assert paths.installed_modules(tmp_path) == []


def test_authorizer_requests_then_accepts_one_single_use_approval():
    class Store:
        def __init__(self):
            self.requests = 0
            self.approved = False

        def consume_kind(self, **kwargs):
            return {"id": "appr"} if self.approved else None

        def request_kind(self, **kwargs):
            self.requests += 1
            return {"id": "appr_pending"}

    store = Store()
    ctx = SimpleNamespace(approvals=store, run_id="r", emitter=None)
    tool = SimpleNamespace(name="python_env_install")
    authorize = make_python_env_authorizer()
    assert asyncio.run(authorize(tool, {"packages": ["quantstats"]}, ctx)) is False
    assert store.requests == 1
    store.approved = True
    assert asyncio.run(authorize(tool, {"packages": ["quantstats"]}, ctx)) is True


def test_tools_register():
    registry = ToolRegistry()
    names = register_python_env_tools(registry)
    assert set(names) == {
        "python_env_install", "python_env_remove", "python_env_list", "python_env_status",
    }
    assert registry.get("python_env_install").permission == "write"


def test_analysis_can_import_an_installed_package(tmp_path: Path, monkeypatch):
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    target = paths.site_packages(tmp_path)
    target.mkdir(parents=True)
    _fake_package(target)
    paths.write_lock(paths.installed_packages(tmp_path), tmp_path)
    result = run_analysis(AnalysisRequest(
        source="import demo_pkg\nresult = {'value': demo_pkg.VALUE}\n",
        purpose="import the managed package",
    ))
    assert result.status == "ok"
    assert result.outputs["value"] == 42
