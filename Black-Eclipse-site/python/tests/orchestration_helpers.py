"""Shared fixtures for the orchestration tests (offline, deterministic)."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from harness.orchestration import (
    EngineConfig,
    OrchestrationEngine,
    OrchestrationStore,
    RuntimeContext,
)
from harness.persistence import AgentMemoryStore
from harness.tools import ToolContext, ToolDefinition, ToolRegistry


def make_store(tmp_path: Any) -> AgentMemoryStore:
    return AgentMemoryStore(os.path.join(str(tmp_path), "agent-memory.db"))


def make_registry(tools: Optional[list[tuple[str, Callable, str]]] = None) -> ToolRegistry:
    registry = ToolRegistry()
    for name, handler, permission in tools or []:
        registry.register(ToolDefinition(
            name=name, description=name,
            input_schema={"type": "object", "properties": {"value": {"type": "string"}}},
            handler=handler, permission=permission, risk="low",
        ))
    return registry


def make_engine(
    store: AgentMemoryStore,
    *,
    callables: Optional[dict[str, Callable]] = None,
    registry: Optional[ToolRegistry] = None,
    limits: Optional[dict[str, int]] = None,
    max_concurrency: int = 8,
    tool_context: Optional[ToolContext] = None,
    bus: Any = None,
    model_settings: Any = None,
    allowed: Optional[set[str]] = None,
    run_id: str = "test_run",
) -> OrchestrationEngine:
    runtime = RuntimeContext(
        registry=registry if registry is not None else ToolRegistry(),
        store=store, bus=bus, model_settings=model_settings, allowed=allowed,
        tool_context=tool_context, run_id=run_id,
    )
    config = EngineConfig(
        max_concurrency=max_concurrency,
        lease_ttl_ms=5_000,
        default_timeout_ms=5_000,
        limits=dict(limits or {}),
        heartbeat_interval_s=0.25,
    )
    engine = OrchestrationEngine(OrchestrationStore(store), runtime, config=config)
    for name, fn in (callables or {}).items():
        engine.register_callable(name, fn)
    return engine


def tool_ctx(store: AgentMemoryStore, *, allowed: Optional[set[str]] = None,
             registry: Optional[ToolRegistry] = None) -> ToolContext:
    return ToolContext(
        run_id="test_run", log=lambda *a, **k: None, memory_store=store,
        tool_registry=registry, allowed=allowed,
    )
