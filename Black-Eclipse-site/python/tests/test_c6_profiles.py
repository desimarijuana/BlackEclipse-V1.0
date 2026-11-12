"""C6: sandbox profiles plan the boundary and report honest enforceability."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.security.models import ACTION_SHELL_EXECUTE
from harness.security.profiles import (
    REQUIRED_CAPABILITIES,
    SandboxProfile,
    allowlist_permits,
    describe_profiles,
    parse_profile,
    path_within,
    resolve_profile,
)
from harness.security.sandbox import SandboxHandle, SandboxResult, SandboxSpec, UnavailableSandbox


class FakeSandbox:
    def __init__(self, name: str, caps: dict) -> None:
        self.name = name
        self._caps = caps

    def available(self) -> bool:
        return True

    def capabilities(self) -> dict:
        return {"backend": self.name, **self._caps}

    def create(self, spec: SandboxSpec) -> SandboxHandle:  # pragma: no cover - unused
        return SandboxHandle(id="sbx", backend=self.name)

    def execute(self, handle: SandboxHandle, spec: SandboxSpec) -> SandboxResult:  # pragma: no cover
        return SandboxResult(0, "", "", self.name, 0.0)


DOCKER_CAPS = {
    "processIsolation": True,
    "filesystemIsolation": True,
    "networkIsolation": True,
    "secretIsolation": True,
}
LOCAL_CAPS = {
    "processIsolation": True,
    "filesystemIsolation": False,
    "networkIsolation": False,
    "secretIsolation": True,
}


def test_profiles_parse_aliases_and_default():
    assert parse_profile("read-only") is SandboxProfile.READ_ONLY
    assert parse_profile("ro") is SandboxProfile.READ_ONLY
    assert parse_profile("workspace") is SandboxProfile.WORKSPACE_WRITE
    assert parse_profile("") is SandboxProfile.WORKSPACE_WRITE
    assert parse_profile("nonsense") is SandboxProfile.WORKSPACE_WRITE


def test_read_only_mounts_the_workspace_read_only_and_has_no_network():
    workspace = tempfile.mkdtemp(prefix="be-c6-ro-")
    plan = resolve_profile(
        SandboxProfile.READ_ONLY, argv=["cat", "x"], workspace=workspace,
        sandbox=FakeSandbox("docker", DOCKER_CAPS),
    )
    assert plan.enforceable, plan.reason
    assert plan.missing == ()
    assert plan.spec.allow_network is False
    assert plan.spec.mounts == [(workspace, "/workspace", True)]
    assert plan.to_dict()["profile"] == "read-only"


def test_workspace_write_mounts_writable_without_network():
    workspace = tempfile.mkdtemp(prefix="be-c6-rw-")
    plan = resolve_profile(
        SandboxProfile.WORKSPACE_WRITE, workspace=workspace,
        sandbox=FakeSandbox("docker", DOCKER_CAPS),
    )
    assert plan.enforceable
    assert plan.spec.mounts == [(workspace, "/workspace", False)]
    assert plan.spec.allow_network is False


def test_a_weak_host_is_not_enforceable_and_names_what_is_missing():
    plan = resolve_profile(
        SandboxProfile.READ_ONLY, workspace=tempfile.mkdtemp(),
        sandbox=FakeSandbox("local", LOCAL_CAPS),
    )
    assert plan.enforceable is False
    assert "filesystemIsolation" in plan.missing
    assert "networkIsolation" in plan.missing
    assert "cannot enforce" in plan.reason


def test_network_allowlist_requires_a_proxy_and_wires_proxy_env(monkeypatch):
    workspace = tempfile.mkdtemp(prefix="be-c6-net-")
    backend = FakeSandbox("docker", DOCKER_CAPS)

    monkeypatch.delenv("BLACK_ECLIPSE_EGRESS_PROXY", raising=False)
    without = resolve_profile(
        SandboxProfile.NETWORK_ALLOWLIST, workspace=workspace, sandbox=backend,
    )
    assert without.enforceable is False
    assert without.missing == ("egressProxy",)
    assert without.spec.allow_network is True

    monkeypatch.setenv("BLACK_ECLIPSE_EGRESS_PROXY", "http://127.0.0.1:8118")
    with_proxy = resolve_profile(
        SandboxProfile.NETWORK_ALLOWLIST, workspace=workspace,
        allowlist=["api.example.com", "*.data.example"],
        sandbox=backend,
    )
    assert with_proxy.enforceable, with_proxy.reason
    assert with_proxy.spec.env["HTTPS_PROXY"] == "http://127.0.0.1:8118"
    assert with_proxy.spec.env["HTTP_PROXY"] == "http://127.0.0.1:8118"


def test_full_only_needs_process_isolation():
    plan = resolve_profile(
        SandboxProfile.FULL, sandbox=FakeSandbox("local", LOCAL_CAPS),
    )
    assert plan.enforceable
    assert plan.spec.allow_network is True


def test_an_unavailable_backend_fails_closed():
    plan = resolve_profile(SandboxProfile.WORKSPACE_WRITE, sandbox=UnavailableSandbox())
    assert plan.enforceable is False
    assert plan.backend == "unavailable"
    assert plan.missing


def test_the_egress_allowlist_is_exact_and_wildcard_only():
    allow = ["api.example.com", "*.data.example"]
    assert allowlist_permits("api.example.com", allow)
    assert allowlist_permits("https://api.example.com/v1", allow)
    assert allowlist_permits("api.example.com:443", allow)
    assert allowlist_permits("x.data.example", allow)
    assert not allowlist_permits("data.example", allow)
    assert not allowlist_permits("evil.example.com", allow)
    assert not allowlist_permits("api.example.com.evil.com", allow)


def test_path_traversal_never_escapes_the_workspace():
    root = tempfile.mkdtemp(prefix="be-c6-root-")
    inside = os.path.join(root, "notes.txt")
    assert path_within(inside, root)
    assert path_within("notes.txt", root)
    assert not path_within(os.path.join(root, "..", "outside.txt"), root)
    assert not path_within("/etc/passwd", root)


def test_describe_profiles_reports_every_profile():
    report = describe_profiles(FakeSandbox("docker", DOCKER_CAPS))
    assert [item["profile"] for item in report] == [p.value for p in SandboxProfile]
    assert all(item["enforceable"] for item in report if item["profile"] != "network-allowlist")
    assert set(REQUIRED_CAPABILITIES) == set(SandboxProfile)


def test_a_configured_unenforceable_profile_refuses_execution(monkeypatch):
    from harness.security import integration, profiles

    monkeypatch.setenv("BLACK_ECLIPSE_SANDBOX_PROFILE", "read-only")
    monkeypatch.setattr(
        profiles, "get_sandbox", lambda: FakeSandbox("local", LOCAL_CAPS),
    )
    reason = integration.profile_requirement(ACTION_SHELL_EXECUTE)
    assert reason and "read-only" in reason

    monkeypatch.setattr(
        profiles, "get_sandbox", lambda: FakeSandbox("docker", DOCKER_CAPS),
    )
    assert integration.profile_requirement(ACTION_SHELL_EXECUTE) is None
    # A read action is not an execution action and is never blocked by a profile.
    assert integration.profile_requirement("filesystem.read") is None
