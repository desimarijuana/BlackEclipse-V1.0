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
        # Universal-financial-fact analysis accumulated over the run's retrievals.
        self._finance: Optional["_FinanceAccumulator"] = None

    # ── Ingestion ───────────────────────────────────────────────────────────
    def add(self, result: FinancialRetrievalResult, analysis: Any = None) -> None:
        """Record one retrieval result. Never raises — provenance is best-effort.

        `analysis` is the `finance_facts.analysis.ResultAnalysis` already computed
        by the retrieval tool (computed once, passed here — never recomputed). When
        absent, a run simply carries no finance analysis.
        """
        try:
            self._record_sources(result)
            self._record_citations(result)
            self._record_conflicts(result)
            self._record_finance(analysis)
        except Exception:  # noqa: BLE001 - collection must never break a run
            return

    def _record_finance(self, analysis: Any) -> None:
        if analysis is None:
            return
        if self._finance is None:
            self._finance = _FinanceAccumulator()
        self._finance.add(analysis)

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
        blob: dict[str, Any] = {
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
        if self._finance is not None:
            blob["financeAnalysis"] = self._finance.to_dict()
        return blob

    # ── Finance analysis access ───────────────────────────────────────────────
    def finance_analysis(self) -> Optional[dict[str, Any]]:
        """The accumulated universal-fact analysis, or None when no retrieval ran."""
        return self._finance.to_dict() if self._finance is not None else None


class _FinanceAccumulator:
    """Merges the per-retrieval `ResultAnalysis` of one run.

    Fact verdicts are deduplicated by (entity, metric, definition, period) so a
    value fetched twice appears once. Exclusions accumulate; notes are merged
    without repetition. It exposes the union of everything the answer must honor.
    """

    def __init__(self) -> None:
        self._facts: dict[str, dict[str, Any]] = {}
        self._excluded: set[str] = set()
        self._notes: list[str] = []
        self._seen_notes: set[str] = set()
        self._conflicts: list[dict[str, Any]] = []
        self._conflict_keys: set[str] = set()
        self._sector: Optional[str] = None
        self._financial_framework = False

    def add(self, analysis: Any) -> None:
        for fact in getattr(analysis, "facts", []) or []:
            data = fact.to_dict() if hasattr(fact, "to_dict") else dict(fact)
            key = "|".join(str(data.get(k)) for k in ("metric", "definition", "period"))
            # Keep the higher-confidence verdict when the same fact repeats.
            existing = self._facts.get(key)
            if existing is None or _conf_rank(data.get("confidence")) > _conf_rank(existing.get("confidence")):
                self._facts[key] = data
        for name in getattr(analysis, "excluded", []) or []:
            self._excluded.add(name)
        for note in getattr(analysis, "notes", []) or []:
            if note not in self._seen_notes:
                self._seen_notes.add(note)
                self._notes.append(note)
        for conflict in getattr(analysis, "conflicts", []) or []:
            key = "|".join(str(conflict.get(k)) for k in ("metric", "sourceA", "sourceB", "period"))
            if key not in self._conflict_keys:
                self._conflict_keys.add(key)
                self._conflicts.append(conflict)
        if getattr(analysis, "sector", None):
            self._sector = analysis.sector
        if getattr(analysis, "financial_framework", False):
            self._financial_framework = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "presentable": not self._excluded,
            "sector": self._sector,
            "financialFramework": self._financial_framework,
            "excluded": sorted(self._excluded),
            "conflicts": self._conflicts,
            "notes": self._notes,
            "facts": list(self._facts.values()),
        }


_CONF_RANK = {"unverified": 0, "low": 1, "medium": 2, "high": 3}


def _conf_rank(level: Any) -> int:
    return _CONF_RANK.get(str(level), 0)


__all__ = ["SourceCollector", "MAX_CITATIONS"]
