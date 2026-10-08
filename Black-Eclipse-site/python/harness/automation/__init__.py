"""The Eclipse Native Automation Engine.

Automation decides WHEN and WHY work executes; the existing Task/Workflow/Agent
runtime decides WHAT and HOW it executes. This package is therefore a *trigger +
policy + durability* layer over the ONE runtime (`service.run`,
`service.run_skill`, `service.run_workflow`, `ToolRegistry.execute`) — never a
second execution engine.

It supersedes the earlier `harness.jobs` scheduler (ADR-H108) while keeping the
legacy `/jobs` API working through an adapter (`automation.legacy`). One durable
definition model, one scheduler loop, one event-routing table, one execution
ledger.

Bound to the ONE `agent-memory.db` connection, exactly like `jobs`, `run_lineage`
and `mcp/approvals`. NEVER `jdds.db` (market data) and NEVER `eclipse-memory.db`
(normalized memory).
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
