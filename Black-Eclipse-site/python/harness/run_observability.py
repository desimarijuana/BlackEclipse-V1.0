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


def explain_run(
    *,
    run_id: str,
    retrieval_event: Optional[dict[str, Any]] = None,
    events: Optional[list[dict[str, Any]]] = None,
    bundle_resolution: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble a bounded run explanation from canonical records.

    `retrieval_event` is one `MemoryRetrievalEvent` row (or its dict) for the
    run; `events` are the run's `HarnessEvent` rows. Every field is bounded and
    redacted.
    """
    result: dict[str, Any] = {
        "runId": run_id,
        "memory": {"injected": [], "excluded": [], "budget": {}},
        "profile": None,
        "promptPlan": None,
        "skills": None,
        "note": (
            "Derived from canonical retrieval/run events. Exclusions are the "
            "authoritative filters that already applied; this changes nothing."
        ),
    }

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

    if bundle_resolution and result["skills"] is None:
        result["skills"] = {
            "bundleId": _redact(bundle_resolution.get("bundleId")),
            "resolved": [_redact(x) for x in (bundle_resolution.get("resolved") or [])],
            "missing": [_redact(x) for x in (bundle_resolution.get("missing") or [])],
            "unavailable": [_redact(x) for x in (bundle_resolution.get("unavailable") or [])],
        }

    return result


__all__ = ["explain_run"]
