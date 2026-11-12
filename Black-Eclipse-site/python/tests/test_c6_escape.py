"""C6 escape suite: traversal, env exfiltration, fork bombs and raw egress.

These are the four escape classes the round-5 acceptance names. Each test proves
the boundary refuses the escape, or reports honestly that the host cannot enforce
it — never that it silently degrades.
"""

from __future__ import annotations

import sys
import tempfile

import pytest

from harness.code.sandbox import RunSpec, build_env
from harness.security.profiles import SandboxProfile, resolve_profile
from harness.security.sandbox import (
    LocalSandbox,
    SandboxSpec,
    UnavailableSandbox,
    docker_argv,
)

HARDENED = {
    "processIsolation": True,
    "filesystemIsolation": True,
    "networkIsolation": True,
    "secretIsolation": True,
}


class FakeSandbox:
    name = "docker"

    def available(self) -> bool:
        return True

    def capabilities(self) -> dict:
        return {"backend": self.name, **HARDENED}


# ── path traversal ──────────────────────────────────────────────────────────
def test_only_the_workspace_is_mounted_and_it_is_read_only_for_read_only():
    workspace = tempfile.mkdtemp(prefix="be-escape-")
    plan = resolve_profile(
        SandboxProfile.READ_ONLY, workspace=workspace, sandbox=FakeSandbox(),
    )
    assert plan.spec.mounts == [(workspace, "/workspace", True)]
    # A traversal outside the workspace has no mount to reach: the container
    # rootfs is read-only and the host paths are not present.
    assert all(host == workspace for host, _, _ in plan.spec.mounts)


def test_a_workspace_write_profile_never_widens_the_mount():
    workspace = tempfile.mkdtemp(prefix="be-escape-rw-")
    plan = resolve_profile(
        SandboxProfile.WORKSPACE_WRITE, workspace=workspace, sandbox=FakeSandbox(),
    )
    assert plan.spec.mounts == [(workspace, "/workspace", False)]
    assert plan.spec.allow_network is False


# ── env exfiltration ────────────────────────────────────────────────────────
def test_the_child_environment_contains_no_parent_secret(monkeypatch):
    for key in ("HARNESS_AUTH_SECRET", "CRON_SECRET", "OPENAI_API_KEY",
                "BLACK_ECLIPSE_SETTINGS_KEY"):
        monkeypatch.setenv(key, "super-secret-value")
    env = build_env()
    for key in ("HARNESS_AUTH_SECRET", "CRON_SECRET", "OPENAI_API_KEY",
                "BLACK_ECLIPSE_SETTINGS_KEY"):
        assert key not in env, f"{key} leaked into the sandbox environment"


def test_proxy_configuration_is_dropped_from_the_child_environment(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://attacker:8080")
    monkeypatch.setenv("HTTP_PROXY", "http://attacker:8080")
    env = build_env()
    assert "HTTPS_PROXY" not in env
    assert "HTTP_PROXY" not in env


# ── fork bomb / resource exhaustion ─────────────────────────────────────────
def test_a_fork_bomb_is_bounded_by_a_pid_limit_in_the_container():
    spec = SandboxSpec(argv=["bash", "-c", ":(){ :|:& };:"], pids=32, memory_mb=128)
    argv = docker_argv(spec, container_name="eclipse_escape")
    assert "--pids-limit" in argv and "32" in argv
    assert "--memory" in argv and "128m" in argv
    assert "--cap-drop" in argv and "ALL" in argv


def test_the_local_primitive_also_carries_a_process_limit():
    # `RunSpec.process_limit` is the Job Object / rlimit bound the local backend
    # applies; a profile plan forwards whatever the caller sets.
    plan = resolve_profile(
        SandboxProfile.FULL, pids=48, memory_mb=256, sandbox=FakeSandbox(),
    )
    assert plan.spec.pids == 48
    assert plan.spec.memory_mb == 256
    assert RunSpec(
        argv=["true"], cwd=tempfile.gettempdir(), env={}, timeout_s=10,
        output_cap_bytes=1_000, network=False, process_limit=48,
    ).process_limit == 48


# ── egress ─────────────────────────────────────────────────────────────────
def test_raw_egress_is_not_an_allowlist(monkeypatch):
    monkeypatch.delenv("BLACK_ECLIPSE_EGRESS_PROXY", raising=False)
    plan = resolve_profile(
        SandboxProfile.NETWORK_ALLOWLIST, sandbox=FakeSandbox(),
    )
    assert plan.enforceable is False
    assert plan.missing == ("egressProxy",)


def test_allowlisted_profile_routes_through_the_proxy_only(monkeypatch):
    monkeypatch.setenv("BLACK_ECLIPSE_EGRESS_PROXY", "http://127.0.0.1:8118")
    plan = resolve_profile(
        SandboxProfile.NETWORK_ALLOWLIST, allowlist=["api.example.com"],
        sandbox=FakeSandbox(),
    )
    assert plan.enforceable
    assert plan.spec.env["HTTPS_PROXY"] == "http://127.0.0.1:8118"
    assert plan.allowlist == ("api.example.com",)


def test_workspace_write_has_no_network_at_all():
    plan = resolve_profile(
        SandboxProfile.WORKSPACE_WRITE, sandbox=FakeSandbox(),
    )
    assert plan.spec.allow_network is False


# ── fail closed ────────────────────────────────────────────────────────────
def test_an_unavailable_host_refuses_every_profile_that_promises_isolation():
    for profile in (SandboxProfile.READ_ONLY, SandboxProfile.WORKSPACE_WRITE,
                    SandboxProfile.NETWORK_ALLOWLIST, SandboxProfile.FULL):
        plan = resolve_profile(profile, sandbox=UnavailableSandbox())
        assert plan.enforceable is False


def test_an_unavailable_sandbox_refuses_execution():
    result = UnavailableSandbox().execute(None, SandboxSpec(argv=["true"]))
    assert result.refused and not result.ok


def test_the_hardened_docker_argv_is_deny_by_default():
    argv = docker_argv(SandboxSpec(argv=["true"]), container_name="eclipse_x")
    joined = " ".join(argv)
    assert "--network none" in joined
    assert "--read-only" in joined
    assert "no-new-privileges" in joined
    assert "--cap-drop ALL" in joined
    assert "--user 1000:1000" in joined


def test_local_sandbox_honours_the_plan_environment():
    """A profile's explicit env (the egress proxy) must reach the child."""
    sandbox = LocalSandbox()
    if not sandbox.available():
        pytest.skip("no local process primitive on this host")
    spec = SandboxSpec(
        argv=[sys.executable, "-c",
              "import os; print(os.environ.get('C6_MARKER', 'missing'))"],
        env={"C6_MARKER": "planned"},
        timeout_s=30,
    )
    result = sandbox.execute(sandbox.create(spec), spec)
    assert result.refused is False, result.reason
    assert "planned" in result.stdout
