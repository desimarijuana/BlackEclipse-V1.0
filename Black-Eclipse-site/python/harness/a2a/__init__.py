"""Agent-to-Agent (A2A) subsystem.

A first-class A2A layer ON TOP of the existing runtime. It does NOT replace
`execute_run`, the tool registry, the event bus, the Task runtime or the
persistence layer:

  * `model.py`     — the closed vocabularies + validated contracts (AgentDefinition,
                     AgentEnvelope, Finding, A2AResult, Conflict, AgentBudget).
  * `protocol.py`  — typed messages, payload validation, correlation, idempotency.
  * `store.py`     — durable agents/messages/deliveries/delegations/budgets/results
                     on the ONE agent-memory connection.
  * `registry.py`  — the versioned Agent Registry + capability index.
  * `bus.py`       — the durable Message Bus (publish/consume/ack/reject/dead-letter).
  * `budget.py`    — per-root-run budgets that only ever narrow.
  * `permissions.py` — least-privilege authorization + spawning intersection.
  * `results.py`   — normalization, evidence linking, conflict detection, merging.
  * `supervisor.py` — the Supervisor + QA review.
  * `service.py`   — `A2AService`: delegation, spawning, messaging, merging, review.
  * `tools.py`     — the model-facing `A2A_TOOLS`.
  * `bootstrap.py` — boot wiring onto `AgenticService`.

A delegated task IS a normal `service.run` dispatched by the existing
`TaskScheduler`; every message and delivery is a durable row.
"""

from .bootstrap import install_a2a_layer, recover_a2a
from .bus import MessageBus
from .budget import BudgetExceeded, BudgetTracker
from .model import (
    AgentBudget,
    AgentCapability,
    AgentDefinition,
    AgentEnvelope,
    AgentStatus,
    A2AResult,
    ApprovalStatus,
    Conflict,
    ConflictCandidate,
    DelegationRecord,
    DelegationStatus,
    DeliveryStatus,
    Finding,
    MergedResult,
    MessagePriority,
    MessageType,
    SupervisorReport,
    SupervisorVerdict,
)
from .protocol import ProtocolError, make_envelope, validate_envelope
from .registry import AgentRegistry, RegistryError
from .results import detect_conflicts, merge_results
from .service import A2AError, A2AService
from .store import A2AStore
from .supervisor import qa_checklist, review_results
from .tools import A2A_TOOLS, a2a_for, forget_a2a, register_a2a_tools

__all__ = [
    "A2AError",
    "A2AService",
    "A2AStore",
    "A2A_TOOLS",
    "AgentBudget",
    "AgentCapability",
    "AgentDefinition",
    "AgentEnvelope",
    "AgentRegistry",
    "AgentStatus",
    "A2AResult",
    "ApprovalStatus",
    "BudgetExceeded",
    "BudgetTracker",
    "Conflict",
    "ConflictCandidate",
    "DelegationRecord",
    "DelegationStatus",
    "DeliveryStatus",
    "Finding",
    "MergedResult",
    "MessageBus",
    "MessagePriority",
    "MessageType",
    "ProtocolError",
    "RegistryError",
    "SupervisorReport",
    "SupervisorVerdict",
    "a2a_for",
    "detect_conflicts",
    "forget_a2a",
    "install_a2a_layer",
    "make_envelope",
    "merge_results",
    "qa_checklist",
    "recover_a2a",
    "register_a2a_tools",
    "review_results",
    "validate_envelope",
]
