"""Deterministic research query expansion.

`research.queries` turns a question plus the gaps/claims a run already named
into concrete search queries, including disconfirming (counter-evidence)
queries. It is PURE: no store, no network, no model. The output feeds
`research.web_search` (often through `flow.parallel`), which keeps the search
plan inspectable and reproducible.

Nothing here decides truth. It only proposes what to look for; a result is still
a pointer until a page is fetched, extracted and verified.
"""

from __future__ import annotations

import json
from typing import Any

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_QUERIES = 20
_WEAK_STATUSES = {"UNSUPPORTED", "CONTRADICTED", "OUTDATED", "AMBIGUOUS"}


def _rows(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("gaps", "claims", "items"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [raw]
    return []


def exec_queries(context: NodeExecContext) -> dict[str, Any]:
    question = str(
        context.inputs.get("question") or context.config.get("question") or ""
    ).strip()
    claims = _rows(context.inputs.get("claims"))
    raw_claims = context.config.get("claimsJson")
    if isinstance(raw_claims, str) and raw_claims.strip():
        try:
            raw_claims = json.loads(raw_claims)
        except (TypeError, ValueError) as exc:
            raise ValueError("claimsJson must be a JSON array") from exc
    claims = claims + _rows(raw_claims)
    gaps = _rows(context.inputs.get("gaps"))

    try:
        max_queries = int(context.config.get("maxQueries", 8))
    except (TypeError, ValueError) as exc:
        raise ValueError("maxQueries must be a whole number") from exc
    max_queries = max(1, min(max_queries, MAX_QUERIES))
    include_counter = bool(context.config.get("includeCounterEvidence", True))
    include_primary = bool(context.config.get("includePrimarySources", True))
    site_filter = str(context.config.get("siteFilter") or "").strip()

    if not question and not claims and not gaps:
        raise ValueError("question or claims/gaps is required")

    proposed: list[dict[str, Any]] = []
    if question:
        proposed.append({"query": question, "purpose": "answer", "origin": "question"})
        if include_primary:
            primary = f"{question} primary source"
            if site_filter:
                primary = f"site:{site_filter} {question}"
            proposed.append({
                "query": primary,
                "purpose": "primary_source",
                "origin": "question",
            })

    for gap in gaps:
        text = str(gap.get("text") or gap.get("reason") or "").strip()
        kind = str(gap.get("kind") or "").strip().lower()
        if not text:
            continue
        if kind == "question":
            proposed.append({"query": text, "purpose": "gap", "origin": "gap"})
        elif kind == "claim":
            proposed.append({
                "query": f"{text} evidence", "purpose": "support", "origin": "gap",
            })
            if include_counter:
                proposed.append({
                    "query": f"{text} contradicting evidence",
                    "purpose": "counter_evidence",
                    "origin": "gap",
                })

    for claim in claims:
        text = str(claim.get("text") or claim.get("claimText") or "").strip()
        if not text:
            continue
        status = str(claim.get("status") or "").strip().upper()
        if status and status not in _WEAK_STATUSES:
            continue
        proposed.append({"query": f"{text} evidence", "purpose": "support", "origin": "claim"})
        if include_counter:
            proposed.append({
                "query": f"{text} contradicting evidence",
                "purpose": "counter_evidence",
                "origin": "claim",
            })

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in proposed:
        query = " ".join(str(entry["query"]).split())
        key = query.casefold()
        if not query or key in seen:
            continue
        seen.add(key)
        deduped.append({**entry, "query": query})

    by_purpose: dict[str, int] = {}
    for entry in deduped:
        purpose = str(entry["purpose"])
        by_purpose[purpose] = by_purpose.get(purpose, 0) + 1
    page = deduped[:max_queries]
    context.emit(f"{len(page)}/{len(deduped)} research quer(ies) proposed")
    return {
        "queries": page,
        "summary": {
            "total": len(deduped),
            "count": len(page),
            "truncated": len(page) < len(deduped),
            "maxQueries": max_queries,
            "byPurpose": by_purpose,
            "counterEvidence": include_counter,
            "siteFilter": site_filter or None,
            "status": "OK",
        },
    }


def build_research_query_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="research.queries", version="1.0.0", label="Plan search queries",
            category="research",
            inputs=(
                PortDef(id="question", name="Question", type=PortType.STRING, optional=True),
                PortDef(id="claims", name="Claims", type=PortType.ARRAY, optional=True),
                PortDef(id="gaps", name="Gaps", type=PortType.ARRAY, optional=True),
            ),
            outputs=(
                PortDef(id="queries", name="Queries", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("question", "string", "", max_length=2_000),
                ConfigField("claimsJson", "array", []),
                ConfigField("includeCounterEvidence", "boolean", True),
                ConfigField("includePrimarySources", "boolean", True),
                ConfigField("siteFilter", "string", "", max_length=200),
                ConfigField("maxQueries", "integer", 8, minimum=1, maximum=MAX_QUERIES),
            ),
            capabilities=(),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_queries,
            metadata={"docs": "Pure deterministic query expansion from a question, named gaps and weak claims. Adds a disconfirming query per weak claim; a search result is still a pointer, not evidence."},
        ),
    ]


__all__ = ["build_research_query_nodes", "exec_queries"]
