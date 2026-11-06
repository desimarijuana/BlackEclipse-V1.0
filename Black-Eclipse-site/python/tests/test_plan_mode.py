"""The composer's `planMode` preference — a prompt nudge, never a grant.

"on" appends one block telling the model to lay out a plan and wait for
approval before starting the work. "off"/"auto" add nothing. The block is
guidance only: it never hard-blocks a tool call or authorizes an effect.
"""

from __future__ import annotations

from types import SimpleNamespace

from harness.plan_mode import (
    PLAN_MODE_BLOCK,
    apply_plan_context,
    plan_mode_block,
)


def _request(mode: object | None) -> SimpleNamespace:
    context = {"planMode": mode} if mode is not None else {}
    return SimpleNamespace(input=SimpleNamespace(context=context))


def test_off_and_auto_add_nothing():
    # Only the exact "on" opts in; a near-miss must never activate the nudge.
    for mode in (None, "auto", "off", "on "):
        assert apply_plan_context(_request(mode), {"create_plan"}, "BASE") == "BASE"


def test_on_appends_the_block():
    out = apply_plan_context(_request("on"), {"create_plan"}, "BASE")
    assert out == f"BASE\n\n{PLAN_MODE_BLOCK}"
    assert "<plan_mode>" in out
    assert "wait" in out
    assert "approv" in out


def test_on_does_not_require_the_task_tools():
    # The plan can be written in the reply when the durable tools are absent.
    assert apply_plan_context(_request("on"), {"get_quote"}, "BASE") == f"BASE\n\n{PLAN_MODE_BLOCK}"


def test_a_malformed_request_never_raises():
    assert apply_plan_context(object(), {"create_plan"}, "BASE") == "BASE"


def test_block_is_the_single_source():
    assert plan_mode_block() == PLAN_MODE_BLOCK
