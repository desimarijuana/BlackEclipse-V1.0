"""G13: scheduled prompts name capabilities, never tool ids."""

from __future__ import annotations

from harness.agents import get_agent
from harness.jobs import prompt_policy as PP
from harness.jobs.templates import JOB_TEMPLATES


def _real_tool_names() -> set[str]:
    return set(get_agent("eclipse-agent").tools or [])


def test_the_agent_really_exposes_tool_names_to_check_against():
    names = _real_tool_names()
    assert len(names) > 50
    assert "web_search" in names or "tool_search" in names


def test_every_bundled_template_prompt_names_capabilities_only():
    problems = PP.lint_templates(JOB_TEMPLATES, _real_tool_names())
    assert problems == [], problems


def test_a_prompt_that_names_a_tool_is_flagged_with_a_position():
    findings = PP.lint_prompt("Use get_sec_filings for ACME and summarise it.", {"get_sec_filings"})
    assert findings and findings[0]["tool"] == "get_sec_filings"
    assert findings[0]["index"] == 4
    assert "capability" in findings[0]["hint"]


def test_capability_language_is_clean():
    text = "Summarise new regulatory filings and overnight news for these holdings."
    assert PP.is_clean(text, {"get_sec_filings", "web_search", "stock_news"}) is True


def test_matching_is_by_whole_token_not_substring():
    # a tool called `news` must not match the ordinary word inside `news_digest`
    assert PP.lint_prompt("read the news_digest", {"news"}) == []
    assert PP.lint_prompt("read the news", {"news"})[0]["tool"] == "news"


def test_common_english_verbs_are_not_treated_as_tool_mentions():
    for verb in ("read", "write", "open", "close", "get", "set", "run"):
        assert PP.lint_prompt(f"please {verb} the report", {verb}) == []


def test_empty_or_blank_prompts_are_clean():
    assert PP.is_clean("", {"web_search"}) is True
    assert PP.is_clean("   ", {"web_search"}) is True


def test_lint_templates_reports_the_template_and_field():
    class _T:
        id = "demo"
        target = {"objective": "call web_search then summarise"}

    problems = PP.lint_templates([_T()], {"web_search"})
    assert problems[0]["template"] == "demo"
    assert problems[0]["field"] == "objective"
