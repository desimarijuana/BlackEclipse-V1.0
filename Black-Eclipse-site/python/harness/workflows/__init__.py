"""Composable workflow graph (Harness closeout Phase 5).

The runtime already IS a harness: ONE execution plane (`execute_run`), ONE tool
registry, ONE allowlist seam, ONE event bus, ONE persistence layer. Phase 5 adds
orchestration ON TOP of that plane — it does NOT replace `execute_run`, and it
does NOT build a second agent loop, tool registry or model adapter.

NON-GOALS (deliberate):
  * NOT a generic harness for arbitrary finance tools. Per the coding-agent
    contract, agents must NOT inherit each other's tools or access; a workflow
    step's tool scope is the INTERSECTION of the agent allowlist and the step's
    declared tools, and STRENGTHENS separation.
  * NOT a visual workflow designer, bot scheduler, or agent-builder UI (roadmap
    Phases 8-9).
  * Does NOT replace `execute_run`. A workflow step invokes it.

Package layout:
  * `model.py`    — Workflow / WorkflowStep contracts + limits.
  * `validate.py` — reject a cycle, unbounded fan-out, out-of-scope tool, or a
    step with no terminal path; each rejection names its reason.
  * `store.py`    — persist workflow definitions + versions (agent-memory.db).
  * `compile.py`  — compile a Workflow onto the existing graph by invoking
    `execute_run` per step with the step's narrowed allowlist.
"""

from .model import Workflow, WorkflowStep, STEP_KINDS, WorkflowValidationError
from .validate import validate_workflow
from .store import WorkflowStore
from .compile import compile_workflow, run_workflow

__all__ = [
    "Workflow",
    "WorkflowStep",
    "STEP_KINDS",
    "WorkflowValidationError",
    "validate_workflow",
    "WorkflowStore",
    "compile_workflow",
    "run_workflow",
]
