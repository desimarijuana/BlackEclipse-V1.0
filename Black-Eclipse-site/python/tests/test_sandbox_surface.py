"""The sandbox's health surface and the operator's fail-closed switch.

The audit's hardest finding was that the isolation boundary was INVISIBLE:
an operator could not tell which primitive was in force, and a platform with
no primitive at all degraded silently. These tests pin the observable
surface (`GET /sandbox`), the fail-closed switch
(`HARNESS_SANDBOX_REQUIRED=1`) and the analysis admission gate.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from harness import main as harness_main
from harness.code import sandbox as sandbox_mod
from harness.code.execution import (
    SANDBOX_UNAVAILABLE,
    AnalysisRequest,
    prepare_analysis,
)
from harness.routers import sandbox as sandbox_router


def _client() -> TestClient:
    return TestClient(harness_main.app)


def test_sandbox_route_reports_the_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HARNESS_SANDBOX_REQUIRED", raising=False)
    with _client() as client:
        response = client.get("/sandbox")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    # The boundary is described honestly: what is enforced, and what is not.
    assert body["backend"]
    assert body["isolation"]["filesystemIsolation"] is False
    assert body["isolation"]["networkIsolation"] is False
    assert body["isolation"]["processTreeKill"] is True
    assert body["required"] is False


def test_sandbox_route_reports_the_interpreter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HARNESS_SANDBOX_REQUIRED", raising=False)
    with _client() as client:
        body = client.get("/sandbox").json()
    # The interpreter is reported when the analysis stack is installed; the
    # route never fails when it is not.
    assert "interpreter" in body
    assert "packageLockDigest" in body


def test_required_isolation_switch_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARNESS_SANDBOX_REQUIRED", "1")
    assert sandbox_mod.isolation_required() is True
    monkeypatch.setenv("HARNESS_SANDBOX_REQUIRED", "0")
    assert sandbox_mod.isolation_required() is False
    monkeypatch.setenv("HARNESS_SANDBOX_REQUIRED", "yes")
    assert sandbox_mod.isolation_required() is True
    monkeypatch.delenv("HARNESS_SANDBOX_REQUIRED")
    assert sandbox_mod.isolation_required() is False


def test_required_isolation_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With the switch on, the local backend must not run user code."""
    monkeypatch.setenv("HARNESS_SANDBOX_REQUIRED", "1")
    # The local backend provides no filesystem or network boundary.
    monkeypatch.setattr(sandbox_mod, "isolation_satisfied", lambda: False)
    prepared = prepare_analysis(
        AnalysisRequest(source="print(1)", purpose="probe"),
    )
    assert prepared.status == "refused"
    assert prepared.code == SANDBOX_UNAVAILABLE
    assert "isolation" in (prepared.stderr or "").lower()


def test_sandbox_route_is_503_when_required_and_unmet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HARNESS_SANDBOX_REQUIRED", "1")
    monkeypatch.setattr(sandbox_mod, "isolation_satisfied", lambda: False)
    with _client() as client:
        response = client.get("/sandbox")
    assert response.status_code == 503
    assert "isolation" in response.json()["detail"].lower()


def test_analysis_admission_gate_limits_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate bounds how many analyses run at once on one host."""
    from harness import analysis_tools

    monkeypatch.setenv("HARNESS_ANALYSIS_CONCURRENCY", "1")
    monkeypatch.setenv("HARNESS_ANALYSIS_QUEUE_WAIT_S", "0.2")

    peak = 0
    live = 0
    guard = asyncio.Lock()

    async def _fake_run() -> None:
        nonlocal peak, live
        async with guard:
            live += 1
            peak = max(peak, live)
        await asyncio.sleep(0.05)
        async with guard:
            live -= 1

    async def _scenario() -> None:
        sem = analysis_tools._slots()
        assert sem._eclipse_limit == 1  # type: ignore[attr-defined]
        await asyncio.gather(
            _with_slot(sem, _fake_run), _with_slot(sem, _fake_run)
        )

    async def _with_slot(sem, fn) -> None:
        await sem.acquire()
        try:
            await fn()
        finally:
            sem.release()

    asyncio.run(_scenario())
    assert peak == 1


def test_queue_wait_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    from harness import analysis_tools

    monkeypatch.setenv("HARNESS_ANALYSIS_QUEUE_WAIT_S", "7")
    assert analysis_tools._queue_wait_s() == 7.0
    monkeypatch.setenv("HARNESS_ANALYSIS_QUEUE_WAIT_S", "nonsense")
    assert analysis_tools._queue_wait_s() == 30.0
    monkeypatch.delenv("HARNESS_ANALYSIS_QUEUE_WAIT_S")
    assert analysis_tools._queue_wait_s() == 30.0
