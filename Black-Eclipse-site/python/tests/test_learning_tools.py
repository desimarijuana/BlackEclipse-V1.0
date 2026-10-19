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
from harness.tools import ToolContext, ToolRegistry


@pytest.fixture()
def env(tmp_path):
    run_store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    memory = EclipseMemoryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))
    registry = ToolRegistry()
    register_memory_tools(registry)
    ctx = ToolContext(
        run_id="run_t",
        log=lambda *_: None,
        user_id="u1",
        memory_store=run_store,
        memory_service=memory,
        learning_store=memory.store,
    )
    yield {"run_store": run_store, "memory": memory, "registry": registry, "ctx": ctx}
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


def test_banner_links_to_the_learning_queue_screen():
    eligibility = _eligibility_dict(
        "run_1", eligible=False, reason="no tool use", steps=1, tool_calls=0, skill_requested=False,
    )
    assert eligibility["learnQueuePath"] == "/?tab=skills&sub=skills.learning"
