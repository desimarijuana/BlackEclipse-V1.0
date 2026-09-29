"""Run-level source collection for ORDINARY (non-gated) agent runs.

The gated research flow builds rich `Citation`/`ResponseMetadata` records for its
evidence. An ordinary chat run has no equivalent: its retrieval happens inside
tool calls and, before this module, the provenance it gathered was never
aggregated into anything the chat UI could render as Sources. This collector
closes that gap.

It is a DERIVED read model over the retrieval results a run actually produced:

  * citations are built ONLY from retrieved evidence — field-by-field copied,
    never inferred (reusing the research citation builder, so there is one shape),
  * every consulted source is listed with its tier/url/title when known,
  * sources that could not be retrieved become `failedRoutes`,
  * sources that disagree are surfaced as conflicts.

It produces the SAME shape the existing `research` blob uses, so the chat
"Sources" panel renders it with no new wire contract. Nothing here fabricates a
URL, source name, or date, and nothing changes runtime authorization.
"""

from __future__ import annotations

from typing import Any, Optional

from .research.citations import Citation, build_citations
from .retrieval.contract import FinancialRetrievalResult

MAX_CITATIONS = 40
MAX_ROUTES = 40

# Retrieval source ids → a coarse display tier when the evidence carries none.
_TIER_BY_SOURCE = {
    "jdds": "structured",
    "live": "structured",
    "yfinance": "structured",
    "sec": "primary",
    "web": "secondary",
}


class SourceCollector:
    """Accumulates provenance across every retrieval of one run.

    Deduplicated on `(url | sourceSpan | source:evidenceId)` so repeated tool calls
    (and the retrieval layer's own cache hits) do not list the same source twice.
    """

    def __init__(self) -> None:
        self._citations: list[Citation] = []
        self._seen: set[str] = set()
        # source id → best-known attempt status ("ok" | "unavailable")
        self._source_status: dict[str, str] = {}
        self._source_meta: dict[str, dict[str, Any]] = {}
        self._conflicts: list[dict[str, Any]] = []

    # ── Ingestion ───────────────────────────────────────────────────────────
    def add(self, result: FinancialRetrievalResult) -> None:
        """Record one retrieval result. Never raises — provenance is best-effort."""
        try:
            self._record_sources(result)
            self._record_citations(result)
            self._record_conflicts(result)
        except Exception:  # noqa: BLE001 - collection must never break a run
            return

    def _record_sources(self, result: FinancialRetrievalResult) -> None:
        status = "ok" if result.status in ("OK", "PARTIAL") else "unavailable"
        for ref in getattr(result, "sourceReferences", None) or []:
            name = getattr(ref, "source", None) or "unknown"
            # A source that succeeded anywhere is "ok"; only an all-failed source
            # is reported as unavailable.
            if status == "ok" or self._source_status.get(name) == "ok":
                self._source_status[name] = "ok"
            else:
                self._source_status.setdefault(name, "unavailable")
            self._source_meta.setdefault(
                name,
                {
                    "tier": getattr(ref, "sourceType", None)
                    or _TIER_BY_SOURCE.get(str(name).lower(), "unknown"),
                    "url": getattr(ref, "url", None),
                    "title": getattr(ref, "title", None),
                },
            )

    def _record_citations(self, result: FinancialRetrievalResult) -> None:
        evidence = list(getattr(result, "evidence", None) or [])
        if evidence:
            for citation in build_citations(evidence):
                self._add_citation(citation)
            return
        # A retrieval with no evidence items still has source-level provenance.
        for ref in getattr(result, "sourceReferences", None) or []:
            name = getattr(ref, "source", "unknown")
            self._add_citation(
                Citation(
                    evidenceId=f"src:{name}",
                    kind="source",
                    source=getattr(ref, "source", None),
                    sourceType=getattr(ref, "sourceType", None)
                    or _TIER_BY_SOURCE.get(str(name).lower()),
                    url=getattr(ref, "url", None),
                    title=getattr(ref, "title", None),
                    publishedAt=getattr(ref, "publishedAt", None),
                    retrievedAt=getattr(ref, "retrievedAt", None),
                    validationStatus=getattr(ref, "validationStatus", None),
                )
            )

    def _add_citation(self, citation: Citation) -> None:
        if len(self._citations) >= MAX_CITATIONS:
            return
        key = citation.url or citation.sourceSpan or f"{citation.source}:{citation.evidenceId}"
        if key in self._seen:
            return
        self._seen.add(key)
        self._citations.append(citation)

    def add_fetched_source(
        self,
        *,
        url: str,
        title: Optional[str] = None,
        ok: bool = True,
        published_at: Optional[str] = None,
        retrieved_at: Optional[str] = None,
    ) -> None:
        """Record a directly-fetched URL (research.retrieve_source).

        The URL is a real, caller-supplied source; it is listed as `secondary`
        unless it also appears elsewhere with a stronger tier. A failed fetch is
        recorded as a failed route, never as a citation — it is not evidence.
        """
        try:
            name = str(url)
            if not ok:
                self._source_status[name] = "unavailable"
                self._source_meta.setdefault(name, {"tier": "unknown", "url": url, "title": title})
                return
            self._source_status[name] = "ok"
            self._source_meta.setdefault(
                name, {"tier": "secondary", "url": url, "title": title or url}
            )
            self._add_citation(
                Citation(
                    evidenceId=f"url:{url}",
                    kind="web",
                    source=name,
                    sourceType="secondary",
                    url=url,
                    title=title or url,
                    publishedAt=published_at,
                    retrievedAt=retrieved_at,
                )
            )
        except Exception:  # noqa: BLE001 - provenance is best-effort
            return

    def _record_conflicts(self, result: FinancialRetrievalResult) -> None:
        for conflict in getattr(result, "conflicts", None) or []:
            if not isinstance(conflict, dict):
                continue
            self._conflicts.append(
                {
                    "metric": conflict.get("metric"),
                    "period": conflict.get("period"),
                    "candidates": conflict.get("candidates") or [],
                }
            )

    # ── Output ──────────────────────────────────────────────────────────────
    def has_content(self) -> bool:
        return bool(self._citations or self._source_meta or self._conflicts)

    def to_research_blob(self) -> Optional[dict[str, Any]]:
        """Shape the collected provenance as the existing `research` run blob.

        Returns None when nothing was collected, so an ordinary run carries no
        empty Sources panel. Status is the honest `collected` (never `accepted`):
        this is provenance of what was consulted, not a gated verification.
        """
        if not self.has_content():
            return None
        failed = [
            f"{name} — unavailable (no evidence retrieved)"
            for name, status in self._source_status.items()
            if status == "unavailable"
        ]
        return {
            "status": "collected",
            "metadata": {
                "taskType": "ordinary_run",
                "status": "collected",
                "citations": [c.model_dump() for c in self._citations],
                "conflicts": self._conflicts,
            },
            # Source-level rows (consulted sources, with tier/url) for a future
            # dedicated display; the current panel renders citations + routes.
            "collectedSources": [
                {"name": name, **(self._source_meta.get(name) or {})}
                for name in self._source_meta
            ],
            "failedRoutes": failed[:MAX_ROUTES] or None,
            "collected": True,
        }


__all__ = ["SourceCollector", "MAX_CITATIONS"]
