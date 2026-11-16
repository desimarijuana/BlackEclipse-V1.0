"""The per-run outcome envelope — one record naming how a run was routed (W1.3).

A run that did not get done must be diagnosable from ONE record, not from a
replay of scattered facts. The round-4 meta loop needs four of them: the
**intent verdict** (what the router decided), the **resolved surface and
allowlist** (what the run could actually do), the **refusal code** (why it
stopped) and the **capability gap** (what was missing).

Three of the four were already persisted — the run row carries the agent and
the terminal error code, the `prompt.plan` event carries the resolved surface
and allowlist summary, the `ui.capability_gap` event carries the gap and the
`recovery.decided` event its incident id. The **intent verdict had no home at
all**: it died with the tool result, so this module owns it (`RunOutcome`),
the same pattern `run_lineage.py` uses for its own columns, rather than growing
the ratcheted `persistence.py`.

Nothing here changes runtime behaviour. The envelope is a DERIVED, read-only
record; a fact that was never recorded is `null` — never guessed, never
inferred from prose.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

log = logging.getLogger("harness.run_outcome")

#: How many allowlist names the envelope names (bounded). The digest covers the
#: WHOLE list, so two runs can be compared without dumping hundreds of names.
MAX_ALLOWLIST_NAMES = 40

#: How many capability-gap texts / incident ids the envelope names (bounded).
MAX_GAP_ITEMS = 5

#: The intent verdicts the UI router can return. Anything else is recorded as
#: given (the record is bounded and redacted), never widened into this set.
INTENT_VERDICTS = ("compose", "engineer", "both", "escalate", "unknown")


def _digest(names: list[str]) -> str:
    """A stable digest of a name list (so two allowlists can be compared)."""
    joined = "\n".join(names).encode("utf-8")
    return "sha256:" + hashlib.sha256(joined).hexdigest()[:32]


def surface_summary(agent_id: str, allowed: Optional[set[str]]) -> dict[str, Any]:
    """The resolved surface + allowlist of one run (bounded, comparable).

    `allowed is None` means the unrestricted case (every tool) — it is recorded
    as such, never as an empty list that would read as "no tools".
    """
    if allowed is None:
        return {
            "agentId": str(agent_id or ""),
            "allowlist": {"unrestricted": True, "count": None, "names": [], "digest": None},
        }
    names = sorted(str(name) for name in allowed)
    return {
        "agentId": str(agent_id or ""),
        "allowlist": {
            "unrestricted": False,
            "count": len(names),
            "names": names[:MAX_ALLOWLIST_NAMES],
            "digest": _digest(names),
        },
    }


# ── The intent verdict (the one fact with no home before W1.3) ────────────────


def record_intent(store: Any, run_id: str, intent: dict[str, Any]) -> None:
    """Record the run's intent verdict. The FIRST verdict wins — it is the routing.

    Best-effort and additive: a failure here never breaks a run, and a second
    verdict for the same run does not overwrite the routing decision.
    """
    if store is None or not run_id or not isinstance(intent, dict):
        return
    db = getattr(store, "_db", None)
    if db is None:
        return
    try:
        from .persistence import now_iso  # noqa: PLC0415

        db.execute(
            "CREATE TABLE IF NOT EXISTS RunOutcome ("
            "  runId TEXT PRIMARY KEY, intent TEXT NOT NULL, createdAt TEXT NOT NULL)"
        )
        db.execute(
            "INSERT OR IGNORE INTO RunOutcome (runId, intent, createdAt) VALUES (?, ?, ?)",
            (str(run_id), json.dumps(intent, default=str)[:4_000], now_iso()),
        )
        db.commit()
    except Exception:  # noqa: BLE001 - the record is additive; never break a run
        log.debug("intent record failed for run %s", run_id, exc_info=True)


def read_intent(store: Any, run_id: str) -> Optional[dict[str, Any]]:
    """The run's recorded intent verdict, or None when none was recorded."""
    if store is None or not run_id:
        return None
    db = getattr(store, "_db", None)
    if db is None:
        return None
    try:
        row = db.execute(
            "SELECT intent FROM RunOutcome WHERE runId = ?", (str(run_id),),
        ).fetchone()
    except Exception:  # noqa: BLE001 - a missing table is no record
        return None
    if not row:
        return None
    try:
        value = json.loads(row[0]) if row[0] else None
    except Exception:  # noqa: BLE001 - a malformed record is no record
        return None
    return value if isinstance(value, dict) else None


# ── The envelope ──────────────────────────────────────────────────────────────


def _event_data(event: Any) -> dict[str, Any]:
    data = event.get("data") if isinstance(event, dict) else None
    return data if isinstance(data, dict) else {}


def _intent_block(intent: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not intent:
        return None
    verdict = str(intent.get("verdict") or "").strip().lower()
    witness = [str(w)[:80] for w in (intent.get("witness") or [])][:MAX_GAP_ITEMS]
    return {
        "verdict": verdict if verdict in INTENT_VERDICTS else "unknown",
        "reason": str(intent.get("reason") or "")[:300],
        "witness": witness,
        "capabilityGap": bool(intent.get("capabilityGap")),
    }


def _surface_block(run: Optional[dict[str, Any]], events: list[Any]) -> dict[str, Any]:
    """The resolved surface + allowlist (the run row's agent + the plan event)."""
    block: dict[str, Any] = {
        "agentId": str((run or {}).get("agentId") or ""),
        "allowlist": None,
    }
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "prompt.plan":
            continue
        data = _event_data(event)
        surface = data.get("surface")
        if isinstance(surface, dict):
            block["agentId"] = str(surface.get("agentId") or block["agentId"])
            allowlist = surface.get("allowlist")
            if isinstance(allowlist, dict):
                block["allowlist"] = {
                    "unrestricted": bool(allowlist.get("unrestricted")),
                    "count": allowlist.get("count"),
                    "names": [str(n)[:80] for n in (allowlist.get("names") or [])][:MAX_ALLOWLIST_NAMES],
                    "digest": allowlist.get("digest"),
                }
        break
    return block


def _refusal_code(run: Optional[dict[str, Any]], events: list[Any]) -> Optional[str]:
    """The refusal code the runtime recorded — the run's error, else a refusal event."""
    error = (run or {}).get("error")
    if isinstance(error, dict):
        code = str(error.get("code") or "").strip()
        if code:
            return code[:120]
    for event in events:
        data = _event_data(event)
        status = str(data.get("status") or "").lower()
        refused = bool(data.get("refused")) or status == "refused"
        if not refused:
            continue
        code = str(data.get("code") or "").strip()
        if code:
            return code[:120]
    return None


def _gap_block(events: list[Any]) -> Optional[dict[str, Any]]:
    """The capability gap this run recorded, with its recovery incident ids."""
    gap: Optional[dict[str, Any]] = None
    incidents: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        etype = str(event.get("type") or "")
        data = _event_data(event)
        if etype in ("ui.capability_gap", "capability.offer") or (
            data.get("capabilityGap") and str(data.get("code") or "") == "UI_CAPABILITY_GAP"
        ):
            gap = {
                "code": str(data.get("code") or "UI_CAPABILITY_GAP")[:120],
                "capability": str(
                    data.get("need") or data.get("capability") or ""
                )[:300],
                "mode": str(data.get("kind") or data.get("mode") or "")[:40],
                "offer": bool(data.get("offer")) or etype == "capability.offer",
            }
        elif etype == "recovery.decided":
            incident = str(data.get("incidentId") or "").strip()
            if incident and incident not in incidents:
                incidents.append(incident[:120])
    if gap is None:
        return None
    gap["incidentIds"] = incidents[:MAX_GAP_ITEMS]
    return gap


def _recovery_block(events: list[Any]) -> Optional[dict[str, Any]]:
    """How the bounded answer recovery ended, derived from its own events.

    `None` means the run never needed it — never "recovered zero times". The
    block is bounded and names only the routes the guard suggested, so an
    operator can see whether a refusal was routed or accepted.
    """
    started = 0
    exhausted = False
    recovered = False
    routes: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        etype = str(event.get("type") or "")
        if etype == "answer.recovery_started":
            started += 1
            for name in (_event_data(event).get("nextRoutes") or []):
                route = str(name)[:80]
                if route and route not in routes:
                    routes.append(route)
        elif etype == "answer.recovery_exhausted":
            exhausted = True
        elif etype == "answer.recovered":
            recovered = True
    if not started and not exhausted:
        return None
    return {
        "attempts": started,
        "recovered": recovered,
        "exhausted": exhausted,
        "nextRoutes": routes[:8],
    }


def _quant_block(
    rows: list[Any],
    run: Optional[dict[str, Any]],
    tool_executions: Optional[list[Any]],
) -> Optional[dict[str, Any]]:
    """The derived quant-completeness record, or None when the turn was not quant."""
    plan: Optional[dict[str, Any]] = None
    for event in rows:
        if isinstance(event, dict) and event.get("type") == "quant.plan":
            plan = _event_data(event)
            break
    if not plan:
        return None
    from .quant_intent import evaluate_quant_outcome  # noqa: PLC0415

    names = [
        str(row.get("name") or "") if isinstance(row, dict) else ""
        for row in (tool_executions or [])
    ]
    return evaluate_quant_outcome(
        plan, names, str((run or {}).get("output") or "")
    )


def _goal_block(store: Any, run_id: str) -> Optional[dict[str, Any]]:
    if store is None:
        return None
    try:
        from .goals import GoalStore  # noqa: PLC0415

        return GoalStore(store).goal_for_run(run_id)
    except Exception:  # noqa: BLE001 - an outcome is best-effort, never fatal
        return None


def _evidence_block(store: Any, run_id: str) -> Optional[dict[str, Any]]:
    if store is None:
        return None
    try:
        from .goals import EvidenceLedger  # noqa: PLC0415

        ledger = EvidenceLedger(store)
        summary = ledger.summary(run_id)
        return {**summary, "verdict": ledger.verdict(run_id).to_dict()}
    except Exception:  # noqa: BLE001
        return None


def build_outcome_envelope(
    *,
    run_id: str,
    run: Optional[dict[str, Any]] = None,
    events: Optional[list[Any]] = None,
    tool_executions: Optional[list[Any]] = None,
    intent: Optional[dict[str, Any]] = None,
    store: Any = None,
) -> dict[str, Any]:
    """Assemble the ONE record that names how a run was routed.

    Derived from the run's canonical records (the run row, its events and its
    tool executions) plus the recorded intent verdict. Every field is bounded;
    a fact that was never recorded is `null`.
    """
    rows = list(events or [])
    envelope: dict[str, Any] = {
        "runId": str(run_id),
        "intent": _intent_block(intent),
        "surface": _surface_block(run, rows),
        "refusalCode": _refusal_code(run, rows),
        "capabilityGap": _gap_block(rows),
        # Bounded answer recovery: a refused answer that was sent back to an
        # untried route (and whether it recovered or was accepted).
        "answerRecovery": _recovery_block(rows),
        "quant": _quant_block(rows, run, tool_executions),
        # C4: the goal step this run executed and the evidence it recorded.
        "goal": _goal_block(store, run_id),
        "evidence": _evidence_block(store, run_id),
        "toolCalls": len(list(tool_executions or [])),
        "note": (
            "Derived from the run's canonical records. A fact that was never "
            "recorded is null — never inferred."
        ),
    }
    return envelope


__all__ = [
    "INTENT_VERDICTS",
    "MAX_ALLOWLIST_NAMES",
    "build_outcome_envelope",
    "read_intent",
    "record_intent",
    "surface_summary",
]
