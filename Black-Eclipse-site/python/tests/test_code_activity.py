"""Safe tool-activity summaries (the live-stream "what" and "result" lines).

The critical property: a `detail` shows a command, a file PATH, or the CHANGED
PATHS — never file CONTENT. A `workspace_patch_apply` carrying a secret in its
`content`/`new` fields must summarize to the paths only.
"""

from __future__ import annotations

from harness.code import activity


def test_terminal_detail_is_the_command():
    assert activity.tool_detail("terminal_run", {"command": "python app.py"}) == "python app.py"


def test_command_run_detail_is_the_class():
    assert activity.tool_detail("command_run", {"command_class": "python_test"}) == "python_test"


def test_read_detail_is_the_path():
    assert activity.tool_detail("workspace_read", {"path": "src/app.py"}) == "src/app.py"


def test_patch_detail_is_paths_never_content():
    args = {"operations": [
        {"op": "create", "path": "a.py", "content": "SECRET=1"},
        {"op": "replace", "path": "b.py", "old": "x", "new": "SECRET=2"},
    ]}
    detail = activity.tool_detail("workspace_patch_apply", args)
    assert detail is not None
    assert "a.py" in detail and "b.py" in detail
    assert "SECRET" not in detail


def test_unknown_tool_has_no_detail():
    assert activity.tool_detail("market_get_quote", {"ticker": "AAPL"}) is None


def test_detail_is_bounded():
    detail = activity.tool_detail("terminal_run", {"command": "python " + "a" * 500})
    assert detail is not None
    assert len(detail) <= activity.MAX_DETAIL_CHARS


def test_analysis_detail_names_the_recipe_or_purpose_never_the_source():
    assert activity.tool_detail("analysis_run", {"recipe": "sharpe", "purpose": "p"}) == "sharpe"
    assert (
        activity.tool_detail("analysis_run", {"purpose": "portfolio drawdown"})
        == "portfolio drawdown"
    )
    detail = activity.tool_detail(
        "analysis_run", {"purpose": "volatility", "source": "SECRET = 1\nresult = SECRET"}
    )
    assert detail == "volatility"
    assert "SECRET" not in (detail or "")
    long = activity.tool_detail("analysis_run", {"purpose": "a" * 500})
    assert long is not None and len(long) <= activity.MAX_DETAIL_CHARS


def test_command_summary_reports_exit_code():
    assert activity.tool_result_summary("terminal_run", {"status": "ok", "exitCode": 0}) == "exit 0"
    assert activity.tool_result_summary("terminal_run", {"status": "timed_out"}) == "timed out"


def test_patch_summary_counts_changes():
    assert activity.tool_result_summary("workspace_patch_apply", {"applied": [{}, {}]}) == "2 change(s)"


def test_unrecognised_result_has_no_summary():
    assert activity.tool_result_summary("market_get_quote", {"price": 123}) is None
    assert activity.tool_result_summary("terminal_run", {}) is None


# ── R3-06: the computed / collected result lines ─────────────────────────────


def test_analysis_summary_counts_values_and_saved_files():
    data = {"status": "ok", "outputs": {"sharpe": 1.4}, "artifacts": [{"name": "s.csv"}]}
    assert activity.tool_result_summary("analysis_run", data) == "worked out 1 value(s), 1 saved"


def test_analysis_summary_reports_a_refusal_code():
    assert (
        activity.tool_result_summary("analysis_run", {"status": "refused", "code": "INPUT_INVALID"})
        == "refused (INPUT_INVALID)"
    )


def test_scrape_summary_reports_records_or_tables_never_content():
    assert (
        activity.tool_result_summary("web_scrape", {"rows": [{"a": "SECRET"}]})
        == "1 record(s) collected"
    )
    assert (
        activity.tool_result_summary("web_scrape", {"tables": [{"rows": []}], "text": "SECRET"})
        == "1 table(s) collected"
    )
    assert activity.tool_result_summary("web_scrape", {"collected": True, "rows": []}) == (
        "no matching records on the page"
    )
