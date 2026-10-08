"""A2A delegation, spawning, waiting, cancellation and asking."""

from __future__ import annotations

import asyncio

import pytest

from harness.a2a.service import A2AError

from a2a_helpers import make_service


def test_delegate_creates_task_delegation_and_messages(tmp_path):
    service, _, _ = make_service(tmp_path)

    async def run():
        return await service.delegate_task(
            sender_agent_id="eclipse-agent", run_id="run_t", objective="Value Tesla (DCF)",
            target_agent_id="valuation-agent",
        )

    result = asyncio.run(run())
    assert result["childAgentId"] == "valuation-agent"
    assert result["status"] == "TODO"
    task = service.get_task_status(result["taskId"])
    assert task["status"] == "TODO"
    assert task["assignedAgentId"] == "valuation-agent"
    assert len(service.delegations("run_t")) == 1
    # The DELEGATION + TASK_REQUEST envelopes were persisted.
    messages = service.store.list_messages(run_id="run_t", limit=10)
    assert {m.type.value for m in messages} >= {"DELEGATION", "TASK_REQUEST"}


def test_capability_routing_selects_agent(tmp_path):
    service, _, _ = make_service(tmp_path)

    async def run():
        return await service.delegate_task(
            sender_agent_id="eclipse-agent", run_id="r", objective="Summarize news",
            capability="news",
        )

    assert asyncio.run(run())["childAgentId"] == "news-agent"


def test_unauthorized_delegation_is_refused(tmp_path):
    service, _, _ = make_service(tmp_path)

    async def run():
        return await service.delegate_task(
            sender_agent_id="research-agent", run_id="r", objective="x",
            target_agent_id="valuation-agent",
        )

    with pytest.raises(A2AError) as exc:
        asyncio.run(run())
    assert exc.value.code == "A2A_DELEGATION_REFUSED"


def test_unknown_capability_is_refused(tmp_path):
    service, _, _ = make_service(tmp_path)

    async def run():
        return await service.delegate_task(
            sender_agent_id="eclipse-agent", run_id="r", objective="x",
            capability="teleportation",
        )

    with pytest.raises(A2AError) as exc:
        asyncio.run(run())
    assert exc.value.code == "A2A_NO_CAPABLE_AGENT"


def test_agent_budget_cap_stops_the_second_delegation(tmp_path):
    service, _, _ = make_service(tmp_path)
    service.budgets.set_limits("r", max_agents=1, max_tasks=1, max_depth=10)

    async def run():
        await service.delegate_task(sender_agent_id="eclipse-agent", run_id="r",
                                    objective="one", target_agent_id="news-agent")
        await service.delegate_task(sender_agent_id="eclipse-agent", run_id="r",
                                    objective="two", target_agent_id="risk-agent")

    with pytest.raises(A2AError) as exc:
        asyncio.run(run())
    assert exc.value.code == "A2A_BUDGET_EXCEEDED"


def test_depth_cap(tmp_path):
    service, _, _ = make_service(tmp_path)
    service.budgets.set_limits("r", max_depth=1, max_agents=10, max_tasks=10)

    async def run():
        await service.delegate_task(sender_agent_id="eclipse-agent", run_id="r",
                                    objective="a", target_agent_id="news-agent")
        await service.delegate_task(sender_agent_id="eclipse-agent", run_id="r",
                                    objective="b", target_agent_id="risk-agent")

    with pytest.raises(A2AError) as exc:
        asyncio.run(run())
    assert exc.value.detail.get("kind") == "depth"


def test_spawn_narrows_and_cannot_delegate(tmp_path):
    service, _, _ = make_service(tmp_path)

    async def run():
        return await service.spawn_agent(
            sender_agent_id="eclipse-agent", run_id="r", base_agent_id="research-agent",
            objective="A focused sub-investigation",
        )

    result = asyncio.run(run())
    spawned_id = result["spawnedAgentId"]
    spawned = service.get_agent(spawned_id)
    assert spawned["canDelegate"] is False
    assert spawned["status"] == "ACTIVE"
    # The spawned agent inherits only the intersection of tools/capabilities.
    base = service.get_agent("research-agent")
    assert set(spawned["capabilities"]) <= set(base["capabilities"])
    assert result["status"] == "TODO"


def test_wait_returns_immediately_for_terminal_task(tmp_path):
    service, store, _ = make_service(tmp_path)

    async def run():
        result = await service.delegate_task(sender_agent_id="eclipse-agent", run_id="r",
                                             objective="x", target_agent_id="news-agent")
        manager = service._task_manager()
        manager.start_task(result["taskId"])
        manager.complete_task(result["taskId"], output_reference="run_child")
        return await service.wait_agent(task_id=result["taskId"], timeout_s=1)

    status = asyncio.run(run())
    assert status["status"] == "COMPLETED"


def test_wait_is_event_driven(tmp_path):
    service, store, host = make_service(tmp_path)

    async def run():
        result = await service.delegate_task(sender_agent_id="eclipse-agent", run_id="r",
                                             objective="x", target_agent_id="news-agent")
        task_id = result["taskId"]

        async def fire():
            await asyncio.sleep(0.05)
            host.bus.publish({"type": "task.completed", "taskId": task_id,
                              "data": {"taskId": task_id}})

        asyncio.ensure_future(fire())
        status = await service.wait_agent(task_id=task_id, timeout_s=2)
        return status

    status = asyncio.run(run())
    assert status["timedOut"] is False


def test_wait_times_out_honestly(tmp_path):
    service, _, _ = make_service(tmp_path)

    async def run():
        result = await service.delegate_task(sender_agent_id="eclipse-agent", run_id="r",
                                             objective="x", target_agent_id="news-agent")
        return await service.wait_agent(task_id=result["taskId"], timeout_s=0.1)

    status = asyncio.run(run())
    assert status["timedOut"] is True


def test_cancel_agent_cancels_delegations(tmp_path):
    service, _, _ = make_service(tmp_path)

    async def run():
        result = await service.delegate_task(sender_agent_id="eclipse-agent", run_id="r",
                                             objective="x", target_agent_id="news-agent")
        await service.cancel_agent(run_id="r", task_id=result["taskId"])
        return service.get_task_status(result["taskId"])

    assert asyncio.run(run())["status"] == "CANCELLED"


def test_ask_agent_creates_answer_task(tmp_path):
    service, _, _ = make_service(tmp_path)

    async def run():
        return await service.ask_agent(sender_agent_id="eclipse-agent",
                                       recipient_agent_id="research-agent",
                                       question="What is the latest guidance?", run_id="r")

    result = asyncio.run(run())
    assert result["answerTaskId"]
    assert service.get_task_status(result["answerTaskId"])["assignedAgentId"] == "research-agent"
