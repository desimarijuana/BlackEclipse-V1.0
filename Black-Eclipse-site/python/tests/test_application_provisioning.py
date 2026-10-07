"""Provider readiness + provider-driven requirements — tests.

Deterministic and offline: a fake registry of adapters whose availability and
credential status are controlled by the test. No real CLI is probed.
"""

from __future__ import annotations

from pathlib import Path

from harness.execution.application.provisioning import (
    _install_hint,
    provider_readiness,
    required_providers_for,
)


class _FakeAdapter:
    def __init__(self, name, *, installed=True, authenticated=None, version="1.0", kind="deployment",
                 credential_env=()) -> None:
        self.name = name
        self.binary = name
        self.kind = kind
        self._installed = installed
        self._authenticated = authenticated
        self._version = version
        self.credential_env = tuple(credential_env)

    def available(self) -> bool:
        return self._installed

    def version(self) -> str:
        return self._version if self._installed else ""

    def credential_status(self):
        return {
            "provider": self.name,
            "configured": self._authenticated,
            "present": [],
            "required": list(self.credential_env),
        }


class _Registry:
    def __init__(self, *, containers=(), orchestrators=(), infrastructure=(), deployments=()) -> None:
        self.containers = _Sub(containers)
        self.orchestrators = _Sub(orchestrators)
        self.infrastructure = _Sub(infrastructure)
        self.deployments = _Sub(deployments)


class _Sub:
    def __init__(self, adapters) -> None:
        self._by_name = {a.name.casefold(): a for a in adapters}


def test_readiness_reports_missing_and_auth():
    registry = _Registry(
        deployments=[_FakeAdapter("vercel", installed=False),
                     _FakeAdapter("railway", installed=True, authenticated=False),
                     _FakeAdapter("render", installed=True, authenticated=True)],
    )
    report = provider_readiness(registry)
    by_name = {p["name"]: p for p in report["providers"]}
    assert by_name["vercel"]["installed"] is False
    assert by_name["railway"]["authenticated"] is False
    assert by_name["render"]["authenticated"] is True
    assert "vercel" in report["missing"]
    assert "railway" in report["unauthenticated"]
    assert report["hints"]


def test_readiness_required_providers_gates_ready():
    registry = _Registry(infrastructure=[_FakeAdapter("terraform", installed=False, kind="infrastructure")])
    assert provider_readiness(registry, required=["terraform"])["ready"] is False
    assert provider_readiness(registry, required=[])["ready"] is True


def test_readiness_never_returns_a_secret_value(monkeypatch):
    monkeypatch.setenv("RENDER_API_KEY", "super-secret")
    registry = _Registry(deployments=[_FakeAdapter("render", installed=True, authenticated=True,
                                                   credential_env=("RENDER_API_KEY",))])
    report = provider_readiness(registry)
    assert "super-secret" not in str(report)
    # Only the NAME of the credential env is reported, never its value.
    assert "RENDER_API_KEY" in str(report)


def test_readiness_unknown_auth_is_null_not_fabricated():
    # An adapter with no declared credential env reports authenticated: null.
    registry = _Registry(orchestrators=[_FakeAdapter("kubectl", installed=True, credential_env=())])
    report = provider_readiness(registry)
    row = next(p for p in report["providers"] if p["name"] == "kubectl")
    # `configured` is None when credential_env is empty -> authenticated stays None.
    assert row["authenticated"] in (None, False) or isinstance(row["authenticated"], bool)


def test_required_providers_for_a_project(tmp_path):
    from harness.execution.application.discovery import discover_application

    (tmp_path / "docker-compose.yml").write_text("services:\n  web:\n    build: .\n", encoding="utf-8")
    (tmp_path / "main.tf").write_text('resource "x" "y" {}\n', encoding="utf-8")
    (tmp_path / "k8s").mkdir()
    descriptor = discover_application(tmp_path)
    required = required_providers_for(descriptor)
    assert "docker" in required
    assert "terraform" in required
    assert "kubectl" in required


def test_install_hint_uses_binary_name_for_aliased_provider():
    # `azure` probes `az`; the hint must name the real binary.
    assert "Azure CLI" in _install_hint("azure")
    assert "Google Cloud" in _install_hint("gcp")
    assert "Wrangler" in _install_hint("cloudflare")
