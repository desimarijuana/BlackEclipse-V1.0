"""Failure Intelligence & Adaptive Recovery — the unifying failure layer.

Eclipse already owns every *piece* of autonomous problem-solving: provider error
normalization (`model_runtime.errors`), build/test diagnostics
(`execution.diagnostics`), retry classification (`orchestration.retry`), model
fallback (`model_runtime.routing`), loop detection
(`observability.anomaly`), durable task checkpoints (`tasks`), the learning
pipeline (`skills.learning`, `eclipse_memory`), and verification
(`code.verify`, `execution.verify_loop`). What was missing was the layer that
*composes* them: one shared failure vocabulary, one stable failure signature, one
inspectable recovery policy and one bounded decision — recorded durably as agent
memory.

This package is that layer. It is not a second execution loop, not a second
registry and not a second memory: it records what the existing subsystems already
know about a failure, decides a bounded next step, and hands that decision back.

Public surface:

    normalize_failure(...)         # classify into FailureKind / Retryability
    failure_signature(...)         # stable fingerprint; RecurrenceTracker
    select_strategies(failure)     # permitted strategies, ordered
    RecoveryController().decide(...)  # one bounded RecoveryDecision
    RecoveryService(store).record_failure(...)  # classify+decide+persist
"""

from .config import budget_from_env, recovery_enabled
from .compensation import compensate_pending
from .controller import RecoveryAction, RecoveryController, RecoveryDecision
from .diagnosis import Diagnosis, DiagnosisEngine, Hypothesis
from .discovery import (
    AcquisitionPlan,
    AcquisitionStep,
    CapabilityDescriptor,
    CapabilityIndex,
    CapabilityMatch,
    acquisition_plan,
    build_default_index,
)
from .envelope import (
    ActionClass,
    AutonomyEnvelope,
    EnvelopeDecision,
    EnvelopeOutcome,
    default_envelope,
    from_dict,
    load_envelope,
)
from .executor import RecoveryRunResult, recover_operation
from .learning import incident_to_candidate, promote_incidents
from .operations import OperationLedger
from .probes import register_default_probes
from .reproduction import ReproducerRegistry, ReproductionResult, reproduce
from .policy import (
    CandidateStrategy,
    RecoveryBudget,
    RecoveryStrategy,
    reject_reason,
    select_strategies,
)
from .service import RecoveryService
from .signature import RecurrenceTracker, RecurrenceVerdict, failure_signature, normalize_message
from .store import RecoveryStore
from .taxonomy import (
    FailureKind,
    NormalizedFailure,
    Retryability,
    classify,
    normalize_failure,
)

__all__ = [
    "AcquisitionPlan",
    "AcquisitionStep",
    "ActionClass",
    "AutonomyEnvelope",
    "CandidateStrategy",
    "CapabilityDescriptor",
    "CapabilityIndex",
    "CapabilityMatch",
    "Diagnosis",
    "DiagnosisEngine",
    "EnvelopeDecision",
    "EnvelopeOutcome",
    "FailureKind",
    "Hypothesis",
    "NormalizedFailure",
    "OperationLedger",
    "RecoveryAction",
    "RecoveryBudget",
    "RecoveryController",
    "RecoveryDecision",
    "RecoveryRunResult",
    "RecoveryService",
    "RecoveryStore",
    "RecoveryStrategy",
    "RecurrenceTracker",
    "RecurrenceVerdict",
    "Retryability",
    "acquisition_plan",
    "budget_from_env",
    "build_default_index",
    "classify",
    "compensate_pending",
    "default_envelope",
    "failure_signature",
    "from_dict",
    "incident_to_candidate",
    "load_envelope",
    "normalize_failure",
    "normalize_message",
    "promote_incidents",
    "recover_operation",
    "recovery_enabled",
    "register_default_probes",
    "reject_reason",
    "ReproducerRegistry",
    "ReproductionResult",
    "reproduce",
    "select_strategies",
]
