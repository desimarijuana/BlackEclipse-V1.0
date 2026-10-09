"""Per-tenant physical store isolation."""

from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-sec-ts-"), "agent-memory.db"),
)

from harness.security.tenant_store import (
    TenantIdError,
    TenantStoreRegistry,
    default_tenant_root,
    normalize_tenant,
)


def test_normalize_tenant_rejects_unsafe_ids():
    assert normalize_tenant("acme") == "acme"
    assert normalize_tenant(" acme-1.2 ") == "acme-1.2"
    assert normalize_tenant(None) is None
    assert normalize_tenant("") is None
    for bad in ("../evil", "a/b", "a\\b", "..", ".", "x" * 100, "a b"):
        with pytest.raises(TenantIdError):
            normalize_tenant(bad)


def test_path_for_is_under_the_root(tmp_path):
    registry = TenantStoreRegistry(root=str(tmp_path))
    assert registry.path_for("acme") == os.path.join(str(tmp_path), "acme", "agent-memory.db")
    assert registry.path_for_safe("../evil") is None


def test_distinct_tenants_get_distinct_stores(tmp_path):
    registry = TenantStoreRegistry(root=str(tmp_path))
    acme = registry.store_for("acme")
    beta = registry.store_for("beta")
    assert acme.path != beta.path
    acme.create_run("run-a", "agent", {"query": "a"})
    beta.create_run("run-b", "agent", {"query": "b"})
    # Physical separation: beta cannot see acme's run at all.
    acme_runs = {r["id"] for r in acme.list_runs(50)}
    beta_runs = {r["id"] for r in beta.list_runs(50)}
    assert "run-a" in acme_runs and "run-b" not in acme_runs
    assert "run-b" in beta_runs and "run-a" not in beta_runs


def test_registry_caches_and_closes(tmp_path):
    registry = TenantStoreRegistry(root=str(tmp_path))
    assert registry.store_for("acme") is registry.store_for("acme")
    assert registry.known_tenants() == ["acme"]
    assert registry.close("acme") is True
    assert registry.known_tenants() == []


def test_env_override_for_root(monkeypatch):
    monkeypatch.setenv("BLACK_ECLIPSE_TENANT_DB_DIR", "/custom/tenants")
    assert default_tenant_root() == "/custom/tenants"
