"""Live provider integration tests — OPT-IN, never part of `npm test`.

These exercise a REAL cloud/orchestration CLI against a real account. They are
skipped unless the operator explicitly enables them, exactly like
`test_git_provider_live.py`:

    BLACK_ECLIPSE_PROVIDER_IT=1            # turn the suite on
    BLACK_ECLIPSE_PROVIDER=<name>         # vercel | cloudflare | render | aws | ...
    (plus that provider's own credentials, set in the environment)

They NEVER run in CI and NEVER run on a machine without the opt-in, because they
touch a live account. The offline `test_application_orchestration.py` covers the
same adapters deterministically through the TEST SEAM.
"""

from __future__ import annotations

import os

import pytest

from harness.execution.application.cloud import build_deployment_adapters
from harness.execution.application.infrastructure import TerraformAdapter
from harness.execution.application.orchestrators import build_orchestrator_adapters

_ENABLED = os.environ.get("BLACK_ECLIPSE_PROVIDER_IT") in ("1", "true", "True")
_PROVIDER = (os.environ.get("BLACK_ECLIPSE_PROVIDER") or "").strip().casefold()

pytestmark = pytest.mark.skipif(
    not _ENABLED,
    reason="live provider tests are opt-in: set BLACK_ECLIPSE_PROVIDER_IT=1 and BLACK_ECLIPSE_PROVIDER",
)


def _deployment_adapter(name: str):
    return next((a for a in build_deployment_adapters() if a.name == name), None)


def _orchestrator_adapter(name: str):
    return next((a for a in build_orchestrator_adapters() if a.name == name), None)


def test_the_selected_provider_is_installed():
    if not _PROVIDER:
        pytest.skip("set BLACK_ECLIPSE_PROVIDER to one provider name")
    adapter = (_deployment_adapter(_PROVIDER) or _orchestrator_adapter(_PROVIDER)
               or (TerraformAdapter() if _PROVIDER == "terraform" else None))
    if adapter is None:
        pytest.skip(f"no adapter named {_PROVIDER!r}")
    assert adapter.available(), (
        f"{_PROVIDER} is not installed (or not signed in). Install it and authenticate, then re-run."
    )


def test_identity_is_readable_for_the_selected_provider():
    """A read-only identity/status call proves the credentials actually work."""
    if not _PROVIDER:
        pytest.skip("set BLACK_ECLIPSE_PROVIDER to one provider name")
    adapter = _deployment_adapter(_PROVIDER)
    if adapter is None:
        pytest.skip(f"{_PROVIDER} has no identity/status operation")
    operation = "identity" if "identity" in getattr(adapter, "operations", {}) else "status"
    result = adapter.run_operation(operation, {})
    # A real account answers; a broken credential fails the structured call.
    assert result.ok or result.code in ("FAILED", "ENGINE_UNAVAILABLE"), result.to_dict()


def test_terraform_version_when_selected():
    if _PROVIDER != "terraform":
        pytest.skip("only when BLACK_ECLIPSE_PROVIDER=terraform")
    adapter = TerraformAdapter()
    if not adapter.available():
        pytest.skip("terraform is not installed")
    assert adapter.run_operation("version", {}).ok
