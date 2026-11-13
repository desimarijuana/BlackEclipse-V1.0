"""Run-scoped bindings for process-wide subsystems.

The service owns ONE market gateway and ONE MCP manager for the whole process.
Before multi-session support, each run rewrote state on those singletons
(`gateway._bridge = bridge`, `mcp.set_sampling_model_factory(...)`), so two
concurrent runs overwrote each other's transport and model.

These values are per-run, so they live in `ContextVar`s: every run is an asyncio
task, and a task inherits its own copy of the context. The singleton reads the
current run's binding first and falls back to its construction-time default.

The context manager is synchronous and wraps the awaitable run body; child
tasks (streams, tool workers) inherit the binding automatically.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional

_RUN_BRIDGE: ContextVar[Optional[Any]] = ContextVar("harness_run_bridge", default=None)
_RUN_SAMPLING_FACTORY: ContextVar[Optional[Any]] = ContextVar(
    "harness_run_sampling_factory", default=None
)


def current_bridge(fallback: Any = None) -> Any:
    """The calling run's data bridge, or the singleton's default."""
    bridge = _RUN_BRIDGE.get()
    return fallback if bridge is None else bridge


def current_sampling_factory(fallback: Any = None) -> Any:
    """The calling run's sampling model factory, or the singleton's default."""
    factory = _RUN_SAMPLING_FACTORY.get()
    return fallback if factory is None else factory


@contextmanager
def bind_run(
    *,
    bridge: Any = None,
    sampling_factory: Any = None,
) -> Iterator[None]:
    """Bind run-scoped values for the duration of one run."""
    bridge_token = _RUN_BRIDGE.set(bridge)
    factory_token = _RUN_SAMPLING_FACTORY.set(sampling_factory)
    try:
        yield
    finally:
        _RUN_SAMPLING_FACTORY.reset(factory_token)
        _RUN_BRIDGE.reset(bridge_token)


__all__ = ["bind_run", "current_bridge", "current_sampling_factory"]
