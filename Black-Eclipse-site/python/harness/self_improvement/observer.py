"""Deterministic observation pass for RSL.

R1 is deliberately model-free. One call:

* reads the ONE recurrence ledger and creates an inert `EvolutionCandidate` when
  a mistake category crosses `RECURRENCE_THRESHOLD`;
* mines a failed run into a deduplicated `EvaluationCandidate` (evidence only —
  no expected behavior is invented);
* emits `self_improvement.candidate_created` for each new candidate.

It never proposes operations, runs a candidate or activates anything. A failure
is returned as a bounded error string so the caller (post-run review) can never
be broken by observation.
"""

from __future__ import annotations

from typing import Any, Optional

from ..code import evolution
from .config import RSLConfig
from .models import Observation

_SINCE = "1970-01-01T00:00:00.000Z"


def _emit_candidate_created(run_store: Any, run_id: str, data: dict[str, Any]) -> None:
    """Persist one bounded event without letting an event-store failure escape."""
    try:
        events = run_store.list_events(run_id)
        seq = max((int(event.get("seq") or 0) for event in events), default=0) + 1
        run_store.append_event(
            run_id, "self_improvement.candidate_created", seq, data,
        )
    except Exception:  # noqa: BLE001 - observation is best-effort
        pass


def _bounded_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": candidate.get("id"),
        "signature": candidate.get("signature"),
        "sourceCategory": candidate.get("sourceCategory"),
        "observedCount": candidate.get("observedCount"),
        "problemStatement": str(candidate.get("problemStatement") or "")[:500],
        "targetPath": candidate.get("targetPath"),
        "status": candidate.get("status"),
        "createdByRunId": candidate.get("createdByRunId"),
        "createdAt": candidate.get("createdAt"),
    }


def _bounded_mined(mined: dict[str, Any]) -> dict[str, Any]:
    return {
        key: mined.get(key)
        for key in (
            "created", "deduplicated", "candidateId", "signature", "category", "labels",
        )
        if key in mined
    }


def observe_run(
    run_id: str,
    status: str,
    *,
    run_store: Any,
    eval_store: Any = None,
    config: Optional[RSLConfig] = None,
) -> dict[str, Any]:
    """Observe one finished run and create only inert, deduplicated candidates.

    `mode=off` is a strict no-op (it does not even open an evaluation store).
    Every non-off mode runs this same deterministic pass; candidate execution is
    introduced in a later RSL phase, not here.
    """
    settings = config or RSLConfig.from_env()
    result: dict[str, Any] = {
        "mode": settings.mode,
        "runId": run_id,
        "observations": [],
        "candidates": [],
        "mined": None,
        "errors": [],
    }
    if settings.is_off:
        return result

    # 1) Recurrence -> an inert evolution candidate. The ledger decides; the
    # bridge dedupes by signature and never writes the ledger itself.
    try:
        created = evolution.candidates_from_mistakes(
            store=run_store,
            since_iso=_SINCE,
            max_candidates=settings.max_candidates,
            created_by_run_id=run_id,
        )
    except Exception as exc:  # noqa: BLE001 - observation must not break a review
        result["errors"].append(f"recurrence: {exc}")
        created = []

    for candidate in created:
        category = str(candidate.get("sourceCategory") or "")
        observation = Observation(
            kind="mistake_recurrence",
            signature=str(candidate.get("signature") or ""),
            runId=run_id,
            category=category,
            observedCount=int(candidate.get("observedCount") or 0),
            targetHint=evolution.CATEGORY_TARGETS.get(category),
            evidenceRunIds=(run_id,),
        )
        result["observations"].append(observation.to_dict())
        result["candidates"].append(_bounded_candidate(candidate))
        _emit_candidate_created(run_store, run_id, {
            "kind": "evolution",
            "candidateId": candidate.get("id"),
            "signature": candidate.get("signature"),
            "category": category,
            "observedCount": candidate.get("observedCount"),
        })

    # 2) A failed run becomes evidence for the evaluation suite. Mining is
    # bounded by its signature dedupe and never invents an expected behavior.
    if str(status or "").strip().lower() == "failed":
        try:
            if eval_store is None:
                from ..evaluation.store import EvaluationStore  # noqa: PLC0415

                eval_store = EvaluationStore(run_store)
            from ..evaluation.mining import mine_from_store  # noqa: PLC0415

            mined = mine_from_store(eval_store, run_store, run_id)
            result["mined"] = _bounded_mined(mined)
            if mined.get("created"):
                observation = Observation(
                    kind="mined_failure",
                    signature=str(mined.get("signature") or ""),
                    runId=run_id,
                    category=str(mined.get("category") or ""),
                    observedCount=1,
                    targetHint=None,
                    evidenceRunIds=(run_id,),
                )
                result["observations"].append(observation.to_dict())
                _emit_candidate_created(run_store, run_id, {
                    "kind": "mined",
                    "candidateId": mined.get("candidateId"),
                    "signature": mined.get("signature"),
                    "category": mined.get("category"),
                })
        except Exception as exc:  # noqa: BLE001 - mining is best-effort
            result["errors"].append(f"mining: {exc}")

    return result


__all__ = ["observe_run"]
