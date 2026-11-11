"""Capability gaps: classify the block, keep it durable, offer one route."""

from __future__ import annotations

from pathlib import Path

from harness.gaps.service import GapService
from harness.gaps.taxonomy import (
    CAPABILITY_MISSING,
    CONTEXT_DENIED,
    SAFETY_DENIED,
    TRANSIENT,
    UNKNOWN,
    classify,
)
from harness.persistence import AgentMemoryStore
from harness.run_outcome import build_outcome_envelope


def _service(tmp_path: Path) -> tuple[AgentMemoryStore, GapService]:
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    return memory, GapService(memory)


def test_the_taxonomy_separates_capability_context_and_safety():
    assert classify("KIT_UNKNOWN") == CAPABILITY_MISSING
    assert classify("PROFILE_DENIED") == CONTEXT_DENIED
    assert classify("WORKSPACE_UNBOUND") == CONTEXT_DENIED
    assert classify("PROTECTED_PATH") == SAFETY_DENIED
    assert classify("TOOL_TIMEOUT") == TRANSIENT
    assert classify("SOMETHING_NEW") == UNKNOWN


def test_a_profile_denial_offers_the_permitted_surface(tmp_path: Path):
    memory, gaps = _service(tmp_path)
    try:
        gap = gaps.record_tool_failure(
            "run_context",
            tool="scaffold_kit",
            code="PROFILE_DENIED",
            reason="this run's profile does not grant code.write",
            need="turn this into a bot that runs every morning at 9am",
        )
        assert gap is not None and gap["kind"] == CONTEXT_DENIED
        offers = gaps.offers_for_run("run_context")
        assert len(offers) == 1
        offer = offers[0]
        assert offer["offer"] is True
        assert offer["nextTool"] == "bot_create"
        assert offer["actionPrompt"]
        assert offer["status"] in ("gap", "handoff_required")
    finally:
        memory.close()


def test_a_workspace_denial_offers_a_code_task(tmp_path: Path):
    memory, gaps = _service(tmp_path)
    try:
        gaps.record_tool_failure(
            "run_ws", tool="scaffold_kit", code="WORKSPACE_UNBOUND",
            reason="there is no project folder bound to this run",
            need="build a market data adapter",
        )
        offer = gaps.offers_for_run("run_ws")[0]
        assert offer["nextTool"] == "create_goal"
        assert offer["surface"] == "code_agent"
    finally:
        memory.close()


def test_a_missing_capability_offers_the_existing_builder(tmp_path: Path):
    memory, gaps = _service(tmp_path)
    try:
        gaps.record_tool_failure(
            "run_cap", tool="analysis_run", code="KIT_UNKNOWN",
            reason="there's no ready-made shape named 'x'",
            need="build a new financial ratio",
        )
        offer = gaps.offers_for_run("run_cap")[0]
        assert offer["nextTool"] in ("capability_build", "scaffold_kit", "analysis_run")
        assert "Want me to?" in gaps.offer_text([offer])
    finally:
        memory.close()


def test_safety_and_transient_failures_never_produce_an_offer(tmp_path: Path):
    memory, gaps = _service(tmp_path)
    try:
        assert gaps.record_tool_failure(
            "run_safe", tool="read_file", code="PROTECTED_PATH",
            reason="the path is protected",
        ) is None
        assert gaps.record_tool_failure(
            "run_safe", tool="price_history", code="TOOL_TIMEOUT",
            reason="timed out",
        ) is None
        assert gaps.offers_for_run("run_safe") == []
    finally:
        memory.close()


def test_accept_decline_and_suppression_are_durable(tmp_path: Path):
    memory, gaps = _service(tmp_path)
    try:
        gap = gaps.record_tool_failure(
            "run_a", tool="scaffold_kit", code="PROFILE_DENIED",
            need="build a bot", reason="profile",
        )
        accepted = gaps.accept(gap["gapId"])
        assert accepted["state"] == "accepted"
        assert accepted["actionPrompt"]
        assert gaps.offers_for_run("run_a") == []

        gap_b = gaps.record_tool_failure(
            "run_b", tool="scaffold_kit", code="PROFILE_DENIED",
            need="build a bot", reason="profile",
        )
        gaps.decline(gap_b["gapId"])
        assert gaps.offers_for_run("run_b") == []

        gap_c = gaps.record_tool_failure(
            "run_c", tool="scaffold_kit", code="PROFILE_DENIED",
            need="build a bot", reason="profile",
        )
        gaps.suppress(gap_c["gapId"])
        # The SAME stable signature stays quiet on the next run.
        quiet = gaps.record_tool_failure(
            "run_d", tool="scaffold_kit", code="PROFILE_DENIED",
            need="build a bot", reason="profile",
        )
        assert quiet is not None and quiet["state"] == "suppressed"
        assert gaps.offers_for_run("run_d") == []
        assert gaps.summary()["total"] >= 3
    finally:
        memory.close()


def test_the_outcome_envelope_names_the_offer():
    envelope = build_outcome_envelope(
        run_id="run_offer",
        run={"status": "completed", "output": "done"},
        events=[{
            "type": "capability.offer",
            "data": {
                "gapId": "gap_1", "need": "build a bot", "kind": "context_denied",
                "code": "PROFILE_DENIED", "offer": True,
            },
        }],
    )
    assert envelope["capabilityGap"]["offer"] is True
    assert envelope["capabilityGap"]["capability"] == "build a bot"
