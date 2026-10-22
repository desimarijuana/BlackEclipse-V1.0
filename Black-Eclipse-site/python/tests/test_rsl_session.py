"""The unattended session: the conductor's surface tick and the watcher."""

from __future__ import annotations

import asyncio

import pytest

from harness.code.evolution_store import EvolutionStore
from harness.evaluation.store import EvaluationStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.config import RSLConfig
from harness.self_improvement.loop import RSLLoop
from harness.self_improvement.session_watch import SessionWatcher


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


class _Service:
    def __init__(self, store):
        self.store = store
        self._rsl_loop = None
        self._drift_watch = None
        self._rsl_session_watch = None
        self.memory_service = None


def _loop(store, service, **overrides) -> RSLLoop:
    return RSLLoop(
        service=service,
        config=RSLConfig(mode="auto", **overrides),
        run_store=store,
        evolution=EvolutionStore(store),
        eval_store=EvaluationStore(store),
    )


def test_the_surface_session_is_off_by_default(store):
    service = _Service(store)
    loop = _loop(store, service)
    assert loop.config.surface_lab is False
    assert loop.surface_budget_ok() is False


def test_the_surface_budget_is_separate_from_the_code_budget(store):
    service = _Service(store)
    loop = _loop(store, service, surface_lab=True, max_surface_experiments_per_day=1)
    assert loop.surface_budget_ok() is True

    EvolutionStore(store).save_candidate({
        "signature": "surface-lab-1",
        "sourceCategory": "surface-lab",
        "observedCount": 1,
        "problemStatement": "a staged session",
        "status": "inert",
    })
    # The surface budget is now spent; the code budget is untouched.
    assert loop.surface_budget_ok() is False
    assert loop.budget_ok() is True


@pytest.mark.asyncio
async def test_the_conductor_runs_a_surface_session_in_auto_mode(store, monkeypatch):
    service = _Service(store)
    loop = _loop(store, service, surface_lab=True)
    service._rsl_loop = loop

    called: list[str] = []

    async def fake_session():
        called.append("session")
        return {"winner": "lesson-1", "staged": {"staged": True}, "variants": [1]}

    monkeypatch.setattr(loop, "run_surface_session", fake_session)

    result = await loop.tick()
    assert called == ["session"]
    assert result["surface"]["winner"] == "lesson-1"
    assert result["surface"]["staged"] is True


@pytest.mark.asyncio
async def test_the_session_watcher_refuses_without_a_budget(store):
    service = _Service(store)
    loop = _loop(store, service)
    service._rsl_loop = loop
    watcher = SessionWatcher(service, interval_seconds=0)

    result = await watcher.check()
    assert result["skipped"] == "budget"
    assert watcher.health()["enabled"] is False
