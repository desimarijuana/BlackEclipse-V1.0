"""Regression: the background (streaming) run path forwards the SAME subsystem
bundles as the foreground path.

`AgenticService.run_background` is the path every streaming chat turn takes. It
used to drop `portfolio`, `quant` and `ui_service`, so quant/portfolio tool
schemas stayed bound but failed at call time with `StoreUnavailable` /
`PORTFOLIO_UNAVAILABLE` — "Eclipse errors instead of answering". This pins the
parity so the two paths can never drift again.
"""

from __future__ import annotations

import asyncio
from typing import Any

from harness import service as service_mod
from harness.service import AgenticService

_FG = "run_fg_parity"
_BG = "run_bg_parity"


class _Request:
    def __init__(self, run_id: str) -> None:
        self.runId = run_id
        self.callbackBaseUrl = "http://127.0.0.1:1"
        self.callbackToken = None


class _Bus:
    def __init__(self) -> None:
        self.ended: list[str] = []

    def end_stream(self, run_id: str) -> None:
        self.ended.append(run_id)


class _LearningReview:
    def mark_user_active(self) -> None:
        """No-op: the foreground path only marks activity."""


class _Result:
    status = "completed"


class _StubService:
    """Only the attributes `run` / `run_background` actually touch."""

    # The real, unmodified kwargs builder: both run paths call it.
    _run_kwargs = AgenticService._run_kwargs

    registry: Any = object()
    store: Any = object()
    retrieval_cache: Any = None
    memory: Any = None
    skill_registry: Any = None
    approvals: Any = None
    memory_router: Any = None
    mcp: Any = None
    code_store: Any = None
    evidence_store: Any = None
    learning_store: Any = None
    search: Any = None
    artifacts: Any = None
    market_gateway: Any = None
    ui: Any = "ui-sentinel"

    def __init__(self) -> None:
        self.bus = _Bus()
        self.learning_review = _LearningReview()
        self._active: dict[str, Any] = {}

    def _market_bundle(self) -> Any:
        return "market-sentinel"

    def _portfolio_bundle(self) -> Any:
        return "portfolio-sentinel"

    def _quant_bundle(self) -> Any:
        return "quant-sentinel"

    async def _schedule_review(self, run_id: str, status: str) -> None:
        """No-op: review scheduling is not under test."""


def _run_both_paths(monkeypatch: Any) -> tuple[_StubService, dict[str, dict[str, Any]]]:
    calls: dict[str, dict[str, Any]] = {}

    async def fake_execute_run(request: Any, registry: Any, bridge: Any, store: Any, bus: Any, **kwargs: Any) -> _Result:
        calls[request.runId] = kwargs
        return _Result()

    monkeypatch.setattr(service_mod, "execute_run", fake_execute_run)

    stub = _StubService()

    async def exercise() -> None:
        await AgenticService.run(stub, _Request(_FG))
        await AgenticService.run_background(stub, _Request(_BG))
        # Await the task run_background created so the call is recorded.
        await stub._active[_BG]

    asyncio.run(exercise())
    return stub, calls


def test_both_paths_forward_the_same_subsystem_kwargs(monkeypatch: Any) -> None:
    _, calls = _run_both_paths(monkeypatch)
    assert set(calls[_FG]) == set(calls[_BG]), (
        "run and run_background drifted: "
        f"foreground-only={set(calls[_FG]) - set(calls[_BG])} "
        f"background-only={set(calls[_BG]) - set(calls[_FG])}"
    )


def test_the_one_kwargs_builder_carries_every_subsystem_bundle() -> None:
    # `_run_kwargs` is the single source both run paths use; it must name every
    # subsystem `execute_run` accepts, or a path silently loses one again.
    kwargs = AgenticService._run_kwargs(_StubService())
    expected = {
        "retrieval_cache", "memory_service", "skill_registry", "approvals",
        "memory_router", "mcp_manager", "code_store", "code_intel_runtime",
        "evidence_store", "learning_store", "market", "portfolio", "quant",
        "search", "artifact_service", "ui_service",
    }
    assert set(kwargs) == expected
    assert kwargs["portfolio"] == "portfolio-sentinel"
    assert kwargs["quant"] == "quant-sentinel"
    assert kwargs["ui_service"] == "ui-sentinel"


def test_background_forwards_portfolio_quant_and_ui(monkeypatch: Any) -> None:
    _, calls = _run_both_paths(monkeypatch)
    background = calls[_BG]
    assert background["portfolio"] == "portfolio-sentinel"
    assert background["quant"] == "quant-sentinel"
    assert background["ui_service"] == "ui-sentinel"


def test_background_signals_the_live_stream_it_is_over(monkeypatch: Any) -> None:
    stub, _ = _run_both_paths(monkeypatch)
    assert stub.bus.ended == [_BG]
