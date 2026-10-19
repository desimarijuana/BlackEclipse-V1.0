"""Round 4 (W13): tool capability contracts — a registered name is not proof.

`check_tool_contract` verifies one tool's metadata (identity, typed input,
permission/risk vocabulary, bounded timeout) and names advisory gaps; the
full-registry audit is the release gate: every advertised tool passes its hard
contract, or it is named. Warnings (untyped output, undeclared effect metadata)
are reported, never silently tolerated and never blocking.
"""

from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace

import pytest

from harness.tool_contracts import (
    MAX_TIMEOUT_MS,
    audit_registry,
    check_tool_contract,
)


def _tool(**overrides) -> SimpleNamespace:
    base = dict(
        name="sample_tool",
        description="A tool that does a describable thing for the caller.",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
        output_schema={"type": "object", "properties": {}},
        permission="read",
        risk="low",
        timeout_ms=20_000,
        effect=None,
        version="1.0.0",
        deprecated=False,
        replacement=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_a_well_formed_tool_passes_with_no_warnings():
    contract = check_tool_contract(_tool())
    assert contract.ok
    assert contract.warnings == []
    assert contract.to_dict()["health"] == "registered"


@pytest.mark.parametrize(
    "overrides,fragment",
    [
        ({"name": "Bad.Name"}, "snake_case"),
        ({"description": "short"}, "description"),
        ({"input_schema": None}, "typed JSON object"),
        ({"input_schema": {"type": "object"}}, "properties"),
        ({"permission": "admin"}, "permission"),
        ({"risk": "critical"}, "risk"),
        ({"timeout_ms": 0}, "timeout_ms"),
        ({"timeout_ms": MAX_TIMEOUT_MS + 1}, "timeout_ms"),
    ],
)
def test_each_hard_rule_is_enforced(overrides, fragment):
    contract = check_tool_contract(_tool(**overrides))
    assert not contract.ok
    assert any(fragment in violation for violation in contract.violations)


def test_advisory_gaps_are_warnings_not_failures():
    contract = check_tool_contract(_tool(
        permission="write", output_schema=None, effect=None,
        deprecated=True, replacement=None,
    ))
    assert contract.ok
    joined = " ".join(contract.warnings)
    assert "effect metadata" in joined
    assert "output schema" in joined
    assert "replacement" in joined


@pytest.fixture(scope="module")
def service_registry():
    from harness.persistence import AgentMemoryStore
    from harness.service import AgenticService

    directory = tempfile.mkdtemp(prefix="be-contracts-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        yield AgenticService(store=store).registry
    finally:
        store.close()


def test_every_advertised_tool_passes_its_contract(service_registry):
    """The release gate: no advertised tool fails its hard contract."""
    report = audit_registry(service_registry, limit=100)
    assert report["violationCount"] == 0, report["violations"]
    assert report["total"] >= 800
    assert report["ok"] == report["total"]
    # The permission vocabulary is actually exercised.
    assert set(report["byPermission"]) == {"read", "write", "external_action"}


def test_the_audit_reports_warnings_without_gating(service_registry):
    report = audit_registry(service_registry, limit=5)
    # Advisory gaps are counted (untyped outputs are the common case), not fatal.
    assert report["warningCount"] > 0
    assert report["violationCount"] == 0


def test_an_audit_of_an_unenumerable_registry_is_reported_not_guessed():
    class _Broken:
        def list(self):
            raise RuntimeError("boom")

    report = audit_registry(_Broken())
    assert report["total"] == 0
    assert report["error"]
