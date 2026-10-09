"""Recovery lifecycle wiring: bootstrap install, event capture, agent tools."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from harness.eclipse_memory.store import EclipseMemoryStore
from harness.recovery.bootstrap import install_recovery_layer, start_recovery, stop_recovery
from harness.recovery.tools import (
    get_recovery_service,
    recovery_incidents_handler,
    recovery_summary_handler,
)
from harness.tools import ToolContext, ToolRegistry


class _FakeBus:
    def __init__(self) -> None:
        self.unsubscribed: list[Any] = []

    def unsubscribe(self, sub: Any) -> None:
        self.unsubscribed.append(sub)


class _FakeEventSystem:
    def __init__(self) -> None:
        self.filters: Any = None
        self.handler: Any = None
        self.bus = _FakeBus()

    def subscribe(self, filter_like: Any, handler: Any, **kwargs: Any) -> Any:
        self.filters = filter_like
        self.handler = handler
        return object()


@dataclass
class _FakeService:
    memory_store: Any = None
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    events: _FakeEventSystem = field(default_factory=_FakeEventSystem)


@dataclass
class _FakeEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = "evt_1"
    task_id: str | None = "t1"
    source: str = "harness"
    replay: bool = False


def _ctx() -> ToolContext:
    return ToolContext(run_id="r1", log=lambda *_: None)


def test_install_registers_service_and_tools(tmp_path):
    svc = _FakeService(memory_store=EclipseMemoryStore(str(tmp_path / "m.db")))
    engine = install_recovery_layer(svc)
    assert engine is not None
    assert get_recovery_service() is engine
    assert "recovery_summary" in svc.registry.names()
    assert "recovery_incidents" in svc.registry.names()


def test_start_subscribes_to_failure_types_and_captures(tmp_path):
    svc = _FakeService(memory_store=EclipseMemoryStore(str(tmp_path / "m.db")))
    install_recovery_layer(svc)

    async def scenario():
        await start_recovery(svc)
        assert "tool.failed" in svc.events.filters
        assert "run.failed" in svc.events.filters
        await svc.events.handler(_FakeEvent(
            type="tool.failed",
            payload={"code": "TOOL_TIMEOUT", "tool": "search", "message": "timed out"},
        ))
        # Replayed events are ignored.
        await svc.events.handler(_FakeEvent(type="tool.failed", replay=True, payload={"code": "x"}))
        await stop_recovery(svc)
        assert svc.events.bus.unsubscribed

    asyncio.run(scenario())
    incidents = get_recovery_service().list_incidents()
    assert len(incidents) == 1
    assert incidents[0]["kind"] == "timeout"
    assert incidents[0]["source"] == "event"


def test_tool_handlers_return_incidents(tmp_path):
    svc = _FakeService(memory_store=EclipseMemoryStore(str(tmp_path / "m.db")))
    engine = install_recovery_layer(svc)
    engine.record_failure(code="TOOL_TIMEOUT", message="x", source="tool", task_id="t1")

    text, data = asyncio.run(recovery_incidents_handler({}, _ctx()))
    assert data["incidents"]
    summary_text, summary = asyncio.run(recovery_summary_handler({}, _ctx()))
    assert summary["incidents"] == 1
    assert "1" in summary_text
