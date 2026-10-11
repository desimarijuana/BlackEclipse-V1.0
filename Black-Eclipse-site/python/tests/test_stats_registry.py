"""Registry contract — the fourteen tools are present, structured and dispatchable."""

from __future__ import annotations

import pytest

from harness.stats import TOOL_NAMES, TOOLS, run_tool, run_tool_safe
from harness.stats.base import StatsError
from harness.stats.registry import catalog


EXPECTED = {
    "calculate_returns", "calculate_volatility", "calculate_correlation",
    "calculate_beta", "calculate_drawdown", "calculate_stationarity",
    "calculate_cointegration", "calculate_autocorrelation", "calculate_regression",
    "calculate_regime", "build_features", "detect_outliers", "analyze_lead_lag",
    "calculate_information_coefficient",
}


def test_all_fourteen_tools_registered():
    assert set(TOOL_NAMES) == EXPECTED
    assert len(TOOL_NAMES) == 14


def test_every_tool_has_description_and_schema():
    for name, spec in TOOLS.items():
        assert spec.description.strip()
        assert isinstance(spec.input_schema, dict)
        assert spec.input_schema.get("type") == "object"


def test_unknown_tool_raises():
    with pytest.raises(StatsError) as exc:
        run_tool("no_such_tool", {})
    assert exc.value.http_status == 404


def test_run_tool_safe_returns_error_envelope():
    out = run_tool_safe("calculate_returns", {"values": []})
    assert out["status"] == "error"
    assert out["errors"][0]["code"] == "INSUFFICIENT_DATA"


def test_response_envelope_shape():
    out = run_tool("calculate_returns", {"values": [1.0, 2.0, 3.0]})
    for key in ("status", "tool", "toolVersion", "parameters", "summary", "results",
                "diagnostics", "warnings", "errors", "provenance", "executionMetadata",
                "artifactReferences"):
        assert key in out
    assert out["provenance"]["toolVersion"] == out["toolVersion"]


def test_catalog_lists_all():
    entries = catalog()
    assert {e["name"] for e in entries} == EXPECTED


def test_registers_on_harness_registry():
    from harness.tools import ToolRegistry
    from harness.stats.tools import STATS_TOOLS, register_stats_tools

    registry = ToolRegistry()
    names = register_stats_tools(registry)
    assert set(names) == set(STATS_TOOLS)
    assert "stats_capabilities" in names
    for name in EXPECTED:
        assert name in registry._tools  # noqa: SLF001 - direct registry inspection
