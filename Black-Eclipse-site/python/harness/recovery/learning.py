"""Incident -> skill candidate promotion.

A validated recovery is exactly the kind of reusable experience the learning
system wants (spec §8.2, §12). This module turns a *resolved, recurrent* incident
into an inert `LearningCandidate` using the SAME persistence and signature scheme
as `skills.learning` — it does not create a second learning pipeline, and it
never creates or enables a skill. A candidate is a reviewable observation; an
operator promotes it through the existing skill lifecycle.

Conservative by construction:

  * only a RESOLVED incident (its recovery actually succeeded) qualifies;
  * recurrence is required (`occurrenceCount` >= `min_occurrences`) — a single
    success is not proof of a generalizable skill;
  * a candidate whose signature already exists is suppressed (deduplicated), so
    the same experience never yields repeated candidates.
"""

from __future__ import annotations

from typing import Any, Optional

from ..skills.learning import _signature

_MIN_OCCURRENCES = 2


def _successful_strategies(attempts: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for attempt in attempts:
        strategy = attempt.get("strategy")
        if strategy and attempt.get("outcome") in ("succeeded", "resolved") and strategy not in out:
            out.append(strategy)
    return out


def incident_to_candidate(
    incident: dict[str, Any],
    attempts: list[dict[str, Any]],
    *,
    min_occurrences: int = _MIN_OCCURRENCES,
) -> Optional[dict[str, Any]]:
    """Build an inert candidate draft, or None if it does not qualify."""
    if incident.get("status") != "resolved":
        return None
    if int(incident.get("occurrenceCount", 0)) < max(2, int(min_occurrences)):
        return None
    # Round 4 (W6): a resolved CAPABILITY gap's reusable lesson is the
    # CONSTRUCTION procedure (engineer → implement → register), not a generic
    # recovery strategy. It is the SAME candidate the run-trace path produces
    # (`skills/procedures.py`), so the two sources collapse into one by
    # signature; no strategy attempt is required for it.
    if str(incident.get("kind") or "") == "capability":
        from ..skills.procedures import construction_candidate_from_incident  # noqa: PLC0415

        return construction_candidate_from_incident(incident, attempts)
    strategies = _successful_strategies(attempts)
    if not strategies:
        return None

    code = incident.get("code") or "error"
    message = incident.get("message") or code
    kind = incident.get("kind") or "unknown"
    signature = _signature("failure_recovery", f"{kind}:{message}")
    return {
        "candidateType": "failure_recovery",
        "title": f"Recover from {kind} ({code})",
        "problem": f"Repeated {kind} failure: {message}",
        "observedBehavior": message,
        "proposedLesson": (
            f"When a {kind} failure with code '{code}' recurs, recover with: "
            + ", ".join(strategies) + "."
        ),
        "proposedProcedure": [
            {"step": 1, "action": "classify", "detail": f"recognize the {kind} signature"},
            {"step": 2, "action": "recover", "detail": f"apply {', '.join(strategies)}"},
            {"step": 3, "action": "verify", "detail": "confirm the original operation succeeds"},
        ],
        "evidenceReferences": [
            {"type": "recovery_incident", "id": incident.get("id")},
            *[
                {"type": "recovery_attempt", "id": a.get("id")}
                for a in attempts if a.get("outcome") in ("succeeded", "resolved")
            ],
        ],
        "confidence": min(0.9, 0.5 + 0.1 * int(incident.get("occurrenceCount", 1))),
        "generalizationNotes": "Derived from a recurring, verified recovery.",
        "knownLimitations": "Applies to the recorded signature; revisit if the environment changes.",
        "diagnostics": incident.get("diagnosis") or {},
        "signature": signature,
        "status": "detected",
    }


def promote_incidents(
    service: Any,
    incidents: Optional[list[dict[str, Any]]] = None,
    *,
    min_occurrences: int = _MIN_OCCURRENCES,
    limit: int = 50,
) -> dict[str, Any]:
    """Create inert candidates for qualifying incidents (deduplicated).

    `service` is a `RecoveryService`: its `store` holds the incidents + attempts
    and its `store.memory_store` is the `EclipseMemoryStore` that holds
    `LearningCandidate`. Never enables a skill. `incidents` defaults to the
    resolved incidents with the highest occurrence count.
    """
    if incidents is None:
        incidents = service.list_incidents(status="resolved", limit=limit)
    skill_store = service.store.memory_store
    created: list[dict[str, Any]] = []
    duplicates: list[str] = []
    considered = 0
    for incident in incidents:
        if considered >= max(1, int(limit)):
            break
        considered += 1
        attempts = service.store.list_attempts(incident["id"])
        draft = incident_to_candidate(incident, attempts, min_occurrences=min_occurrences)
        if draft is None:
            continue
        existing = skill_store.find_candidate_by_signature(draft["signature"])
        if existing:
            duplicates.append(existing["id"])
            continue
        candidate_id = skill_store.save_candidate({**draft, "id": None, "sourceRunId": incident.get("runId")})
        try:
            skill_store.append_event(
                "skill.learning_candidate_created",
                run_id=incident.get("runId"),
                data={"candidateId": candidate_id,
                      "candidateType": draft.get("candidateType", "failure_recovery"),
                      "origin": "recovery_incident"},
            )
        except Exception:  # noqa: BLE001 - the audit event is best-effort
            pass
        created.append(skill_store.get_candidate(candidate_id) or {"id": candidate_id})
    return {"ok": True, "created": created, "duplicates": duplicates}


__all__ = ["incident_to_candidate", "promote_incidents"]
