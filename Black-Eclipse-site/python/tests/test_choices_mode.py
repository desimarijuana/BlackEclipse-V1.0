"""The composer's `choicesMode` preference — a prompt nudge, never a grant.

"on" appends one block telling the model to ask ONE question with concrete
options before an ambiguous turn. "off"/"auto" add nothing. The block is only
added when `clarify` is actually on the run's surface, so the model is never
told to call a tool it does not have.
"""

from __future__ import annotations

from types import SimpleNamespace

from harness.choices_mode import (
    CHOICES_MODE_BLOCK,
    apply_choices_context,
    choices_mode_block,
)


def _request(mode: object | None) -> SimpleNamespace:
    context = {"choicesMode": mode} if mode is not None else {}
    return SimpleNamespace(input=SimpleNamespace(context=context))


def test_off_and_auto_add_nothing():
    # Only the exact "on" opts in; a near-miss must never activate the nudge.
    for mode in (None, "auto", "off", "on "):
        assert apply_choices_context(_request(mode), {"clarify"}, "BASE") == "BASE"


def test_on_appends_the_block():
    out = apply_choices_context(_request("on"), {"clarify"}, "BASE")
    assert out == f"BASE\n\n{CHOICES_MODE_BLOCK}"
    assert "<choices_mode>" in out
    assert "`clarify`" in out


def test_on_is_skipped_when_clarify_is_not_available():
    assert apply_choices_context(_request("on"), {"get_quote"}, "BASE") == "BASE"


def test_on_still_works_with_no_allowlist():
    assert apply_choices_context(_request("on"), None, "BASE") == f"BASE\n\n{CHOICES_MODE_BLOCK}"


def test_a_malformed_request_never_raises():
    assert apply_choices_context(object(), {"clarify"}, "BASE") == "BASE"


def test_block_is_the_single_source():
    assert choices_mode_block() == CHOICES_MODE_BLOCK
