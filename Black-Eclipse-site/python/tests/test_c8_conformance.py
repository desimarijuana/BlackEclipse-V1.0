"""C8.1: the conformance suite is a runnable gate with a verified manifest."""

from __future__ import annotations

import json

from harness.evaluation.conformance import MANIFEST, load_manifest, run_conformance
from harness.evaluation.conformance.__main__ import main
from harness.evaluation.conformance.cases import (
    contract_event_vocabulary,
    contract_plugin_sdk,
    contract_slo_report,
    contract_tool_manifest,
    fault_deadline_blocks_retry,
    fault_duplicate_effect,
    fault_no_retry_400,
    fault_no_retry_cancel,
    fault_retry_429,
    fault_retry_500,
    fault_retry_disconnect,
    golden_run_step_tool,
)


def test_the_suite_passes_and_every_case_is_declared():
    suite = run_conformance()
    assert suite.ok, suite.to_dict()
    assert suite.missing == [] and suite.extra == []
    declared = {case["id"] for case in load_manifest()["cases"]}
    produced = {case.id for case in suite.cases}
    assert produced == declared
    assert len(produced) == 28


def test_quick_mode_skips_without_reporting_a_missing_case():
    suite = run_conformance(quick=True)
    assert suite.ok, suite.to_dict()
    assert suite.missing == []
    assert all(case.id != "contract.tool_manifest" for case in suite.cases)


def test_a_missing_declared_case_fails_the_gate(tmp_path):
    path = tmp_path / "conformance.json"
    path.write_text(json.dumps({"version": 1, "cases": [
        {"id": "fault.retry_429", "kind": "fault"},
        {"id": "does.not.exist", "kind": "fault"},
    ]}), encoding="utf-8")
    suite = run_conformance(manifest_path=path)
    assert suite.ok is False
    assert suite.missing == ["does.not.exist"]


def test_each_fault_case_is_real():
    for factory in (
        fault_retry_429, fault_retry_500, fault_retry_disconnect,
        fault_no_retry_400, fault_no_retry_cancel,
        fault_deadline_blocks_retry, fault_duplicate_effect,
    ):
        result = factory()
        assert result.ok, (result.id, result.detail)
        assert result.kind == "fault"


def test_the_golden_trace_has_the_expected_tree():
    result = golden_run_step_tool()
    assert result.ok, result.detail
    assert result.evidence["parentage"] is True
    assert result.evidence["terminal"] is True
    assert "eclipse.run" in result.evidence["spans"]
    assert "eclipse.step" in result.evidence["spans"]


def test_contract_cases_pass():
    for factory in (
        contract_event_vocabulary, contract_tool_manifest,
        contract_slo_report, contract_plugin_sdk,
    ):
        result = factory()
        assert result.ok, (result.id, result.detail)


def test_the_manifest_file_is_versioned():
    manifest = load_manifest(MANIFEST)
    assert manifest["version"] == 1
    assert len(manifest["cases"]) >= 28


def test_the_cli_returns_zero_and_writes_json(tmp_path, capsys):
    out = tmp_path / "report.json"
    assert main(["--json", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["total"] == 28
    assert "conformance: PASS" in capsys.readouterr().out
