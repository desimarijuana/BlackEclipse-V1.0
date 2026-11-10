"""The live-chat grader checks a real answer/tool trace against the contract."""

from __future__ import annotations

from harness.quant_chat_eval import grade_answer, grade_records


def test_a_complete_build_answer_passes() -> None:
    result = grade_answer(
        "build a gold momentum strategy",
        "Walk-forward out-of-sample Sharpe 1.2 after commission and slippage.\n\n"
        '```eclipse-response {"blocks":[{"type":"chart","chartType":"auto",'
        '"quant":{"experimentId":"exp_abcd1234","figure":"equity"}}]}```\n\n'
        "Artifacts: exp_abcd1234",
        ["model_catalog", "run_backtest", "run_walk_forward"],
    )
    assert result["passed"] is True, result
    assert result["artifactLine"] is True


def test_a_build_without_catalog_or_artifact_line_fails() -> None:
    result = grade_answer(
        "build a gold momentum strategy",
        "The strategy looks good.",
        ["run_backtest"],
    )
    assert result["passed"] is False
    assert any("model_catalog" in failure for failure in result["failures"])
    assert any("Artifacts" in failure for failure in result["failures"])


def test_a_reuse_answer_must_use_the_catalog_and_the_line() -> None:
    result = grade_answer(
        "reuse the model from last week",
        "Use mdl_gold@1.\n\nArtifacts: mdl_gold",
        ["model_catalog"],
    )
    assert result["passed"] is True, result

    bad = grade_answer("reuse the model from last week", "Use it.", [])
    assert bad["passed"] is False


def test_grade_records_summarises_failures() -> None:
    report = grade_records([
        {"query": "reuse the model from last week", "output": "Use it.", "toolNames": []},
        {
            "query": "reuse the model from last week",
            "output": "Use mdl_gold@1.\n\nArtifacts: mdl_gold",
            "toolNames": ["model_catalog"],
        },
    ])
    assert report["total"] == 2
    assert report["passed"] == 1
    assert len(report["failures"]) == 1
