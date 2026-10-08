"""Shared fixtures for the A2A tests (offline, deterministic)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Optional

from harness.a2a.service import A2AService
from harness.events import EventBus
from harness.persistence import AgentMemoryStore
from harness.tools import ToolContext, ToolRegistry


def make_service(tmp_path: Any, *, bus: Optional[Any] = None):
    """A store + host + A2AService seeded with the built-in catalogue."""
    store = AgentMemoryStore(os.path.join(str(tmp_path), "agent-memory.db"))
    event_bus = bus if bus is not None else EventBus()
    host = SimpleNamespace(
        store=store, bus=event_bus, registry=ToolRegistry(), tasks=None, evidence_store=None,
    )
    service = A2AService(host)
    return service, store, host


def tool_context(store: AgentMemoryStore, *, registry: Optional[ToolRegistry] = None,
                 bus: Optional[Any] = None, agent_id: str = "eclipse-agent",
                 run_id: str = "run_t", evidence_store: Optional[Any] = None) -> ToolContext:
    return ToolContext(
        run_id=run_id, log=lambda *a, **k: None, memory_store=store,
        tool_registry=registry, bus=bus, agent_id=agent_id, evidence_store=evidence_store,
    )
