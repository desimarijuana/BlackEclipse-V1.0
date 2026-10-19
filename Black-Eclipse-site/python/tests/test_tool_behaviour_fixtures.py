"""Round 4 (W13): per-family tool BEHAVIOUR fixtures (ADR-H214).

The metadata audit (`test_tool_contracts.py`) proves every advertised tool
DECLARES a contract; these tests prove a representative tool per audited family
actually RUNS through the ONE `ToolRegistry` and answers in the shape it
advertises. A family whose fixture fails is a family whose tools are not
honestly available, and a fixture tool missing from the production registry is
an advertised family that does not exist.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.tool_fixtures import (
    AUDITED_FAMILIES,
    FAMILY_FIXTURES,
    fixture_report,
    run_all_fixtures,
)


def test_every_audited_family_declares_a_fixture():
    report = fixture_report()
    assert report["complete"], report
    assert set(report["families"]) == set(AUDITED_FAMILIES)
    assert all(report["tools"].values())


@pytest.mark.asyncio
async def test_every_family_fixture_runs_its_tool_for_real():
    results = await run_all_fixtures()
    failures = [row for row in results if not row["ok"]]
    assert not failures, failures
    assert {row["family"] for row in results} == set(AUDITED_FAMILIES)
    # Every fixture produced a detail dict — an empty "ok" is not a measurement.
    assert all(row.get("detail") for row in results), results


@pytest.fixture(scope="module")
def service_registry():
    from harness.persistence import AgentMemoryStore
    from harness.service import AgenticService

    directory = tempfile.mkdtemp(prefix="be-fixtures-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        yield AgenticService(store=store).registry
    finally:
        store.close()


def test_each_fixture_tool_is_on_the_production_registry(service_registry):
    """A fixture proves a family only if its representative tool is actually
    advertised by the production registry."""
    missing = [fixture.tool for fixture in FAMILY_FIXTURES if service_registry.get(fixture.tool) is None]
    assert missing == [], f"fixture tools not advertised: {missing}"
