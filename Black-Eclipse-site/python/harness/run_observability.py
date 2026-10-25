"""Run-level memory & skill observability (Phase 7).

Answers, for one run: which facts were injected, which were excluded and why,
which profile/skill-manifest/bundle segments entered the prompt, and the budget
used. It is a DERIVED read model over canonical events (`MemoryRetrievalEvent`
via `/eclipse-memory/retrievals`, and the run's `HarnessEvent` rows) — it never
changes runtime authorization, and it redacts secret-shaped content.

Nothing here is authoritative: the prompt plan and retrieval diagnostics are the
observability record; scope/status/privacy filtering already happened before
injection.
"""

from __future__ import annotations

from typing import Any, Optional

# Bounded payloads so a run explanation cannot become a data dump.
MAX_EXCLUDED = 25
MAX_SELECTED = 25
MAX_SEGMENTS = 20

# Redaction: never surface a secret-shaped token in an explanation.
_SECRET_KEYS = ("secret", "token", "password", "api_key", "apikey", "authorization")


def _redact(text: Any) -> str:
    import re  # noqa: PLC0415

    value = str(text or "")
    return re.sub(
        r"(?i)\b(api[_-]?key|secret|password|passwd|token|authorization|bearer)\b\s*[:=]\s*\S+",
        "[redacted]",
        value,
    )


def _reason_category(reason: str) -> str:
    """Map a free-text exclusion reason to a coarse category for display."""
    text = (reason or "").lower()
    if "scope" in text:
        return "scope"
    if "status" in text or "proposed" in text:
        return "status"
    if "expire" in text:
        return "expiry"
    if "recall" in text and "policy" in text:
        return "permissions"
    if "relevance" in text:
        return "relevance"
    if "budget" in text or "rank limit" in text:
        return "budget"
    if "trust" in text:
        return "trust"
    if "drift" in text or "quarantin" in text:
        return "drift"
    return "other"


def _bounded_delegation(blob: Any) -> Optional[dict[str, Any]]:
    """The persisted fan-out blob as a bounded, redacted read model.

    Only the fields a row needs: identity, status, goal/approach/model, tokens
    and the honest budget. The child's prose and claimed/dropped sentences are
    intentionally NOT re-rendered here — the card's facts come from the runtime,
    never from this diagnostic view.
    """
    if not isinstance(blob, dict):
        return None
    children: list[dict[str, Any]] = []
    for child in (blob.get("children") or [])[:8]:
        if not isinstance(child, dict):
            continue
        row: dict[str, Any] = {
            "childIndex": child.get("childIndex"),
            "runId": _redact(child.get("runId")),
            "status": _redact(child.get("status")),
            "goal": _redact(str(child.get("goal") or ""))[:200],
            "tokens": child.get("tokens"),
        }
        if child.get("approach"):
            row["approach"] = _redact(str(child.get("approach")))[:300]
        if child.get("model"):
            row["model"] = _redact(child.get("model"))
        if child.get("reason"):
            row["reason"] = _redact(child.get("reason"))
        children.append(row)
    budget = blob.get("budget") if isinstance(blob.get("budget"), dict) else {}
    return {
        "delegationId": _redact(blob.get("delegationId")),
        "strategy": _redact(blob.get("strategy") or "split"),
        "winner": blob.get("winner"),
        "children": children,
        "budget": {
            "requestedTokens": budget.get("requestedTokens"),
            "consumedTokens": budget.get("consumedTokens"),
            "children": budget.get("children"),
            "timedOut": budget.get("timedOut"),
            "wallMs": budget.get("wallMs"),
        },
    }


def explain_run(
    *,
    run_id: str,
    retrieval_event: Optional[dict[str, Any]] = None,
    events: Optional[list[dict[str, Any]]] = None,
    bundle_resolution: Optional[dict[str, Any]] = None,
    run: Optional[dict[str, Any]] = None,
    lineage: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble a bounded run explanation from canonical records.

    `retrieval_event` is one `MemoryRetrievalEvent` row (or its dict) for the
    run; `events` are the run's `HarnessEvent` rows. Every field is bounded and
    redacted. `run` (the HarnessRun row) and `lineage` (Phase 1 parent/children)
    add workflow/lineage context; a killed-and-resumed run surfaces its resume
    point from the `run.resumed` event.
    """
    result: dict[str, Any] = {
        "runId": run_id,
        "memory": {"injected": [], "excluded": [], "budget": {}},
        "profile": None,
        "promptPlan": None,
        "skills": None,
        "workflow": None,
        "lineage": None,
        "delegation": None,
        "resumed": None,
        "note": (
            "Derived from canonical retrieval/run events. Exclusions are the "
            "authoritative filters that already applied; this changes nothing."
        ),
    }

    # Workflow + lineage context (Phase 1/5/7). The workflow id + step tree are
    # read from the run row and the `workflow.*` events; the lineage from the
    # bounded parent chain. All content-free (ids/status/scope only).
    if run:
        if run.get("workflowId"):
            result["workflow"] = {"workflowId": _redact(run.get("workflowId")), "steps": []}
        result["lineage"] = {"parentRunId": _redact(run.get("parentRunId"))}
    if run and run.get("delegation"):
        result["delegation"] = _bounded_delegation(run.get("delegation"))
    if lineage is not None:
        merged = result.get("lineage") or {}
        merged.update({
            "runId": _redact(lineage.get("runId")),
            "parents": [
                {"id": _redact(p.get("id")), "status": _redact(p.get("status"))}
                for p in (lineage.get("parents") or [])[:10]
            ],
            "children": [_redact(c) for c in (lineage.get("children") or [])[:50]],
        })
        result["lineage"] = merged

    if retrieval_event:
        selected_ids = retrieval_event.get("selectedIds") or []
        # A retrieval event may store selected ids in `selectionReasons` lines;
        # fall back to parsing the id prefix when a dedicated column is absent.
        try:
            import json as _json  # noqa: PLC0415

            if isinstance(retrieval_event.get("selectionReasons"), str):
                retrieval_event["selectionReasons"] = _json.loads(retrieval_event["selectionReasons"])
            if isinstance(retrieval_event.get("excluded"), str):
                retrieval_event["excluded"] = _json.loads(retrieval_event["excluded"])
        except (ValueError, TypeError):
            pass
        result["memory"]["injected"] = [
            {"id": _redact(i)} for i in list(selected_ids)[:MAX_SELECTED]
        ]
        excluded = []
        for entry in (retrieval_event.get("excluded") or [])[:MAX_EXCLUDED]:
            if isinstance(entry, dict):
                reason = str(entry.get("reason") or "")
                excluded.append({
                    "id": _redact(entry.get("id")),
                    "reason": _redact(reason),
                    "category": _reason_category(reason),
                })
        result["memory"]["excluded"] = excluded
        result["memory"]["budget"] = {
            "usedChars": retrieval_event.get("usedChars"),
            "budgetChars": retrieval_event.get("budgetChars"),
        }
        result["memory"]["selectionReasons"] = [
            _redact(r) for r in (retrieval_event.get("selectionReasons") or [])[:MAX_SELECTED]
        ]

    for event in events or []:
        etype = event.get("type") or ""
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if etype == "prompt.plan":
            result["promptPlan"] = {
                "cacheKey": _redact(data.get("cacheKey")),
                "reusableTokens": data.get("reusableTokens"),
                "segments": [
                    {"id": _redact(s.get("id")), "source": _redact(s.get("source")),
                     "chars": s.get("chars"), "tokenEstimate": s.get("tokenEstimate"),
                     "version": _redact(s.get("version"))}
                    for s in (data.get("segments") or [])[:MAX_SEGMENTS]
                ],
            }
        elif etype == "memory.profile_built":
            result["profile"] = {
                "snapshotId": _redact(data.get("snapshotId")),
                "entries": data.get("entries"),
                "charCount": data.get("charCount"),
                "tokenEstimate": data.get("tokenEstimate"),
                "excluded": data.get("excluded"),
            }
        elif etype == "skill.bundle_resolved":
            result["skills"] = {
                "bundleId": _redact(data.get("bundleId")),
                "resolved": [_redact(x) for x in (data.get("resolved") or [])],
                "missing": [_redact(x) for x in (data.get("missing") or [])],
                "unavailable": [_redact(x) for x in (data.get("unavailable") or [])],
                "provenance": _redact(data.get("provenance")),
            }
        elif etype == "run.resumed":
            # A killed-and-resumed run surfaces WHERE it resumed (Phase 7).
            result["resumed"] = {
                "checkpointId": _redact(data.get("checkpointId")),
                "step": data.get("step"),
            }
        elif etype.startswith("workflow."):
            # Per-step workflow events name the step + its declared scope.
            wf = result.get("workflow")
            if not isinstance(wf, dict):
                wf = {"workflowId": None, "steps": []}
                result["workflow"] = wf
            wf.setdefault("steps", [])
            step = {
                "stepId": _redact(data.get("stepId")),
                "kind": _redact(data.get("kind")),
                "status": _redact(data.get("status")),
                "scope": [_redact(s) for s in (data.get("scope") or [])][:50],
                "runId": _redact(data.get("runId")),
            }
            wf["steps"].append(step)

    if bundle_resolution and result["skills"] is None:
        result["skills"] = {
            "bundleId": _redact(bundle_resolution.get("bundleId")),
            "resolved": [_redact(x) for x in (bundle_resolution.get("resolved") or [])],
            "missing": [_redact(x) for x in (bundle_resolution.get("missing") or [])],
            "unavailable": [_redact(x) for x in (bundle_resolution.get("unavailable") or [])],
        }

    return result


__all__ = ["explain_run"]
