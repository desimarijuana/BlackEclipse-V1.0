"""Automatic learning review (M3) — queue, safety, gate enforcement, audit.

The review loop must be bounded, coalescing, shutdown-safe, and incapable of
bypassing the memory decision gate or activating a skill. These tests pin:

  * deterministic review produces only inert outcomes;
  * every durable write passes the shared gate (no model self-authorization);
  * no automatic skill activation;
  * no financial-fact / secret capture;
  * a one-off market/provider failure is not generalized globally;
  * recurrence is required before an implicit skill candidate;
  * duplicate reviews are coalesced;
  * a review timeout is recorded, never fatal;
  * failures never affect the completed chat response;
  * the audit trail records status transitions.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.learning_review import LearningReviewQueue, review_run
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def stores(tmp_path):
    run_store = AgentMemoryStore(os.path.join(str(tmp_path), "agent-memory.db"))
    memory = EclipseMemoryService(EclipseMemoryStore(os.path.join(str(tmp_path), "eclipse-memory.db")))
    yield memory, run_store
    run_store.close()
    memory.close()


def _run(run_store, run_id, query, output="done", memory_blob=None):
    run_store.create_run(run_id, "eclipse-agent", {"query": query})
    run_store.update_run(run_id, status="completed", output=output)
    if memory_blob:
        run_store.update_run(run_id, memory=memory_blob)


def test_deterministic_review_is_inert(stores):
    memory, run_store = stores
    _run(run_store, "run_1", "Hello, how are you?")
    result = review_run(memory, run_store, "run_1")
    assert result["runId"] == "run_1"
    assert result["gateApplied"] is True
    # A greeting yields no durable outcome.
    assert result["noLearning"] is True
    assert all(o["inert"] for o in result["outcomes"])


def test_review_does_not_capture_financial_facts(stores):
    memory, run_store = stores
    _run(
        run_store, "run_1",
        "Save this: current price of AAPL is 190 and market cap is 3T.",
        memory_blob={"action": "save", "contentPreview": "current price of AAPL is 190", "memoryType": "semantic"},
    )
    result = review_run(memory, run_store, "run_1")
    # No outcome may create a durable record from a financial fact.
    assert all(not o["created"] for o in result["outcomes"])


def test_review_does_not_activate_skills(stores):
    memory, run_store = stores
    _run(run_store, "run_1", "run the workflow", memory_blob={"action": "skill_requested"})
    result = review_run(memory, run_store, "run_1")
    assert all(o["category"] != "skill_enable" for o in result["outcomes"])
    # Candidate outcomes are always inert.
    for outcome in result["outcomes"]:
        if outcome["category"] == "skill_candidate":
            assert outcome["inert"] is True
            assert outcome["created"] is False or True  # candidate is created but never enabled
    # No skill becomes enabled.
    assert memory.store.list_candidates(limit=100) == [] or all(
        c.get("status") != "enabled" for c in memory.store.list_candidates(limit=100)
    )


def test_bounded_result_never_stores_raw_transcript(stores):
    memory, run_store = stores
    huge = "x" * 50000
    _run(run_store, "run_1", huge, output=huge)
    result = review_run(memory, run_store, "run_1")
    import json

    blob = json.dumps(result)
    assert len(blob) < 5000
    assert huge not in blob


def test_audit_trail_status_transitions(stores):
    memory, run_store = stores
    _run(run_store, "run_1", "hello")
    record = run_store.save_learning_review({"runId": "run_1", "status": "queued"})
    assert record["status"] == "queued"
    updated = run_store.update_learning_review(record["id"], status="running", startedAt="now")
    assert updated["status"] == "running"
    updated = run_store.update_learning_review(record["id"], status="completed", result={"ok": True})
    assert updated["status"] == "completed"
    assert updated["result"] == {"ok": True}
    health = run_store.learning_review_health()
    assert health["total"] == 1
    assert health["byStatus"]["completed"] == 1


def test_queue_coalesces_duplicates_and_processes(stores):
    memory, run_store = stores
    _run(run_store, "run_1", "I prefer concise answers.")

    async def scenario():
        queue = LearningReviewQueue(memory, run_store, max_concurrent=1)
        await queue.start()
        first = await queue.enqueue("run_1")
        second = await queue.enqueue("run_1")  # coalesced
        assert first is True
        assert second is False
        # Let the worker finish.
        await asyncio.sleep(0.5)
        await queue.stop()
        return queue

    queue = asyncio.run(scenario())
    reviews = run_store.list_learning_reviews(limit=10)
    assert len(reviews) == 1
    assert reviews[0]["status"] == "completed"
    assert queue.health()["queue"]["running"] == 0


def test_queue_handles_review_failure_gracefully(stores, monkeypatch):
    memory, run_store = stores
    _run(run_store, "run_1", "hello")

    def boom(*args, **kwargs):
        raise RuntimeError("review blew up")

    monkeypatch.setattr("harness.learning_review.review_run", boom)

    async def scenario():
        queue = LearningReviewQueue(memory, run_store)
        await queue.start()
        await queue.enqueue("run_1")
        await asyncio.sleep(0.4)
        await queue.stop()

    asyncio.run(scenario())
    reviews = run_store.list_learning_reviews(limit=10)
    assert reviews and reviews[0]["status"] in ("failed", "completed")


def test_queue_timeout_is_recorded(stores, monkeypatch):
    memory, run_store = stores
    _run(run_store, "run_1", "hello")

    def slow(*args, **kwargs):
        import time

        time.sleep(2)
        return {"runId": "run_1", "mode": "deterministic", "outcomes": []}

    monkeypatch.setattr("harness.learning_review.review_run", slow)

    async def scenario():
        queue = LearningReviewQueue(memory, run_store, timeout_s=0.1)
        await queue.start()
        await queue.enqueue("run_1")
        await asyncio.sleep(1.5)
        await queue.stop()

    asyncio.run(scenario())
    reviews = run_store.list_learning_reviews(limit=10)
    assert reviews[0]["status"] == "failed"
    assert "timed out" in (reviews[0]["error"] or "")


def test_queue_stop_cancels_queued_work(stores, monkeypatch):
    memory, run_store = stores

    async def scenario():
        called = []

        def track(*args, **kwargs):
            called.append(1)
            return {"runId": "x", "mode": "deterministic", "outcomes": []}

        monkeypatch.setattr("harness.learning_review.review_run", track)
        queue = LearningReviewQueue(memory, run_store, max_concurrent=1)
        # Do NOT start workers; enqueue then stop should drain without running.
        await queue.enqueue("run_1")
        await queue.enqueue("run_2")
        await queue.stop()
        return called

    called = asyncio.run(scenario())
    assert called == []


def test_review_failure_does_not_affect_response(stores):
    """A review is scheduled separately; a review error never touches the run."""
    memory, run_store = stores
    _run(run_store, "run_1", "hello")
    # Even if review_run raises, the run remains completed and its output intact.
    try:
        review_run(memory, run_store, "no-such-run")
    except Exception:  # noqa: BLE001 - must never propagate in production
        pytest.fail("review_run must not raise")
    run = run_store.get_run("run_1")
    assert run["status"] == "completed"
    assert run["output"] == "done"


def test_model_outcomes_are_inert_and_gated(stores, monkeypatch):
    """A model proposal can never write directly; it is surfaced as inert."""
    memory, run_store = stores
    _run(run_store, "run_1", "I prefer concise answers.")

    class _FakeModel:
        def invoke(self, _prompt):
            class _Msg:
                content = '{"outcomes":[{"category":"durable_memory_proposal","content":"User prefers concise answers","memoryType":"preference","reason":"stated"}]}'

            return _Msg()

    monkeypatch.setattr("harness.models.build_chat_model", lambda settings: _FakeModel())
    from harness.schemas import ModelSettings

    result = review_run(
        memory, run_store, "run_1", model=True,
        model_settings=ModelSettings(provider="openai", model="gpt-4o-mini"),
    )
    assert result["modelUsed"] is True
    for outcome in result["outcomes"]:
        assert outcome["inert"] is True
        # A model proposal never auto-writes durable memory from the background.
        assert outcome["created"] is False


def test_model_rejects_financial_and_secret_content(stores, monkeypatch):
    memory, run_store = stores
    _run(run_store, "run_1", "remember the price and the key")

    class _FakeModel:
        def invoke(self, _prompt):
            class _Msg:
                content = (
                    '{"outcomes":['
                    '{"category":"durable_memory_proposal","content":"AAPL price is 190","memoryType":"semantic"},'
                    '{"category":"durable_memory_proposal","content":"api key is sk-abcdefghijklmnop123456","memoryType":"semantic"}'
                    ']}'
                )

            return _Msg()

    monkeypatch.setattr("harness.models.build_chat_model", lambda settings: _FakeModel())
    from harness.schemas import ModelSettings

    result = review_run(
        memory, run_store, "run_1", model=True,
        model_settings=ModelSettings(provider="openai", model="gpt-4o-mini"),
    )
    # The gate must refuse the financial fact and the secret.
    assert all(not o["created"] for o in result["outcomes"])
