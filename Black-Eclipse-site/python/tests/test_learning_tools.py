"""Learning-loop read tools — QA Round 1, Phase Q2.

The automatic review queue and the candidate capture both existed, but no agent
tool read them, so an agent asked to summarize "what Eclipse learned" guessed.
These pin the read surface, its honest empty states, and the banner deep link.
"""

from __future__ import annotations

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.graph_context import _eligibility_dict
from harness.memory_tools import (
    learning_candidate_list_handler,
    learning_review_list_handler,
    register_memory_tools,
)
from harness.persistence import AgentMemoryStore
from harness.research.learning_store import LearningStore
from harness.tools import ToolContext, ToolRegistry


@pytest.fixture()
def env(tmp_path):
    run_store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    memory = EclipseMemoryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))
    learning_store = LearningStore(memory.store)
    registry = ToolRegistry()
    register_memory_tools(registry)
    ctx = ToolContext(
        run_id="run_t",
        log=lambda *_: None,
        user_id="u1",
        memory_store=run_store,
        memory_service=memory,
        learning_store=learning_store,
    )
    yield {
        "run_store": run_store,
        "memory": memory,
        "learning_store": learning_store,
        "registry": registry,
        "ctx": ctx,
    }
    run_store.close()
    memory.close()


async def test_learning_tools_are_registered(env):
    names = set(env["registry"].names())
    assert {"learning_review_list", "learning_candidate_list"} <= names
    # Read-only surface: no approval/effect authorizer is required.
    assert env["registry"].get("learning_review_list").permission == "read"
    assert env["registry"].get("learning_candidate_list").permission == "read"


async def test_review_list_empty_state_explains_the_automatic_queue(env):
    text, data = await learning_review_list_handler({}, env["ctx"])
    assert "queued automatically" in text
    assert "Memory → Reviews" in text
    assert data["count"] == 0
    assert data["health"]["total"] == 0


async def test_review_list_reads_stored_reviews(env):
    env["run_store"].save_learning_review({
        "runId": "run_1",
        "status": "completed",
        "mode": "deterministic",
        "result": {"outcomes": [{"category": "no_learning"}]},
    })
    text, data = await learning_review_list_handler({}, env["ctx"])
    assert data["count"] == 1
    assert "run=run_1" in text
    assert data["health"]["total"] == 1


async def test_candidate_list_empty_state_names_the_queue(env):
    text, data = await learning_candidate_list_handler({}, env["ctx"])
    assert "Skills → Learning Queue" in text
    assert data["count"] == 0


async def test_candidate_list_reads_captured_candidates(env):
    env["memory"].store.save_candidate({
        "sourceRunId": "run_1",
        "candidateType": "procedure",
        "title": "Check the schema first",
        "signature": "sig-1",
    })
    text, data = await learning_candidate_list_handler({}, env["ctx"])
    assert data["count"] == 1
    assert "Check the schema first" in text


async def test_candidate_list_reports_total_beyond_the_page(env):
    for index in range(3):
        env["memory"].store.save_candidate({
            "sourceRunId": f"run_{index}",
            "candidateType": "procedure",
            "title": f"Candidate {index}",
            "signature": f"sig-{index}",
        })
    text, data = await learning_candidate_list_handler({"limit": 1}, env["ctx"])
    assert data["count"] == 1
    assert data["total"] == 3
    assert "Showing 1 of 3 learning candidate(s)" in text


async def test_candidate_list_uses_eclipse_memory_store_with_production_wiring(env):
    # service.py wires learning_store to the research LearningStore (paths) and
    # memory_service to EclipseMemoryService. Candidates must still come from the
    # Eclipse-Memory store, never AttributeError on the path store.
    assert isinstance(env["ctx"].learning_store, LearningStore)
    assert not hasattr(env["ctx"].learning_store, "list_candidates")
    env["memory"].store.save_candidate({
        "sourceRunId": "run_1",
        "candidateType": "procedure",
        "title": "Real wiring candidate",
        "signature": "sig-wired",
    })
    text, data = await learning_candidate_list_handler({}, env["ctx"])
    assert data["count"] == 1
    assert "Real wiring candidate" in text


async def test_candidate_list_ignores_decoy_learning_store(env):
    env["ctx"].learning_store = object()
    env["memory"].store.save_candidate({
        "sourceRunId": "run_1",
        "candidateType": "procedure",
        "title": "Decoy-safe candidate",
        "signature": "sig-decoy",
    })
    text, data = await learning_candidate_list_handler({}, env["ctx"])
    assert data["count"] == 1
    assert "Decoy-safe candidate" in text


async def test_candidate_list_reports_unavailable_store_without_raising(env):
    env["ctx"].memory_service = None
    env["ctx"].learning_store = object()
    text, data = await learning_candidate_list_handler({}, env["ctx"])
    assert "not available in this run" in text
    assert data["count"] == 0


async def test_candidate_list_empty_state_respects_disabled_detection(env):
    env["memory"].policy.set("skill_learning_mode", "off")
    text, data = await learning_candidate_list_handler({}, env["ctx"])
    assert "Automatic candidate detection is disabled" in text
    assert "skill learning mode is off" in text
    assert "Settings → Skills" in text
    assert "created automatically" not in text
    assert "automatically at run end" not in text
    assert data["mode"] == "off"
    assert data["autoCandidateDetection"] is False


async def test_candidate_list_empty_state_keeps_auto_wording_when_enabled(env):
    env["memory"].policy.set("skill_learning_mode", "ask_before_saving")
    text, data = await learning_candidate_list_handler({}, env["ctx"])
    assert "A candidate is created automatically at run end" in text
    assert data["mode"] == "ask_before_saving"
    assert data["autoCandidateDetection"] is True


async def test_candidate_list_empty_status_scopes_the_message_and_keeps_footer(env):
    env["memory"].store.save_candidate({
        "sourceRunId": "run_1",
        "candidateType": "procedure",
        "title": "Detected only",
        "signature": "sig-detected",
        "status": "detected",
    })
    text, data = await learning_candidate_list_handler({"status": "accepted"}, env["ctx"])
    assert data["count"] == 0
    assert "No learning candidates captured with status 'accepted' yet." in text
    assert "Read-only." in text


async def test_candidate_list_reports_a_capped_requested_limit(env):
    env["memory"].store.save_candidate({
        "sourceRunId": "run_1",
        "candidateType": "procedure",
        "title": "One row",
        "signature": "sig-limit",
    })
    text, data = await learning_candidate_list_handler({"limit": 500}, env["ctx"])
    assert data["count"] == 1
    assert "Requested limit 500 was capped at 50." in text


def test_banner_links_to_the_learning_queue_screen():
    eligibility = _eligibility_dict(
        "run_1", eligible=False, reason="no tool use", steps=1, tool_calls=0, skill_requested=False,
    )
    assert eligibility["learnQueuePath"] == "/?tab=skills&sub=skills.learning"
