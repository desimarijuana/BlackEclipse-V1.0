"""Eclipse Code Execution & Verification Layer.

A dedicated execution layer, separate from the terminal, filesystem and code
intelligence subsystems, that gives the agent the ability to run, build, test,
diagnose, repair and VERIFY software. It reuses the existing infrastructure
rather than duplicating it:

  * `code/sandbox.py` is the ONE bounded execution primitive (process-tree kill,
    env scrub, output cap);
  * the terminal subsystem owns persistent shells, background processes and ports;
  * `code/policy.py` owns the autonomy/binding/command vocabulary;
  * `code/workspace.py` owns workspace resolution and path confinement;
  * `agent-memory.db` is the history store (via `ExecutionStore`).

The orchestrator owns the lifecycle; runtime adapters own language behaviour.
"""

from __future__ import annotations

from .models import (
    Artifact,
    Diagnostic,
    ErrorClass,
    ExecutionContext,
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    FilesystemPolicy,
    NetworkPolicy,
    ResourceLimits,
    RiskLevel,
    TestResult,
    new_execution_id,
)
from .orchestrator import ExecutionOrchestrator
from .policy import ExecutionDecision, ExecutionPolicyEngine
from .projects import ProjectDetector, ProjectInfo, detect_language
from .runtimes import (
    JavaScriptRuntime,
    PythonRuntime,
    RuntimeAdapter,
    RuntimeRegistry,
    RuntimeUnavailable,
    ShellRuntime,
    SqlRuntime,
    TypeScriptRuntime,
    build_runtime_registry,
)
from .scheduler import ExecutionScheduler
from .service import ExecutionService
from .state import ExecutionState, StateMachine, can_transition, is_terminal
from .store import ExecutionStore
from .verify_loop import ExecutionVerifier, RepairOutcome

__all__ = [
    "Artifact",
    "Diagnostic",
    "ErrorClass",
    "ExecutionContext",
    "ExecutionDecision",
    "ExecutionMode",
    "ExecutionOrchestrator",
    "ExecutionPolicyEngine",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionScheduler",
    "ExecutionService",
    "ExecutionState",
    "ExecutionStore",
    "ExecutionVerifier",
    "FilesystemPolicy",
    "JavaScriptRuntime",
    "NetworkPolicy",
    "ProjectDetector",
    "ProjectInfo",
    "PythonRuntime",
    "RepairOutcome",
    "ResourceLimits",
    "RiskLevel",
    "RuntimeAdapter",
    "RuntimeRegistry",
    "RuntimeUnavailable",
    "ShellRuntime",
    "SqlRuntime",
    "StateMachine",
    "TestResult",
    "TypeScriptRuntime",
    "build_runtime_registry",
    "can_transition",
    "detect_language",
    "is_terminal",
    "new_execution_id",
]
