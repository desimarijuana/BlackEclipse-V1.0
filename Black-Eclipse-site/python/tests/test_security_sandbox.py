"""Execution sandbox — the physical boundary, separate from authorization."""

from __future__ import annotations

import sys

from harness.security.sandbox import (
    DockerSandbox,
    LocalSandbox,
    SandboxSpec,
    SandboxUnavailable,
    UnavailableSandbox,
    docker_argv,
    select_sandbox,
    set_sandbox,
)


def test_unavailable_sandbox_fails_closed():
    sandbox = UnavailableSandbox()
    assert sandbox.available() is False
    result = sandbox.execute(None, SandboxSpec(argv=["echo", "hi"]))
    assert result.refused is True
    assert result.ok is False
    try:
        sandbox.create(SandboxSpec(argv=["echo"]))
        raise AssertionError("create should have raised")
    except SandboxUnavailable:
        pass


def test_docker_argv_is_hardened():
    argv = docker_argv(
        SandboxSpec(
            argv=["python", "-c", "print(1)"],
            allow_network=False,
            secret_env={"TOKEN": "s3cr3t"},
            memory_mb=256,
            pids=64,
            cpus=1.0,
            mounts=[("/host/proj", "/work", True)],
        ),
        container_name="c1",
    )
    joined = " ".join(argv)
    assert "--network none" in joined
    assert "--read-only" in joined
    assert "no-new-privileges" in joined
    assert "--cap-drop ALL" in joined
    assert "--user 1000:1000" in joined
    assert "--memory 256m" in joined
    assert "--pids-limit 64" in joined
    assert "/host/proj:/work:ro" in joined
    assert "-e TOKEN=s3cr3t" in joined
    assert argv[-3:] == ["python", "-c", "print(1)"]


def test_docker_argv_network_bridge_when_allowed():
    argv = docker_argv(SandboxSpec(argv=["true"], allow_network=True), container_name="c")
    assert "--network bridge" in " ".join(argv)


def test_local_sandbox_reports_honest_capabilities():
    caps = LocalSandbox().capabilities()
    assert caps["secretIsolation"] is True
    # The local backend does NOT provide filesystem/network isolation.
    assert caps["filesystemIsolation"] is False
    assert caps["networkIsolation"] is False


def test_local_sandbox_executes_and_captures_output():
    sandbox = LocalSandbox()
    if not sandbox.available():
        return  # no isolation primitive on this host: honest skip
    handle = sandbox.create(SandboxSpec(argv=[]))
    result = sandbox.execute(handle, SandboxSpec(
        argv=[sys.executable, "-c", "print('sandbox-ok')"], timeout_s=30,
    ))
    assert result.refused is False
    assert "sandbox-ok" in result.stdout


def test_select_sandbox_never_returns_unbounded():
    set_sandbox(None)
    sandbox = select_sandbox(prefer="does-not-exist")
    assert sandbox.name == "unavailable"
    chosen = select_sandbox()
    assert chosen.name in ("docker", "local", "unavailable")
