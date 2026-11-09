"""Pure filter/sort/page semantics for the Skills Library list.

The registry owns what exists; this module only shapes the list the UI asked
for, so the query is testable without booting the runtime. Keeping the default
(`limit=None`) as "everything" preserves the historical response shape.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

_RISK_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_MAX_LIMIT = 1000


def _text(skill: dict[str, Any]) -> str:
    tags = skill.get("tags") or []
    parts = (
        skill.get("id"), skill.get("name"), skill.get("description"),
        *tags,
    )
    return " ".join(str(part or "") for part in parts).lower()


def filter_summaries(
    summaries: Sequence[dict[str, Any]],
    *,
    q: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    risk: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Apply the Library filters; empty/`all` means "no filter"."""
    terms = [term for term in (q or "").lower().split() if term]
    out: list[dict[str, Any]] = []
    for skill in summaries:
        if category and category != "all" and skill.get("category") != category:
            continue
        if status and status != "all" and skill.get("status") != status:
            continue
        if risk and risk != "all" and skill.get("riskLevel") != risk:
            continue
        if terms and not all(term in _text(skill) for term in terms):
            continue
        out.append(skill)
    return out


def sort_summaries(
    summaries: Sequence[dict[str, Any]],
    sort: str = "name",
) -> list[dict[str, Any]]:
    """Deterministic sort; an unknown sort falls back to name."""
    items = list(summaries)

    def by_name(skill: dict[str, Any]) -> tuple[str, str]:
        return (str(skill.get("name") or "").lower(), str(skill.get("id") or ""))

    if sort == "status":
        items.sort(key=lambda s: (str(s.get("status") or ""), *by_name(s)))
    elif sort == "risk":
        items.sort(key=lambda s: (_RISK_ORDER.get(str(s.get("riskLevel")), 9), *by_name(s)))
    elif sort == "updated":
        # Two stable passes: name is the tiebreak, then newest-first. An empty
        # timestamp sorts last because "" is the lowest ISO key.
        items.sort(key=by_name)
        items.sort(key=lambda s: str(s.get("updatedAt") or ""), reverse=True)
    else:
        items.sort(key=by_name)
    return items


def page_summaries(
    summaries: Sequence[dict[str, Any]],
    *,
    limit: Optional[int] = None,
    offset: int = 0,
) -> dict[str, Any]:
    """Slice a filtered list and return the exact paging envelope."""
    total = len(summaries)
    start = max(0, int(offset or 0))
    if limit is None:
        effective_limit = total
    else:
        effective_limit = max(1, min(int(limit), _MAX_LIMIT))
    page = list(summaries[start:start + effective_limit])
    return {
        "skills": page,
        "total": total,
        "limit": effective_limit,
        "offset": start,
        "hasMore": start + len(page) < total,
    }
