"""The run's two composition objects (Round 5 / C2.1).

`build_graph` took ~45 keyword arguments and `ToolContext` carries ~100 fields.
The arguments fall into two genuinely different lifetimes:

  * **RunScope** - the process-wide services a run reuses (registry, stores,
    memory, MCP, market, portfolio, ...). One per run, shared by every node.
  * **RunSpec** - the facts of THIS run (request, emitter, resume point,
    allowlist, authorizer, result sinks). One per invocation.

Splitting them is behavior-preserving; the graph unpacks both at the top, so
the node bodies and every tool see exactly the same values as before.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from .schemas import AgentConfig, RunRequest


@dataclass
class RunScope:
    """Process-wide services one run reuses. Never mutated by the graph."""

    registry: Any
    data_bridge: Any
    store: Any
    bus: Any = None
    cancel_event: Optional[asyncio.Event] = None
    retrieval_cache: Any = None
    memory_service: Any = None
    skill_registry: Any = None
    memory_router: Any = None
    mcp_manager: Any = None
    approvals: Any = None
    code_store: Any = None
    code_intel_runtime: Any = None
    evidence_store: Any = None
    learning_store: Any = None
    market: Any = None
    portfolio: Any = None
    ledger: Any = None
    advisory: Any = None
    decision: Any = None
    quant: Any = None
    project_store: Any = None
    search: Any = None
    artifact_service: Any = None
    ui_service: Any = None
    task_manager: Any = None


@dataclass
class RunSpec:
    """The facts of one run invocation."""

    request: RunRequest
    emitter: Any
    agent: Optional[AgentConfig] = None
    effect_authorizer: Any = None
    allowed: Optional[set[str]] = None
    source_sink: Any = None
    lineage: Any = None
    resume_from: Optional[dict[str, Any]] = None
    code_ledger: Any = None
    vision_sink: Any = None
    document_sink: Any = None
    image_sink: Any = None
    video_sink: Any = None
    advisory_sink: Any = None
    # C4: the goal/plan runtime for this run (None = an ordinary run).
    plan: Any = None

    def __post_init__(self) -> None:
        # A caller may hand a mutable set; copy it so a run cannot mutate the
        # caller's surface while it executes.
        if self.allowed is not None:
            self.allowed = set(self.allowed)


__all__ = ["RunScope", "RunSpec"]
