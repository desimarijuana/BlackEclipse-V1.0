"""The live lane must not grade a provider outage as an agent failure."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.evaluation.environments import build_environment
from harness.evaluation.runner import EvaluationRunner, ServiceAgentInvoker
from harness.evaluation.store import EvaluationStore
from harness.evaluation.tasks import EvaluationTask
from harness.persistence import AgentMemoryStore
from harness.schemas import HarnessError, ModelSettings, RunResult


def test_provider_configured_accepts_a_local_provider_without_a_key(monkeypatch):
    from harness.evaluation import live_gate

    monkeypatch.setenv(live_gate.PROVIDER_ENV, "ollama")
    monkeypatch.delenv(live_gate.API_KEY_ENV, raising=False)
    assert live_gate.provider_configured() is True


def test_provider_configured_requires_a_key_for_a_hosted_provider(monkeypatch):
    from harness.evaluation import live_gate

    monkeypatch.setenv(live_gate.PROVIDER_ENV, "openai")
    monkeypatch.delenv(live_gate.API_KEY_ENV, raising=False)
    assert live_gate.provider_configured() is False
    monkeypatch.setenv(live_gate.API_KEY_ENV, "sk-test")
    assert live_gate.provider_configured() is True


def test_provider_configured_rejects_an_empty_provider(monkeypatch):
    from harness.evaluation import live_gate

    monkeypatch.delenv(live_gate.PROVIDER_ENV, raising=False)
    monkeypatch.setenv(live_gate.API_KEY_ENV, "sk-test")
    assert live_gate.provider_configured() is False


def test_a_subset_smoke_cannot_claim_the_live_gate():
    from harness.evaluation import live_gate

    full = live_gate.apply_live_sample_floor(
        {"passed": True, "failures": []}, live_gate.MIN_LIVE_TRIALS,
    )
    assert full["passed"] is True

    small = live_gate.apply_live_sample_floor(
        {"passed": True, "failures": []}, live_gate.MIN_LIVE_TRIALS - 1,
    )
    assert small["passed"] is False
    assert any("sample_size" in message for message in small["failures"])


class _Bus:
    def subscribe(self, _listener):
        return lambda: None


class _FakeService:
    def __init__(self, result: RunResult) -> None:
        self.bus = _Bus()
        self._result = result

    async def run(self, _request):  # noqa: ANN001 - mirrors AgenticService.run
        return self._result


def _task() -> EvaluationTask:
    return EvaluationTask.from_dict({
        "id": "live.provider.001", "category": "core", "difficulty": "easy",
        "input": {"prompt": "say READY"}, "expected_output": {"equals": "READY"},
    })


def _invoker(result: RunResult) -> ServiceAgentInvoker:
    return ServiceAgentInvoker(
        _FakeService(result),
        ModelSettings(provider="ollama", model="test-model",
                      base_url="http://localhost:11434/v1"),
    )


@pytest.mark.asyncio
async def test_a_provider_error_is_unmeasured_not_a_zero():
    result = RunResult(
        runId="r-provider", status="failed",
        error=HarnessError(code="PROVIDER_ERROR", message="429 provider limit"),
    )
    invocation = await _invoker(result).invoke(
        _task(), "trial-1", build_environment({}),
    )
    assert invocation.unmeasured_reason
    assert "PROVIDER_ERROR" in invocation.unmeasured_reason


@pytest.mark.asyncio
async def test_a_provider_failure_marks_the_trial_unmeasured():
    directory = tempfile.mkdtemp(prefix="be-eval-live-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        result = RunResult(
            runId="r-provider", status="failed",
            error=HarnessError(code="PROVIDER_TIMEOUT", message="timed out"),
        )
        runner = EvaluationRunner(
            store, invoker=_invoker(result), eval_store=EvaluationStore(store),
        )
        task_result = await runner.run_task(_task(), trials=1, persist=False)
        trial = task_result.trials[0]
        assert trial.unmeasured is True
        assert trial.status == "unmeasured"
        assert trial.passed is False
    finally:
        store.close()
