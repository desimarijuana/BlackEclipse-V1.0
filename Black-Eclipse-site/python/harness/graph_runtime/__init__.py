"""Eclipse graph runtime — compiler + deterministic executor for the Workflow IR.

The visual editor (`src/components/screens/graph-studio/`) authors a canonical
Workflow IR; the front door loads the persisted version from JDDS and forwards
it here. This package is the RUNTIME half:

  * `model.py`    — the IR contracts (mirrors the TS schema) + run DTOs.
  * `registry.py` — the node SDK: typed ports, config fields, capabilities,
                    side-effect classes, executors.
  * `nodes.py`    — the built-in pure node executors (safe formula language).
  * `compiler.py` — IR → execution plan (validation, layers, authorization).
  * `executor.py` — deterministic layer scheduler (lifecycle, timeout, retry,
                    cancellation, output validation).
  * `store.py`    — durable run rows on `agent-memory.db`.
  * `service.py`  — the ONE compile/run/inspect/cancel entry point.
  * `bootstrap.py`— idempotent boot wiring onto the AgenticService.

Non-goals: this is not a second agent runtime (agent nodes delegate to the
existing runtime in Phase 7), not a second market-data path (Phase 5 reuses the
gateway/JDdS), and not durable cross-process orchestration (Phase 4 wraps this
executor in the Execution Fabric).
"""

from .compiler import RunGrants, compile_workflow
from .executor import GraphExecutor
from .model import (
    Diagnostic,
    ExecutionPlan,
    GraphRun,
    NodeRun,
    NodeStatus,
    RunStatus,
    WorkflowIR,
)
from .nodes import build_default_registry, evaluate_formula
from .registry import NodeDef, NodeExecContext, NodeRegistry
from .service import GraphCompileError, GraphService
from .store import GraphRunStore

__all__ = [
    "RunGrants",
    "compile_workflow",
    "GraphExecutor",
    "Diagnostic",
    "ExecutionPlan",
    "GraphRun",
    "NodeRun",
    "NodeStatus",
    "RunStatus",
    "WorkflowIR",
    "build_default_registry",
    "evaluate_formula",
    "NodeDef",
    "NodeExecContext",
    "NodeRegistry",
    "GraphCompileError",
    "GraphService",
    "GraphRunStore",
]
