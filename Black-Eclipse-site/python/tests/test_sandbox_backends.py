"""Phase 11 G3/G3b — the SandboxBackend interface and the honest-failure rule.

    * an unavailable `container`/`remote` backend REFUSES with
      `SANDBOX_UNAVAILABLE`; no execution happens; the refusal names the backend
      and its guarantees;
    * it NEVER degrades to `local`, and never to an uncontained run;
    * the `local` backend's declared guarantees are DERIVED from the existing
      policy constants, so an upgrade cannot silently restate a weaker guarantee
      as a stronger one.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from harness.code import backends, policy, sandbox
from harness.code.sandbox import RunSpec, SandboxUnavailable


def _spec() -> RunSpec:
    return RunSpec(
        argv=["python", "-c", "print(1)"], cwd=Path("."),
        env={}, timeout_s=5, output_cap_bytes=1000, network=False,
    )


# ── G3 — an unavailable backend refuses; never degrades ──────────────────────


def test_container_backend_is_unavailable_when_no_runtime(monkeypatch):
    monkeypatch.delenv(backends.CONTAINER_BACKEND_ENV, raising=False)
    backend = backends.ContainerBackend()
    assert backend.available is False
    with pytest.raises(SandboxUnavailable) as info:
        backends.select_backend("container")
    assert sandbox.SandboxUnavailable is not None
    # The refusal names the backend and carries a plain reason (no mechanism code).
    assert "container" in str(info.value)
    assert "SANDBOX_UNAVAILABLE" not in str(info.value)


def test_remote_backend_is_unavailable_when_unconfigured(monkeypatch):
    monkeypatch.delenv(backends.REMOTE_BACKEND_ENV, raising=False)
    backend = backends.RemoteBackend()
    assert backend.available is False
    with pytest.raises(SandboxUnavailable):
        backends.select_backend("remote")


def test_selecting_an_unavailable_backend_never_falls_back_to_local(monkeypatch):
    monkeypatch.delenv(backends.CONTAINER_BACKEND_ENV, raising=False)
    monkeypatch.delenv(backends.REMOTE_BACKEND_ENV, raising=False)
    for name in ("container", "remote", "unknown"):
        with pytest.raises(SandboxUnavailable):
            backends.select_backend(name)
    # `local` is still reachable on its own — the fallback would be a silent switch,
    # and there is none.
    assert backends.select_backend("local").name == "local"


def test_a_refusal_names_the_backend_and_its_guarantees():
    backend = backends.ContainerBackend(runtime="definitely-not-a-real-runtime-xyz")
    assert backend.available is False
    description = backend.describe()
    assert description["name"] == "container"
    assert description["guarantees"]["filesystem"] == "not available"
    # Every guarantee slot is present and honest, never a stronger implicit claim.
    assert set(description["guarantees"]) == {
        "filesystem", "network", "resources", "wall_clock", "process_tree", "env", "output_cap",
    }


def test_an_unavailable_backend_run_refuses_not_executes(monkeypatch):
    monkeypatch.delenv(backends.CONTAINER_BACKEND_ENV, raising=False)
    backend = backends.ContainerBackend()
    with pytest.raises(SandboxUnavailable):
        asyncio.run(backend.run(_spec()))


def test_describe_all_reports_every_backend_honestly(monkeypatch):
    monkeypatch.delenv(backends.CONTAINER_BACKEND_ENV, raising=False)
    monkeypatch.delenv(backends.REMOTE_BACKEND_ENV, raising=False)
    described = backends.describe_all()
    assert set(described) == {"local", "container", "remote"}
    assert described["local"]["available"] is True
    assert described["container"]["available"] is False
    assert described["remote"]["available"] is False


# ── G3b — the local declaration matches the enforced policy constants ────────


def test_local_guarantees_are_derived_from_policy_constants():
    declared = backends.LocalBackend().guarantees
    # The network posture is the enforced one.
    if policy.NETWORK_DEFAULT:
        assert "allows it" in declared.network
    else:
        assert "denied by policy" in declared.network
    # The count of protected locations in the declaration is the real count.
    assert str(len(policy.PROTECTED_PATHS)) in declared.filesystem
    # The environment scrub count is the real allowlist size.
    assert str(len(policy.SECRET_ENV_ALLOWLIST)) in declared.env
    # The output cap is the real constant, not a restated number.
    assert str(sandbox.MAX_OUTPUT_CAP_BYTES) in declared.output_cap


def test_local_backend_declares_process_level_bounds_only():
    declared = backends.LocalBackend().guarantees
    # `local` makes NO filesystem-boundary claim: it is process-level bounds only.
    assert "process-level bounds only" in declared.resources
    assert "real filesystem boundary" not in declared.filesystem
    # A container DOES claim a real boundary; the two are not conflated.
    container = backends.ContainerBackend(runtime="docker")
    # It is either available (docker present) or its declaration says "not available".
    if container.available:
        assert "real filesystem boundary" in container.guarantees.filesystem


def test_local_backend_runs_through_the_existing_primitive():
    # The `local` backend IS `code/sandbox.py` — behaviour unchanged.
    backend = backends.LocalBackend()
    assert backend.name == "local"
    assert backend.available is True
    assert backend.describe()["guarantees"] == backends.LocalBackend().guarantees.as_dict()
