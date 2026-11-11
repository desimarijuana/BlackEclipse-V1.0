"""Round 5 / C2: every run is registered, so SSE and cancel can see it.

Before this change only `run_background` touched `_active`; a foreground run was
invisible to `GET /runs/{id}/stream` (the stream closed early) and to
`POST /runs/{id}/cancel` (the cancel was a no-op).

The service is built with `__new__` on purpose: this test is about the
registration contract, not about booting the ~40 subsystems.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from harness import service as service_mod
from harness.events import EventBus
from harness.schemas import RunResult
from harness.service import AgenticService


class _Store:
    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}

    def update_run(self, run_id: str, **fields) -> None:
        self.runs.setdefault(run_id, {}).update(fields)

    def append_event(self, *_args, **_kwargs) -> None:
        return None


class _Learning:
    def mark_user_active(self) -> None:
        return None

    async def enqueue(self, *_args, **_kwargs) -> None:
        return None


def _request(run_id: str = "run_1") -> SimpleNamespace:
    return SimpleNamespace(
        runId=run_id,
        callbackBaseUrl="http://127.0.0.1:1",
        callbackToken="test-token",
        agentId="eclipse-agent",
        input=SimpleNamespace(query="test", history=None),
    )


def _service() -> AgenticService:
    svc = AgenticService.__new__(AgenticService)
    svc.store = _Store()
    svc.bus = EventBus()
    svc.registry = object()
    svc._active = {}
    svc._run_slots = None
    svc.learning_review = _Learning()
    svc._run_kwargs = lambda: {}  # type: ignore[method-assign]

    async def _no_review(*_args, **_kwargs) -> None:
        return None

    svc._schedule_review = _no_review  # type: ignore[method-assign]
    return svc


@pytest.fixture(autouse=True)
def _no_chat_build_bookkeeping(monkeypatch):
    monkeypatch.setattr(service_mod, "apply_chat_build_budget", lambda _r: None)
    monkeypatch.setattr(service_mod, "record_chat_build", lambda *_a, **_k: None)


@pytest.mark.asyncio
async def test_foreground_run_is_active_and_cancellable(monkeypatch):
    started = asyncio.Event()

    async def fake_execute(request, *_args, **_kwargs):
        started.set()
        await asyncio.sleep(60)
        return RunResult(runId=request.runId, status="completed")

    monkeypatch.setattr(service_mod, "execute_run", fake_execute)
    svc = _service()
    task = asyncio.create_task(svc.run(_request()))

    await asyncio.wait_for(started.wait(), timeout=2)
    assert svc.is_active("run_1") is True
    assert svc.cancel("run_1") is True

    result = await asyncio.wait_for(task, timeout=2)
    assert result.status == "cancelled"
    assert svc.store.runs["run_1"]["status"] == "cancelled"
    assert svc.is_active("run_1") is False


@pytest.mark.asyncio
async def test_foreground_run_deregisters_when_it_finishes(monkeypatch):
    async def fake_execute(request, *_args, **_kwargs):
        return RunResult(runId=request.runId, status="completed")

    monkeypatch.setattr(service_mod, "execute_run", fake_execute)
    svc = _service()

    result = await svc.run(_request("run_2"))
    assert result.status == "completed"
    assert "run_2" not in svc._active


@pytest.mark.asyncio
async def test_background_run_is_registered_and_cancellable(monkeypatch):
    started = asyncio.Event()

    async def fake_execute(request, *_args, **_kwargs):
        started.set()
        await asyncio.sleep(60)
        return RunResult(runId=request.runId, status="completed")

    monkeypatch.setattr(service_mod, "execute_run", fake_execute)
    svc = _service()

    await svc.run_background(_request("run_3"))
    await asyncio.wait_for(started.wait(), timeout=2)
    assert svc.is_active("run_3") is True
    assert svc.cancel("run_3") is True
    await asyncio.sleep(0.05)
    assert svc.is_active("run_3") is False


@pytest.mark.asyncio
async def test_cancel_unknown_or_finished_run_is_false():
    svc = _service()
    assert svc.cancel("missing") is False

    done = asyncio.create_task(asyncio.sleep(0))
    await done
    svc._active["finished"] = done
    assert svc.cancel("finished") is False
