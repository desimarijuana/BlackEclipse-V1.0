"""Construction procedure learning (round 4, W6) — inert until promoted.

A successful UI construction sequence (engineer → implement → register) is the
procedure the recorded clock run had to re-derive: what was missing was not a
recovery strategy but the KNOW-HOW — which files to touch, which registration
steps to take, which ceiling not to cross. This module encodes that sequence as
an inert `successful_procedure` candidate on the EXISTING learning store, with
the SAME candidate type, signature scheme and review path the rest of the
learning system uses. It never creates or enables a skill itself.

Conservative by construction, like `recovery/learning.py`:

  * the candidate exists after the FIRST successful construction (the sequence is
    strong, observable evidence — a registration that actually ran);
  * the DRAFT is opened only on RECURRENCE (`learning_recurrence` >= 2), so a
    single lucky build does not become a procedure;
  * one stable signature deduplicates every construction into one candidate —
    the procedure is "engineer + register a UI capability", not one per widget;
  * the draft is inert (`status: draft`, `evaluationStatus: not_evaluated`);
    activation remains the existing evaluation + operator promotion.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

#: The two tools that mark a construction sequence. The CLOSE tool (registration)
#: is required — it is the loop-closing act that proves the capability was really
#: added to the catalog, not merely attempted.
CONSTRUCTION_START_TOOL = "ui_start_engineering"
CONSTRUCTION_CLOSE_TOOL = "ui_register_engineered_component"
CONSTRUCTION_TOOLS: tuple[str, ...] = (CONSTRUCTION_START_TOOL, CONSTRUCTION_CLOSE_TOOL)

#: The stable problem text IS the dedupe input — one candidate for the
#: construction procedure, however many components get engineered.
CONSTRUCTION_PROBLEM = (
    "A requested UI capability was missing from the catalog and had to be "
    "engineered, implemented and registered."
)

#: The re-derived know-how, encoded: the exact steps and constraints the clock
#: run had to work out for itself (the widget layer's files and its size budget).
CONSTRUCTION_PROCEDURE: tuple[dict[str, str], ...] = (
    {"step": 1, "action": "escalate",
     "detail": "call ui_start_engineering with the request; it re-checks the catalog and files a durable engineering task — never answer \"cannot\""},
    {"step": 2, "action": "implement",
     "detail": "implement the component in src/lib/dashboard/widgets.tsx and keep the file within the repo's 1200-line hard ceiling — split a module instead of exceeding it"},
    {"step": 3, "action": "register",
     "detail": "register the widget definition and renderer in src/lib/dashboard/registry.tsx"},
    {"step": 4, "action": "icon",
     "detail": "add the widget's icon name to the ICONS map in src/lib/dashboard/registry.tsx — an unknown icon name renders blank"},
    {"step": 5, "action": "verify",
     "detail": "run npx tsc --noEmit and the front-end tests until they pass; never claim success without a zero-exit run"},
    {"step": 6, "action": "catalog",
     "detail": "call ui_register_engineered_component to register the component in the ONE UI catalog — it satisfies the \"registered in the UI catalog\" criterion and attaches the ui-component artifact"},
    {"step": 7, "action": "compose",
     "detail": "the component is now Compose-able: a follow-up request can place it on a page with ui_add_widget"},
)

CONSTRUCTION_GENERALIZATION = (
    "The escalate → implement → register → compose shape generalizes to any "
    "missing UI capability; the concrete file paths and the 1200-line ceiling "
    "are repo facts that must be re-checked if the widget layer moves."
)

CONSTRUCTION_LIMITATIONS = (
    "Learned from an observed construction sequence. The procedure is inert "
    "until evaluated and promoted by an operator; re-verify the named files and "
    "the size ceiling before reuse."
)

#: The recurrence key for the construction procedure. Deliberately stable: two
#: construction runs recur even when the surrounding tool calls differ.
CONSTRUCTION_RECURRENCE_KEY = hashlib.sha256(
    b"successful_procedure|ui-construction"
).hexdigest()[:32]

_MIN_CONSTRUCTION_RECURRENCE = 2


def _tool_records(run_store: Any, run_id: str) -> list[dict[str, Any]]:
    try:
        rows = run_store.list_tool_executions(run_id)
    except Exception:  # noqa: BLE001 - a missing trace is no evidence
        return []
    return [r for r in (rows or []) if isinstance(r, dict)]


def construction_evidence(tools: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The construction signal in a run's tool executions, or None.

    Requires a SUCCESSFUL `ui_register_engineered_component` — the registration
    actually ran. A successful `ui_start_engineering` in the same trace is
    recorded as extra evidence but not required (the registration often happens
    in the engineering task's own run).
    """
    registered = [
        t for t in tools
        if str(t.get("name") or "") == CONSTRUCTION_CLOSE_TOOL and t.get("ok")
    ]
    if not registered:
        return None
    started = [
        t for t in tools
        if str(t.get("name") or "") == CONSTRUCTION_START_TOOL and t.get("ok")
    ]
    components: list[str] = []
    for record in registered:
        args = record.get("args")
        spec = args.get("component") if isinstance(args, dict) else None
        component_id = spec.get("id") if isinstance(spec, dict) else None
        if component_id and str(component_id) not in components:
            components.append(str(component_id))
    return {
        "started": bool(started),
        "registered": len(registered),
        "components": components[:5],
    }


def construction_candidate_draft(run_id: str, run_store: Any) -> Optional[dict[str, Any]]:
    """The inert candidate draft for a successful construction run, or None."""
    tools = _tool_records(run_store, run_id)
    evidence = construction_evidence(tools)
    if evidence is None:
        return None
    observed = "successful ui_register_engineered_component"
    if evidence["started"]:
        observed = (
            "successful ui_start_engineering → engineering task → "
            "ui_register_engineered_component"
        )
    if evidence["components"]:
        observed += f" (component(s): {', '.join(evidence['components'])})"
    return {
        "candidateType": "successful_procedure",
        "title": "Engineer a missing UI capability and register it",
        "problem": CONSTRUCTION_PROBLEM,
        "observedBehavior": f"Run {run_id}: {observed}.",
        "proposedLesson": (
            "When a UI request names a capability the catalog cannot satisfy, "
            "escalate to an engineering task, implement + register the component "
            "within the widget layer's constraints, then Compose it."
        ),
        "proposedProcedure": [dict(step) for step in CONSTRUCTION_PROCEDURE],
        "evidenceReferences": [
            {"kind": "tool", "name": str(t.get("name")), "at": t.get("createdAt")}
            for t in tools
            if t.get("ok") and str(t.get("name") or "") in CONSTRUCTION_TOOLS
        ],
        "confidence": 0.6,
        "generalizationNotes": CONSTRUCTION_GENERALIZATION,
        "knownLimitations": CONSTRUCTION_LIMITATIONS,
        "scope": {"capability": "ui_engineering", "scopeClaim": "the dashboard widget layer"},
        "sourceRunId": run_id,
    }


def construction_candidate_from_incident(
    incident: dict[str, Any], attempts: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """The SAME candidate, derived from a resolved capability incident.

    Shares `CONSTRUCTION_PROBLEM` with the run-trace path, so the two sources
    collapse into ONE candidate by signature. Used by
    `recovery/learning.py::incident_to_candidate` for capability incidents — a
    resolved capability gap's reusable lesson is the construction procedure, not
    a generic failure recovery.
    """
    from .learning import _signature  # noqa: PLC0415 - shared signature scheme

    capability = str(incident.get("message") or incident.get("code") or "a UI capability")
    return {
        "candidateType": "successful_procedure",
        "title": "Engineer a missing UI capability and register it",
        "problem": CONSTRUCTION_PROBLEM,
        "observedBehavior": f"Resolved capability incident: {capability[:300]}",
        "proposedLesson": (
            "When a UI request names a capability the catalog cannot satisfy, "
            "escalate to an engineering task, implement + register the component "
            "within the widget layer's constraints, then Compose it."
        ),
        "proposedProcedure": [dict(step) for step in CONSTRUCTION_PROCEDURE],
        "evidenceReferences": [
            {"type": "recovery_incident", "id": incident.get("id")},
            *[
                {"type": "recovery_attempt", "id": a.get("id")}
                for a in (attempts or [])
                if a.get("outcome") in ("succeeded", "resolved")
            ],
        ],
        "confidence": 0.6,
        "generalizationNotes": CONSTRUCTION_GENERALIZATION,
        "knownLimitations": CONSTRUCTION_LIMITATIONS,
        "scope": {"capability": "ui_engineering", "scopeClaim": "the dashboard widget layer"},
        "signature": _signature("successful_procedure", CONSTRUCTION_PROBLEM),
        "sourceRunId": incident.get("runId"),
    }


# ── Recurrence + the draft gate ───────────────────────────────────────────────


def record_construction_recurrence(run_store: Any, run_id: str) -> int:
    """Record this construction run against the stable key. Never raises."""
    record = getattr(run_store, "record_learning_recurrence", None)
    if record is None:
        return 0
    try:
        return int(record(CONSTRUCTION_RECURRENCE_KEY, run_id))
    except Exception:  # noqa: BLE001 - the ledger is best-effort
        return 0


def construction_recurrence(run_store: Any) -> int:
    """How many construction runs have been seen (0 when unseen)."""
    counter = getattr(run_store, "learning_recurrence", None)
    if counter is None:
        return 0
    try:
        return int(counter(CONSTRUCTION_RECURRENCE_KEY))
    except Exception:  # noqa: BLE001
        return 0


def construction_candidate(skill_store: Any) -> Optional[dict[str, Any]]:
    """The stored construction candidate (by its stable signature), or None."""
    from .learning import _signature  # noqa: PLC0415 - shared signature scheme

    try:
        return skill_store.find_candidate_by_signature(
            _signature("successful_procedure", CONSTRUCTION_PROBLEM)
        )
    except Exception:  # noqa: BLE001
        return None


def maybe_draft_construction(
    run_id: str,
    run_store: Any,
    skill_store: Any,
    *,
    available_tools: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Open the inert draft when the SAME construction has recurred.

    Called from the post-run review. Drafts ONLY when: this run carries the
    construction evidence, the candidate exists and is still `detected`, and
    recurrence >= 2. The draft is inert — `propose_draft` stores a
    `status: draft` / `evaluationStatus: not_evaluated` version; enabling it
    remains the existing evaluation + operator promotion, which this module
    never calls.

    `available_tools` defaults to the construction tools themselves: a tool that
    EXECUTED in a recorded run is by definition registered, so no tool name is
    invented.
    """
    if construction_candidate_draft(run_id, run_store) is None:
        return {"ok": True, "drafted": False, "reason": "no construction evidence in this run"}
    candidate = construction_candidate(skill_store)
    if candidate is None:
        return {"ok": True, "drafted": False, "reason": "no construction candidate to draft"}
    if str(candidate.get("status")) != "detected":
        return {
            "ok": True, "drafted": False,
            "reason": f"candidate is {candidate.get('status')}",
            "candidateId": candidate.get("id"),
        }
    recurrence = construction_recurrence(run_store)
    if recurrence < _MIN_CONSTRUCTION_RECURRENCE:
        return {
            "ok": True, "drafted": False,
            "reason": "recurrence evidence is not yet sufficient",
            "candidateId": candidate.get("id"), "recurrence": recurrence,
        }
    from .draft import propose_draft  # noqa: PLC0415 - same draft path as the operator route

    tools = list(available_tools) if available_tools is not None else list(CONSTRUCTION_TOOLS)
    result = propose_draft(str(candidate["id"]), skill_store, available_tools=tools)
    if not result.get("ok"):
        return {
            "ok": False, "drafted": False, "reason": result.get("error"),
            "candidateId": candidate.get("id"), "recurrence": recurrence,
        }
    draft = result.get("draft") or {}
    return {
        "ok": True, "drafted": True,
        "candidateId": candidate.get("id"), "skillId": draft.get("id"),
        "recurrence": recurrence, "reusable": result.get("reusable"),
        "issues": result.get("issues") or [],
    }


__all__ = [
    "CONSTRUCTION_CLOSE_TOOL",
    "CONSTRUCTION_GENERALIZATION",
    "CONSTRUCTION_LIMITATIONS",
    "CONSTRUCTION_PROBLEM",
    "CONSTRUCTION_PROCEDURE",
    "CONSTRUCTION_RECURRENCE_KEY",
    "CONSTRUCTION_START_TOOL",
    "CONSTRUCTION_TOOLS",
    "construction_candidate",
    "construction_candidate_draft",
    "construction_candidate_from_incident",
    "construction_evidence",
    "construction_recurrence",
    "maybe_draft_construction",
    "record_construction_recurrence",
]
