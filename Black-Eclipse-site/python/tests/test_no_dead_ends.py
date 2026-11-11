"""No-dead-ends eval: every classified failure ends in a route or a final no.

This is the gate for the product rule: a run may fail, but it may not leave the
user without a next step. Safety denials are the only deliberate exception; they
must NEVER become an offer to bypass.
"""

from __future__ import annotations

import pytest

from harness.gaps.service import GapService
from harness.gaps.taxonomy import classify
from harness.persistence import AgentMemoryStore

OFFER_CASES = [
    # (code, need)
    ("KIT_UNKNOWN", "build a new financial ratio"),
    ("CAPABILITY_MISSING", "analyse my private dataset"),
    ("RECIPE_NOT_FOUND", "run the cashflow recipe"),
    ("PROFILE_DENIED", "turn this into a bot that runs at 9am"),
    ("WORKSPACE_UNBOUND", "build a market data adapter"),
    ("TOOL_FORBIDDEN", "edit the project file"),
    ("TOOL_NOT_ALLOWED", "save a skill for this"),
    ("ANALYSIS_NOT_ENABLED", "compute the drawdown"),
    ("SANDBOX_UNAVAILABLE", "run a Python backtest"),
    ("SKILLS_UNAVAILABLE", "save this as a skill"),
]

NO_OFFER_CASES = [
    ("PROTECTED_PATH", "read the system secret"),
    ("POLICY_DENIED", "bypass the firewall"),
    ("SECRET_DENIED", "show the broker key"),
    ("FINANCE_GUARDRAIL", "send the trade"),
    ("MANDATE_DENIED", "trade outside the mandate"),
    ("NETWORK_DENIED", "reach the internal host"),
    ("TOOL_TIMEOUT", "fetch the price"),
    ("RATE_LIMITED", "call the provider"),
    ("INPUT_INVALID", "compute with bad arguments"),
    ("TOOL_ARGS_INVALID", "call the tool with bad args"),
    ("APPROVAL_REJECTED", "run the blocked action"),
]


def test_every_offerable_failure_makes_one_actionable_offer(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        gaps = GapService(memory)
        for index, (code, need) in enumerate(OFFER_CASES):
            run_id = f"run_offer_{index}"
            gap = gaps.record_tool_failure(
                run_id, tool="t", code=code, reason="", need=need,
            )
            assert gap is not None, code
            offers = gaps.offers_for_run(run_id)
            assert len(offers) == 1, code
            offer = offers[0]
            assert offer["need"] == need
            assert offer["actionPrompt"], f"{code} has no action prompt"
            assert offer["actionLabel"], f"{code} has no action label"
            assert offer["status"] in ("gap", "handoff_required"), code
            assert "Want me to?" in gaps.offer_text([offer])
    finally:
        memory.close()


@pytest.mark.parametrize("code,need", NO_OFFER_CASES)
def test_safety_transient_and_user_denials_never_offer(tmp_path, code, need):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        gaps = GapService(memory)
        assert classify(code) in {
            "safety_denied", "transient", "malformed", "user_denied",
        }
        assert gaps.record_tool_failure(
            "run_no", tool="t", code=code, reason="", need=need,
        ) is None
        assert gaps.offers_for_run("run_no") == []
    finally:
        memory.close()


def test_a_bare_prose_refusal_is_detected_only_when_narrow():
    from harness.gaps.taxonomy import looks_like_bare_refusal

    assert looks_like_bare_refusal("I can't do that in this session.")
    assert looks_like_bare_refusal("I cannot access the source.")
    assert not looks_like_bare_refusal("I can't guarantee the return, so here is the range.")
    assert not looks_like_bare_refusal("I can't do that.", tool_calls=3)
    assert not looks_like_bare_refusal("x" * 800 + " I can't do that.")


def test_a_reason_only_failure_is_classified_not_guessed(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        gaps = GapService(memory)
        gap = gaps.record_tool_failure(
            "run_reason", tool="x", code="",
            reason="this run's profile does not grant code.write",
            need="build a file",
        )
        assert gap is not None
        assert gap["kind"] == "context_denied"
        offer = gaps.offers_for_run("run_reason")[0]
        assert offer["nextTool"] == "create_goal"
    finally:
        memory.close()
