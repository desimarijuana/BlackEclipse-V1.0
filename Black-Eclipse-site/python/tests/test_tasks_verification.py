"""Round 4 (W8.4/W14): the task-type verifier — completion is evidence, not prose.

These pin the dispatch rule (no taskType ⇒ no verifier, pre-W8 behavior), each
built-in verifier's accept/reject boundary against the REAL evidence shapes the
runtime writes, the deliverable-coverage rule, and the honest refusal for an
unknown verifier or a crashing one.

W14 added the sixth task type (`data` ⇒ a reproducible calculation) and made
every verifier read what the runtime actually records: the ordinary run's
collected research blob, the gated run's validation/receipt records, the
recorded document sections and the run's analysis records. A plausible but
incomplete answer — confident prose, a source with no evidence, a partial
answer that hides its gap, a workflow that produced nothing, a number with no
recorded computation — is REJECTED.
"""

from __future__ import annotations

import pytest

from harness.tasks import verification as verification_module
from harness.tasks.goal import classify_task_type, infer_acceptance, parse_required_sections
from harness.tasks.model import GoalContract, Task, TaskType
from harness.tasks.verification import TaskVerification, verify_task

NOW = "2026-01-01T00:00:00+00:00"


def _task(task_type=None, contract=None) -> Task:
    return Task(
        id="task_x", title="t", task_type=task_type, goal_contract=contract,
        created_at=NOW, updated_at=NOW,
    )


def _record(command_class: str, exit_code: int) -> dict:
    return {
        "commandClass": command_class, "exitCode": exit_code,
        "outputDigest": "d" * 16, "argv": ["x"], "startedAt": NOW,
    }


CODE_CONTRACT = GoalContract(
    objective="build a greeting app", deliverables=["greeting app"],
    acceptance=["the produced files exist", "tests pass"],
)


def _code_evidence(passing: bool = True) -> dict:
    return {"codeVerification": {
        "records": [_record("python_test", 0 if passing else 1)],
        "artifacts": [], "reviews": [],
    }}


def _gated_research(
    *, status: str = "accepted", claims=None, gaps=None, refs=None,
) -> dict:
    """The gated research blob the runtime really writes."""
    return {
        "research": {
            "status": status,
            "metadata": {"taskType": "financial_comparison", "asOf": "2026-01-01"},
            "validation": {
                "status": status,
                "claims": claims if claims is not None else [
                    {"text": "revenue rose", "supportStatus": "supported", "evidenceIds": ["e1"]},
                ],
                "unresolved": gaps or [],
            },
            "coverage": {"status": status, "legs": []},
            "receipt": {
                "evidenceRefs": refs if refs is not None else [
                    {"id": "e1", "kind": "filing", "url": "https://x/10-k",
                     "publishedAt": "2026-01-01", "retrievedAt": "2026-01-02"},
                ],
                "claims": claims if claims is not None else [
                    {"text": "revenue rose", "supportStatus": "supported", "evidenceIds": ["e1"]},
                ],
                "validationIssues": gaps or [],
                "temporalStatus": {"asOf": "2026-01-01"},
                "finalStatus": status,
            },
        }
    }


def _collected_research() -> dict:
    """The ordinary run's collected research blob (the other real shape)."""
    return {
        "research": {
            "status": "collected",
            "metadata": {
                "taskType": "ordinary_run",
                "citations": [{"url": "https://x/a", "title": "A"}],
                "limitations": [],
            },
            "collectedSources": [{"name": "provider", "url": "https://x/b"}],
            "failedRoutes": None,
        }
    }


def _analysis_record(**overrides) -> dict:
    record = {
        "status": "ok",
        "sourceDigest": "sha256:abc",
        "inputDigests": {"prices": "sha256:def"},
        "outputs": {"correlation": 0.42},
        "artifactCount": 0,
    }
    record.update(overrides)
    return {"analyses": {"records": [record], "count": 1}}


# ── Dispatch ──────────────────────────────────────────────────────────────────


def test_no_task_type_means_no_verifier():
    assert verify_task(_task(), status="completed") is None


def test_unknown_task_type_is_a_refusal_not_a_pass(monkeypatch):
    task = _task(task_type=TaskType.CODE, contract=CODE_CONTRACT)
    monkeypatch.setitem(verification_module._VERIFIERS, "code", None)
    verdict = verify_task(task, status="completed", evidence=_code_evidence(),
                          artifacts=[{"label": "greeting app"}])
    assert verdict is not None and not verdict.ok
    assert "no verifier is registered" in verdict.missing[0]


def test_a_crashing_verifier_refuses(monkeypatch):
    class Boom:
        task_type = "code"

        def verify(self, ctx):
            raise RuntimeError("boom")

    monkeypatch.setitem(verification_module._VERIFIERS, "code", Boom())
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=CODE_CONTRACT), status="completed",
    )
    assert verdict is not None and not verdict.ok
    assert "failed to run" in verdict.missing[0]


# ── Code ──────────────────────────────────────────────────────────────────────


def test_code_passes_with_passing_tests_and_a_matching_artifact():
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=CODE_CONTRACT),
        status="completed", evidence=_code_evidence(),
        artifacts=[{"uri": "/w/greeting.py", "kind": "file", "label": "greeting app"}],
    )
    assert verdict.ok, verdict.summary()
    names = {c.name for c in verdict.checks}
    assert {"run_completed", "tests", "deliverable:greeting app"} <= names


def test_code_rejects_failing_tests_even_when_the_run_completed():
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=CODE_CONTRACT),
        status="completed", evidence=_code_evidence(passing=False),
        artifacts=[{"label": "greeting app"}],
    )
    assert not verdict.ok
    assert "no successful tests run was recorded" in verdict.missing


def test_code_rejects_missing_artifact_for_a_declared_deliverable():
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=CODE_CONTRACT),
        status="completed", evidence=_code_evidence(), artifacts=[],
    )
    assert not verdict.ok
    assert any("greeting app" in m and "artifact" in m for m in verdict.missing)


def test_code_requires_no_test_record_when_acceptance_never_mentions_tests():
    contract = GoalContract(
        objective="build a script", deliverables=["sync script"],
        acceptance=["the produced files exist"],
    )
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=contract),
        status="completed", evidence={"codeVerification": {"records": [], "artifacts": []}},
        artifacts=[{"label": "sync script"}],
    )
    assert verdict.ok, verdict.summary()


def test_code_build_signal_requires_a_build_record():
    contract = GoalContract(
        objective="x", deliverables=["app"],
        acceptance=["the project builds without errors"],
    )
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=contract),
        status="completed", evidence=_code_evidence(), artifacts=[{"label": "app"}],
    )
    assert not verdict.ok
    assert "no successful build run was recorded" in verdict.missing


def test_code_run_status_not_completed_is_a_refusal():
    verdict = verify_task(
        _task(task_type=TaskType.CODE, contract=CODE_CONTRACT),
        status="failed", evidence=_code_evidence(),
        artifacts=[{"label": "greeting app"}],
    )
    assert not verdict.ok
    assert "the run did not complete" in verdict.missing


# ── Research ──────────────────────────────────────────────────────────────────


def test_research_passes_with_traceable_sources_and_a_supported_claim():
    contract = GoalContract(objective="r", acceptance=["claims trace to named sources"])
    verdict = verify_task(
        _task(task_type=TaskType.RESEARCH, contract=contract), status="completed",
        evidence=_gated_research(),
    )
    assert verdict.ok, verdict.summary()
    names = {c.name for c in verdict.checks}
    assert {"sources", "claim_to_evidence", "uncertainty"} <= names


def test_research_accepts_the_ordinary_collected_blob():
    contract = GoalContract(objective="r", acceptance=["claims trace to named sources"])
    verdict = verify_task(
        _task(task_type=TaskType.RESEARCH, contract=contract), status="completed",
        evidence=_collected_research(),
    )
    assert verdict.ok, verdict.summary()


def test_research_rejects_confident_prose_without_a_traceable_source():
    contract = GoalContract(objective="r", acceptance=["claims trace to named sources"])
    verdict = verify_task(
        _task(task_type=TaskType.RESEARCH, contract=contract), status="completed",
        evidence={"research": {"status": "collected", "metadata": {"citations": []}}},
    )
    assert not verdict.ok
    assert "no traceable source was recorded" in verdict.missing


def test_research_rejects_a_claim_no_evidence_backs():
    contract = GoalContract(objective="r", acceptance=["claims trace to named sources"])
    verdict = verify_task(
        _task(task_type=TaskType.RESEARCH, contract=contract), status="completed",
        evidence=_gated_research(claims=[{"text": "c", "supportStatus": "unsupported",
                                          "evidenceIds": []}]),
    )
    assert not verdict.ok
    assert "no claim is supported by recorded evidence" in verdict.missing


def test_research_rejects_a_partial_answer_that_hides_its_gap():
    contract = GoalContract(objective="r", acceptance=["claims trace to named sources"])
    verdict = verify_task(
        _task(task_type=TaskType.RESEARCH, contract=contract), status="completed",
        evidence=_gated_research(status="partial", gaps=[]),
    )
    assert not verdict.ok
    assert "a partial research answer recorded no open gap" in verdict.missing


def test_research_accepts_a_partial_answer_that_names_its_gap():
    contract = GoalContract(objective="r", acceptance=["claims trace to named sources"])
    verdict = verify_task(
        _task(task_type=TaskType.RESEARCH, contract=contract), status="completed",
        evidence=_gated_research(status="partial", gaps=["the Q3 leg is unresolved"]),
    )
    assert verdict.ok, verdict.summary()


def test_research_rejects_a_rejected_engine_verdict():
    contract = GoalContract(objective="r", acceptance=["claims trace to named sources"])
    verdict = verify_task(
        _task(task_type=TaskType.RESEARCH, contract=contract), status="completed",
        evidence=_gated_research(status="rejected"),
    )
    assert not verdict.ok
    assert "the research flow rejected the answer" in verdict.missing


# ── Finance ───────────────────────────────────────────────────────────────────


def test_finance_requires_provenance():
    contract = GoalContract(objective="f", acceptance=["financial claims carry provenance"])
    verdict = verify_task(
        _task(task_type=TaskType.FINANCE, contract=contract), status="completed",
        evidence={},
    )
    assert not verdict.ok
    assert "provenance" in verdict.missing[0]


def test_finance_requires_freshness_evidence():
    contract = GoalContract(objective="f", acceptance=["financial claims carry provenance"])
    verdict = verify_task(
        _task(task_type=TaskType.FINANCE, contract=contract), status="completed",
        evidence={"research": {"status": "collected",
                               "metadata": {"citations": [{"url": "https://x"}]}}},
    )
    assert not verdict.ok
    assert any("freshness" in m for m in verdict.missing)


def test_finance_passes_with_provenance_freshness_and_a_supported_claim():
    contract = GoalContract(objective="f", acceptance=["financial claims carry provenance"])
    verdict = verify_task(
        _task(task_type=TaskType.FINANCE, contract=contract), status="completed",
        evidence=_gated_research(),
    )
    assert verdict.ok, verdict.summary()
    names = {c.name for c in verdict.checks}
    assert {"provenance", "freshness", "claim_to_evidence"} <= names


def test_finance_rejects_a_fact_without_a_source():
    contract = GoalContract(objective="f", acceptance=["financial claims carry provenance"])
    evidence = _gated_research()
    evidence["research"]["financeAnalysis"] = {
        "facts": [{"metric": "revenue", "period": "FY2025", "source": ""}],
    }
    verdict = verify_task(
        _task(task_type=TaskType.FINANCE, contract=contract), status="completed",
        evidence=evidence,
    )
    assert not verdict.ok
    assert "a financial fact carries no source" in verdict.missing


def test_finance_defers_to_the_evidence_engine_verdict():
    contract = GoalContract(objective="f", acceptance=["financial claims carry provenance"])
    verdict = verify_task(
        _task(task_type=TaskType.FINANCE, contract=contract), status="completed",
        evidence=_gated_research(status="rejected"),
    )
    assert not verdict.ok
    assert "the evidence engine rejected the answer" in verdict.missing


# ── Document ──────────────────────────────────────────────────────────────────


def test_document_requires_a_delivered_artifact_or_document_record():
    contract = GoalContract(objective="d", acceptance=["the document artifact is delivered"])
    assert not verify_task(
        _task(task_type=TaskType.DOCUMENT, contract=contract), status="completed",
    ).ok
    assert verify_task(
        _task(task_type=TaskType.DOCUMENT, contract=contract), status="completed",
        artifacts=[{"uri": "artifact://a1", "kind": "document"}],
    ).ok


def test_document_passes_when_every_required_section_was_recorded():
    contract = GoalContract(
        objective="d", deliverables=["quarterly memo"],
        acceptance=["the document artifact is delivered",
                    "the document contains the sections: summary, methodology"],
    )
    verdict = verify_task(
        _task(task_type=TaskType.DOCUMENT, contract=contract), status="completed",
        artifacts=[{"uri": "artifact://a1", "kind": "document"}],
        evidence={"documents": {"documents": [], "authored": [
            {"kind": "authored_document", "state": "DELIVERED",
             "sectionTitles": ["Summary", "Methodology", "Risks"]},
        ]}},
    )
    assert verdict.ok, verdict.summary()


def test_document_rejects_a_missing_required_section():
    contract = GoalContract(
        objective="d", deliverables=["quarterly memo"],
        acceptance=["the document contains the sections: summary, methodology"],
    )
    verdict = verify_task(
        _task(task_type=TaskType.DOCUMENT, contract=contract), status="completed",
        artifacts=[{"uri": "artifact://a1", "kind": "document"}],
        evidence={"documents": {"authored": [
            {"kind": "authored_document", "state": "DELIVERED", "sectionTitles": ["Summary"]},
        ]}},
    )
    assert not verdict.ok
    assert any("methodology" in m for m in verdict.missing)


def test_document_rejects_a_document_that_recorded_no_structure():
    contract = GoalContract(
        objective="d", deliverables=["quarterly memo"],
        acceptance=["the document contains the sections: summary"],
    )
    verdict = verify_task(
        _task(task_type=TaskType.DOCUMENT, contract=contract), status="completed",
        artifacts=[{"uri": "artifact://a1", "kind": "document"}],
    )
    assert not verdict.ok
    assert any("recorded no sections" in m for m in verdict.missing)


# ── Workflow ──────────────────────────────────────────────────────────────────


def test_workflow_requires_observed_steps_and_an_observable_state():
    contract = GoalContract(objective="w", acceptance=["the workflow completed with an observable result"])
    task = _task(task_type=TaskType.WORKFLOW, contract=contract)
    assert not verify_task(task, status="completed", metrics={"toolCalls": 0}).ok
    # Steps alone are not a resulting state: a run that called one tool and
    # produced nothing must not pass (the run id is not a result).
    assert not verify_task(task, status="completed", metrics={"toolCalls": 3}).ok
    verdict = verify_task(
        task, status="completed", metrics={"toolCalls": 3},
        artifacts=[{"uri": "artifact://w1", "kind": "document"}],
    )
    assert verdict.ok, verdict.summary()


def test_workflow_accepts_a_recorded_analysis_as_its_state():
    contract = GoalContract(objective="w", acceptance=["the workflow completed with an observable result"])
    verdict = verify_task(
        _task(task_type=TaskType.WORKFLOW, contract=contract), status="completed",
        metrics={"toolCalls": 2}, evidence=_analysis_record(),
    )
    assert verdict.ok, verdict.summary()


# ── Data (W14) ────────────────────────────────────────────────────────────────


def test_data_classification_keeps_the_other_classes():
    assert classify_task_type("analyze the correlation in this dataset") is TaskType.DATA
    assert classify_task_type("compare the revenue of A and B") is TaskType.RESEARCH
    assert classify_task_type("write a report on the market") is TaskType.DOCUMENT
    assert classify_task_type("build a stock screener app") is TaskType.CODE
    assert classify_task_type("schedule a daily portfolio review") is TaskType.WORKFLOW


def test_data_acceptance_line_names_reproducibility():
    lines = infer_acceptance("compute the correlation", TaskType.DATA)
    assert lines == ["the calculation is reproducible from its recorded inputs"]


def test_data_requires_a_reproducible_calculation():
    contract = GoalContract(
        objective="d", acceptance=["the calculation is reproducible from its recorded inputs"],
    )
    verdict = verify_task(
        _task(task_type=TaskType.DATA, contract=contract), status="completed",
    )
    assert not verdict.ok
    assert "no reproducible calculation was recorded" in verdict.missing


def test_data_passes_with_a_recorded_analysis_that_pinned_its_inputs():
    contract = GoalContract(
        objective="d", acceptance=["the calculation is reproducible from its recorded inputs"],
    )
    verdict = verify_task(
        _task(task_type=TaskType.DATA, contract=contract), status="completed",
        evidence=_analysis_record(),
    )
    assert verdict.ok, verdict.summary()


def test_data_rejects_an_analysis_without_pinned_inputs():
    contract = GoalContract(
        objective="d", acceptance=["the calculation is reproducible from its recorded inputs"],
    )
    verdict = verify_task(
        _task(task_type=TaskType.DATA, contract=contract), status="completed",
        evidence=_analysis_record(inputDigests={}),
    )
    assert not verdict.ok
    assert "no reproducible calculation was recorded" in verdict.missing


def test_data_accepts_a_research_calculation_record():
    contract = GoalContract(
        objective="d", acceptance=["the calculation is reproducible from its recorded inputs"],
    )
    evidence = {"research": {"status": "accepted", "metadata": {"calculations": [{
        "calculationId": "c1", "version": "1.0.0", "formula": "pearson(xs, ys)",
        "metric": "correlation", "value": 0.4,
        "inputs": [{"name": "xs", "value": [1, 2]}], "inputEvidenceIds": ["e1"],
        "status": "OK",
    }]}}}
    verdict = verify_task(
        _task(task_type=TaskType.DATA, contract=contract), status="completed",
        evidence=evidence,
    )
    assert verdict.ok, verdict.summary()


# ── Section parsing ───────────────────────────────────────────────────────────


def test_required_sections_are_parsed_only_from_an_explicit_list():
    assert parse_required_sections("a report with sections: risks, methodology") == [
        "risks", "methodology",
    ]
    assert parse_required_sections("a report with sections risks and methodology") == [
        "risks", "methodology",
    ]
    assert parse_required_sections("a report with sections") == []
    assert parse_required_sections("summarise the document") == []


def test_intake_records_the_required_sections_for_a_document():
    lines = infer_acceptance(
        "write a quarterly memo with sections: summary, risks", TaskType.DOCUMENT,
    )
    assert "the document contains the sections: summary, risks" in lines


# ── General ───────────────────────────────────────────────────────────────────


def test_general_requires_a_recorded_result():
    contract = GoalContract(objective="g", acceptance=["the requested result is delivered"])
    task = _task(task_type=TaskType.GENERAL, contract=contract)
    assert not verify_task(task, status="completed").ok
    assert verify_task(task, status="completed", artifacts=[{"uri": "artifact://a"}]).ok


def test_verification_summary_is_bounded_and_plain():
    verdict = TaskVerification("code", [], ["a", "b", "c", "d", "e", "f"])
    assert verdict.summary().startswith("verification failed:")
    assert verdict.summary().count(";") == 4  # five named, never the whole log
