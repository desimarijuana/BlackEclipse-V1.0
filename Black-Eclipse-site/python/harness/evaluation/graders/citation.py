"""Citation grader.

Grades citation presence, validity, relevance, support, completeness, freshness
and source quality, and detects broken citations, wrong entities, stale citations,
missing citations and irrelevant citations. Citations are parsed deterministically
from the answer (markdown links and bare URLs) and cross-checked against the
trajectory's citation/evidence events.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from . import GradeContext, Grader, GraderResult

_URL_RE = re.compile(r"https?://[^\s)\]}\"'<>]+")
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^\s)]+)\)")


def extract_citations(text: str) -> list[str]:
    found = _MD_LINK_RE.findall(text or "")
    found += _URL_RE.findall(text or "")
    seen: list[str] = []
    for url in found:
        url = url.rstrip(".,;)")
        if url not in seen:
            seen.append(url)
    return seen


class CitationGrader(Grader):
    name = "citation"

    def grade(self, ctx: GradeContext) -> GraderResult:
        config = dict(self.config.get("citation") or getattr(ctx.task, "metadata", {}).get("citation") or {})
        require = bool(config.get("require_citation", False))
        expected_sources = list(config.get("expected_sources") or [])
        allowed_domains = [d.lower() for d in (config.get("allowed_domains") or [])]
        forbidden_domains = [d.lower() for d in (config.get("forbidden_domains") or [])]
        expected_entity = config.get("entity")
        min_citations = int(config.get("min_citations", 1 if require else 0))

        citations = extract_citations(ctx.final_output or "")
        citation_events = [
            e.data for e in getattr(ctx.trajectory, "events", [])
            if e.type in ("citation.created", "research.citation_created")
        ]

        if not config and not citations and not citation_events:
            return GraderResult.unmeasured_result(self.name, "no citation contract or citations")

        failures: list[str] = []

        # Presence / completeness.
        if require and len(citations) < min_citations:
            failures.append(f"citation missing: found {len(citations)}, need {min_citations}")

        # Validity (a parseable absolute URL with a host).
        valid: list[str] = []
        for url in citations:
            host = urlparse(url).netloc
            if not host:
                failures.append(f"broken citation: {url}")
            else:
                valid.append(url)

        # Relevance / support: every expected source should be cited.
        for source in expected_sources:
            if not any(source in c or c in source for c in citations):
                failures.append(f"source not cited: {source}")

        # Irrelevant / forbidden sources.
        for url in citations:
            host = urlparse(url).netloc.lower()
            if forbidden_domains and any(host.endswith(d) for d in forbidden_domains):
                failures.append(f"forbidden source cited: {host}")
            if allowed_domains and not any(host.endswith(d) for d in allowed_domains):
                failures.append(f"irrelevant source cited: {host}")

        # Wrong entity.
        if expected_entity:
            for url in citations:
                if expected_entity.lower() not in url.lower() and expected_entity.lower() not in (ctx.final_output or "").lower():
                    failures.append(f"citation may name the wrong entity: {url}")
                    break

        # Freshness from citation events.
        freshness_days = config.get("freshness_days")
        if freshness_days is not None:
            stale = [e for e in citation_events if _stale(e, float(freshness_days))]
            if stale:
                failures.append(f"{len(stale)} stale citation(s)")

        support = (len(valid) / len(citations)) if citations else (0.0 if require else 1.0)
        passed = not failures
        return GraderResult(
            self.name, support if passed else max(0.0, support - 0.1 * len(failures)), passed,
            details={"citations": citations, "citation_events": len(citation_events)},
            failures=failures,
            evidence=[{"citations": citations}],
        )


def _stale(event: dict[str, Any], freshness_days: float) -> bool:
    import datetime as _dt  # noqa: PLC0415

    stamp = event.get("publishedAt") or event.get("timestamp") or event.get("date")
    if not stamp:
        return False
    try:
        when = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return False
    now = _dt.datetime.now(when.tzinfo) if when.tzinfo else _dt.datetime.now()
    return (now - when).days > freshness_days
