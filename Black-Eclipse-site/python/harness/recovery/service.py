"""The recovery engine facade.

`RecoveryService` composes the three pure pieces (`taxonomy`, `policy`,
`controller`) with durable persistence (`store`) and exposes the ONE operation
the rest of the runtime needs:

    record_failure(...) -> { failure, decision, incidentId, occurrenceCount,
                             recurrent }

It classifies the failure, computes a bounded decision, persists the incident
and the planned attempt, and returns the decision for the caller to act on. The
caller — a task scheduler, an event consumer, an operator — owns execution; this
service never runs a tool or a graph node (it is not a second execution loop).
"""

from __future__ import annotations

from typing import Any, Optional

from .config import budget_from_env, recovery_enabled
from .controller import RecoveryAction, RecoveryController, RecoveryDecision
from .diagnosis import Diagnosis, DiagnosisEngine
from .discovery import CapabilityIndex
from .envelope import AutonomyEnvelope, from_dict, load_envelope
from .learning import promote_incidents
from .operations import OperationLedger
from .policy import RecoveryBudget
from .reproduction import ReproducerRegistry, reproduce
from .store import FAILED, OPEN, RESOLVED, RecoveryStore
from .taxonomy import NormalizedFailure, normalize_failure


class RecoveryService:
    def __init__(
        self,
        memory_store: Any,
        *,
        controller: Optional[RecoveryController] = None,
        store: Optional[RecoveryStore] = None,
        budget: Optional[RecoveryBudget] = None,
        diagnosis_engine: Optional[DiagnosisEngine] = None,
        capability_index: Optional[CapabilityIndex] = None,
        envelope: Optional[AutonomyEnvelope] = None,
    ) -> None:
        self.store = store or RecoveryStore(memory_store)
        self.controller = controller or RecoveryController(
            budget=budget or budget_from_env()
        )
        self.diagnosis = diagnosis_engine or DiagnosisEngine()
        self.capability_index = capability_index
        self.envelope = envelope or self._resolve_envelope()
        self.operations = OperationLedger(self.store)
        self.reproducers = ReproducerRegistry()

    def _resolve_envelope(self) -> AutonomyEnvelope:
        """A persisted operator envelope wins over the config file/default."""
        try:
            durable = self.store.load_envelope_dict()
        except Exception:  # noqa: BLE001 - a store read must never block boot
            durable = None
        if durable is not None:
            return from_dict(durable, source="durable")
        return load_envelope()

    # ── the core operation ───────────────────────────────────────────────────

    def record_failure(
        self,
        *,
        code: Optional[str] = None,
        message: Optional[str] = None,
        subsystem: str = "harness",
        source: str = "unknown",
        location: Optional[str] = None,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        allow_provider_substitution: bool = True,
        record_attempt: bool = True,
        recovery_state: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Classify, decide, persist and return — the recovery entry point.

        `recovery_state` lets a caller supply ITS OWN bounded counters
        (`attempts`, `signature_attempts`, `recurrent`, `delegations`,
        `elapsed_ms`) instead of the durable, cross-run counts. The run hot path
        (R3-03) uses this so a failure seen in a past session cannot exhaust a
        fresh run's allowance; persistence and the recorded decision are
        unchanged.
        """
        failure = normalize_failure(
            code=code, message=message, subsystem=subsystem, source=source,
            location=location, details=details,
        )
        prior = self.store.occurrence_count(failure.signature, task_id=task_id)
        prior_incident = self.store.find_incident(failure.signature, task_id=task_id)
        prior_attempts = int(prior_incident["attempts"]) if prior_incident else 0

        state = recovery_state or {}
        decision = self.controller.decide(
            failure,
            attempts=int(state.get("attempts", prior_attempts)),
            signature_attempts=int(state.get("signature_attempts", prior)),
            delegations=int(state.get("delegations", 0)),
            recurrent=bool(state.get("recurrent", prior >= 1)),
            allow_provider_substitution=allow_provider_substitution,
            elapsed_ms=int(state.get("elapsed_ms", 0)),
        )
        diagnosis = self.diagnosis.diagnose(failure, evidence=details)
        # Round 4 (W11, L3): the ledger's measured preference may REORDER the
        # policy's own candidates — it never adds a strategy the policy did not
        # offer, so every safety invariant (auth denials, non-retryable kinds,
        # approval gating) is unchanged. The evidence rides the result.
        preference = None
        try:
            preference = self.preferred_strategy(failure.signature)
        except Exception:  # noqa: BLE001 - a preference lookup must never block recovery
            preference = None
        if preference is not None and decision.strategy is not None:
            candidates = list(decision.candidates)
            match = next(
                (c for c in candidates if c.strategy.value == preference.strategy), None,
            )
            if match is not None and match.strategy != decision.strategy:
                from dataclasses import replace  # noqa: PLC0415

                decision = replace(
                    decision,
                    strategy=match.strategy,
                    candidates=[match, *[c for c in candidates if c.strategy != match.strategy]],
                    reason=(
                        f"{decision.reason}; L3 preference: {preference.strategy} "
                        f"({preference.success_rate:.2f} over {preference.observations} observation(s))"
                    ),
                )
        incident = self.store.record_failure(
            failure, task_id=task_id, run_id=run_id, decision=decision, metadata=details,
        )
        self.store.set_diagnosis(incident["id"], diagnosis.to_dict())
        result: dict[str, Any] = {
            "failure": failure.to_dict(),
            "decision": decision.to_dict(),
            "diagnosis": diagnosis.to_dict(),
            "incidentId": incident["id"],
            "occurrenceCount": incident["occurrenceCount"],
            "recurrent": prior >= 1,
        }
        if preference is not None:
            result["strategyPreference"] = preference.to_dict()
        if record_attempt and decision.strategy is not None:
            attempt = self.store.record_attempt(
                incident["id"],
                attempt_no=prior_attempts + 1,
                action=decision.action.value,
                strategy=decision.strategy.value,
                reason=decision.reason,
                backoff_ms=decision.backoff_ms,
                outcome="planned",
            )
            result["attemptId"] = attempt["id"]
            # An exhausted decision that stops is a terminal, failed incident.
            if decision.action == RecoveryAction.STOP:
                self.store.set_status(incident["id"], FAILED if decision.exhausted else RESOLVED)
        return result

    def propose_routing_repair(
        self, incident_id: str, *, catalog: Any = None,
    ) -> Optional[dict[str, Any]]:
        """A minimal, typed routing-repair proposal for a stored incident.

        READ-ONLY: it never writes the tree and never activates the change. The
        proposal names its cause, the exact patch op (if any), and the fixture
        that must flip; verification and landing are separate, gated steps.
        """
        incident = self.store.get_incident(incident_id)
        if incident is None:
            return None
        from .routing_repair import proposal_from_incident  # noqa: PLC0415

        return proposal_from_incident(incident, catalog=catalog).to_dict()

    def record_outcome(
        self,
        incident_id: str,
        *,
        outcome: str,
        detail: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """Record how a planned attempt actually ended, and close the incident."""
        incident = self.store.get_incident(incident_id)
        if incident is None:
            return None
        attempts = self.store.list_attempts(incident_id)
        attempt_no = (attempts[-1]["attemptNo"] if attempts else 0)
        attempt = self.store.record_attempt(
            incident_id, attempt_no=attempt_no, action="outcome", outcome=outcome,
            detail=detail,
        )
        if outcome in ("succeeded", "resolved"):
            self.store.set_status(incident_id, RESOLVED)
        elif outcome in ("failed", "exhausted"):
            self.store.set_status(incident_id, FAILED)
        return attempt

    # ── inspection ───────────────────────────────────────────────────────────

    def decide(self, failure: NormalizedFailure, **kwargs: Any) -> RecoveryDecision:
        return self.controller.decide(failure, **kwargs)

    def diagnose_incident(
        self, incident_id: str, *, evidence: Optional[dict[str, Any]] = None
    ) -> Optional[dict[str, Any]]:
        """(Re-)diagnose a recorded incident, optionally with fresh evidence."""
        incident = self.store.get_incident(incident_id)
        if incident is None:
            return None
        failure = normalize_failure(
            code=incident.get("code"), message=incident.get("message"),
            subsystem=incident.get("subsystem") or "harness",
            source=incident.get("source") or "unknown",
        )
        merged = dict(incident.get("metadata") or {})
        merged.update(evidence or {})
        diagnosis: Diagnosis = self.diagnosis.diagnose(failure, evidence=merged)
        self.store.set_diagnosis(incident_id, diagnosis.to_dict())
        return diagnosis.to_dict()

    def list_incidents(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.store.list_incidents(**kwargs)

    def get_incident(self, incident_id: str) -> Optional[dict[str, Any]]:
        return self.store.get_incident(incident_id)

    def incident_attempts(self, incident_id: str) -> list[dict[str, Any]]:
        return self.store.list_attempts(incident_id)

    def summary(self) -> dict[str, Any]:
        return self.store.summary()

    def set_envelope(self, envelope: AutonomyEnvelope) -> dict[str, Any]:
        """Replace AND persist the autonomy envelope (operator action)."""
        self.envelope = envelope
        try:
            self.store.save_envelope(envelope.to_dict())
        except Exception:  # noqa: BLE001 - persistence is best-effort
            pass
        return envelope.to_dict()

    def envelope_view(self) -> dict[str, Any]:
        return self.envelope.to_dict()

    def approve(self, incident_id: str, strategy: str, *, approved_by: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Grant a ONE-OFF operator approval for an out-of-envelope strategy."""
        if self.store.get_incident(incident_id) is None:
            return None
        return self.store.add_approval(incident_id, strategy, approved_by=approved_by)

    def approvals(self, incident_id: str) -> list[dict[str, Any]]:
        return self.store.list_approvals(incident_id)

    def has_approval(self, incident_id: str, strategy: str) -> bool:
        return self.store.has_approval(incident_id, strategy)

    def consume_approval(self, incident_id: str, strategy: str) -> bool:
        """Claim a one-off approval EXACTLY once (single-use).

        The executor uses THIS rather than `has_approval`, so the same operator
        approval can never authorize a second recovery action.
        """
        return self.store.consume_approval(incident_id, strategy)

    # ── auto-reproduction ────────────────────────────────────────────────────

    def register_reproducer(self, kind: Any, name: str, fn: Any) -> None:
        """Register a bounded reproducer for a failure kind (caller-supplied)."""
        self.reproducers.register(kind, name, fn)

    async def reproduce_incident(self, incident_id: str, *, timeout_s: float = 10.0) -> Optional[dict[str, Any]]:
        """Run the registered reproducer for an incident and re-diagnose."""
        incident = self.store.get_incident(incident_id)
        if incident is None:
            return None
        failure = normalize_failure(
            code=incident.get("code"), message=incident.get("message"),
            subsystem=incident.get("subsystem") or "harness",
            source=incident.get("source") or "unknown",
        )
        result = await reproduce(self.reproducers, failure, timeout_s=timeout_s)
        evidence = dict(incident.get("metadata") or {})
        if result.attempted:
            evidence["reproduced"] = result.reproduced
        diagnosis: Diagnosis = self.diagnosis.diagnose(failure, evidence=evidence)
        self.store.set_diagnosis(incident_id, diagnosis.to_dict())
        return {"reproduction": result.to_dict(), "diagnosis": diagnosis.to_dict()}

    # ── discovery + learning ─────────────────────────────────────────────────

    def discover(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Ranked capabilities matching a free-text need (empty if no index)."""
        if self.capability_index is None:
            return []
        return [m.to_dict() for m in self.capability_index.search(query, **kwargs)]

    def plan_acquisition(
        self, query: str, *, task_id: Optional[str] = None,
        facts: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """The typed acquisition lifecycle (W5/W9): surface, approval, gaps, retry.

        `facts` (an operator-supplied GitHub source / plugin folder / kit id)
        only resolve which EXISTING gate an install step names; nothing is
        granted and the step stays approval-flagged.
        """
        if self.capability_index is None:
            return None
        from .acquisition import propose  # noqa: PLC0415

        return propose(query, self.capability_index, task_id=task_id, facts=facts).to_dict()

    def plan_incident_acquisition(
        self, incident_id: str, *, facts: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """Plan the acquisition for a stored incident's original request."""
        incident = self.store.get_incident(incident_id)
        if incident is None:
            return None
        query = str(incident.get("message") or "").strip()
        for prefix in ("no registered component matches: ", "capability gap: "):
            if query.startswith(prefix):
                query = query[len(prefix):].strip()
                break
        if not query:
            return None
        return self.plan_acquisition(query, task_id=incident.get("taskId"), facts=facts)

    def promote_incidents(
        self,
        incidents: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Promote qualifying incidents into inert skill candidates."""
        return promote_incidents(self, incidents, **kwargs)

    def preferred_strategy(
        self, failure_signature: str, **kwargs: Any,
    ) -> Optional[Any]:
        """L3 (round 4, W11): the route the ledger supports for a signature.

        Read-only; returns `None` when the evidence is too thin — an unmeasured
        choice stays unmade.
        """
        from .strategy_learning import preference_from_store  # noqa: PLC0415

        return preference_from_store(self.store, failure_signature, **kwargs)

    def health(self) -> dict[str, Any]:
        try:
            summary = self.summary()
            return {
                "status": "ok" if recovery_enabled() else "disabled",
                "enabled": recovery_enabled(),
                "budget": self.controller.budget.__dict__,
                "autonomy": self.envelope.to_dict(),
                **summary,
            }
        except Exception as exc:  # noqa: BLE001 - health must never raise
            return {"status": "error", "error": str(exc)}


__all__ = ["FAILED", "OPEN", "RESOLVED", "RecoveryService"]
