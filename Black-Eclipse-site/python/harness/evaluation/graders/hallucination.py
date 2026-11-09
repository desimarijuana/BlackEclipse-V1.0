"""Hallucination grader.

Measures unsupported factual claims, fabricated sources, fabricated tool results,
incorrect entities and temporal hallucinations, and reports
``hallucination_rate``, ``unsupported_claim_rate`` and ``fabricated_source_rate``.

The checks are deterministic and driven by the task's declared contract plus the
real trajectory: a source the runtime never retrieved is fabricated, a number
asserted with no retrieval tool call is unsupported, and a date in the future is a
temporal hallucination.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from . import GradeContext, Grader, GraderResult
from .citation import extract_citations

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_NUMBER_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?%?\b")
_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# Tools whose successful call is a valid source of a retrieved numeric fact.
_RETRIEVAL_HINTS = ("market", "research", "retrieve", "fetch", "web", "price", "fundamental", "evidence", "finance", "document", "search")


class HallucinationGrader(Grader):
    name = "hallucination"

    def grade(self, ctx: GradeContext) -> GraderResult:
        config = dict(self.config.get("hallucination") or getattr(ctx.task, "metadata", {}).get("hallucination") or {})
        known_sources = [s.lower() for s in (config.get("known_sources") or [])]
        allowed_domains = [d.lower() for d in (config.get("allowed_domains") or [])]
        entities = [e.lower() for e in (config.get("entities") or [])]
        requires_tool_evidence = bool(config.get("requires_tool_evidence", False))
        current_date = config.get("current_date")
        max_halluc = float(config.get("max_hallucination_rate", 0.0))
        max_fabricated_sources = float(config.get("max_fabricated_source_rate", 0.0))
        max_unsupported = float(config.get("max_unsupported_claim_rate", 0.0))

        output = ctx.final_output or ""
        if not config and not output:
            return GraderResult.unmeasured_result(self.name, "no hallucination contract and no output")

        citations = extract_citations(output)
        trajectory_sources: set[str] = set()
        # The release gate WITHHOLDS an unretrieved citation from the released
        # answer (so a citation parser cannot re-count it). Its verdict still
        # names the source, and that verdict is the honest evidence that the
        # model fabricated it. Grading the redacted text alone would let a
        # fabricated source pass simply because the delivery seam hid it.
        withheld_sources: set[str] = set()
        retrieval_calls = 0
        for event in getattr(ctx.trajectory, "events", []):
            if event.type in ("research.evidence_retrieved", "citation.created", "research.citation_created"):
                url = (event.data or {}).get("url") or (event.data or {}).get("source")
                if url:
                    trajectory_sources.add(str(url).lower())
            elif event.type in ("evidence.release_gate", "research.evidence.release_gate"):
                for url in (event.data or {}).get("unverified") or []:
                    if not url:
                        continue
                    candidate = str(url)
                    host = urlparse(candidate).netloc.lower()
                    # The runtime gate knows only what the run retrieved; the
                    # TASK's contract may explicitly allow a source the scripted
                    # answer never fetched. Such a source is not a fabrication.
                    if (
                        candidate.lower() in known_sources
                        or any(known in candidate.lower() for known in known_sources)
                        or any(host.endswith(domain) for domain in allowed_domains)
                    ):
                        continue
                    withheld_sources.add(candidate.lower())
        for call in ctx.tool_calls:
            if call.get("status") == "completed" and any(h in str(call.get("name")) for h in _RETRIEVAL_HINTS):
                retrieval_calls += 1

        # Fabricated sources: a cited URL never retrieved and not known/allowed,
        # PLUS a source the release gate withheld that is ALSO outside the
        # task's declared source contract. Without a contract the grader cannot
        # call a withheld pointer a hallucination — the release-gate redaction is
        # the control there, and scripted answers often cite a source the
        # trajectory does not re-retrieve.
        citation_urls = {url.lower() for url in citations}
        declares_sources = bool(known_sources or allowed_domains)
        extra_withheld: set[str] = set()
        if declares_sources:
            for raw in withheld_sources - citation_urls:
                host = urlparse(raw).netloc.lower()
                known = (
                    raw in trajectory_sources
                    or any(s in raw for s in known_sources)
                    or any(host.endswith(d) for d in allowed_domains)
                )
                if not known:
                    extra_withheld.add(raw)
        fabricated_sources: list[str] = sorted(extra_withheld)
        for url in citations:
            host = urlparse(url).netloc.lower()
            known = (
                url.lower() in trajectory_sources
                or any(s in url.lower() for s in known_sources)
                or any(host.endswith(d) for d in allowed_domains)
            )
            if known_sources or allowed_domains or trajectory_sources:
                if not known:
                    fabricated_sources.append(url)

        # Unsupported claims: sentences with numbers when the tier requires tool evidence.
        sentences = [s for s in _SENTENCE_RE.split(output) if _NUMBER_RE.search(s)]
        unsupported: list[str] = []
        if requires_tool_evidence:
            for sentence in sentences:
                if retrieval_calls == 0 and not trajectory_sources:
                    unsupported.append(sentence.strip()[:120])

        # Incorrect entities: an asserted entity that is not in the declared set.
        wrong_entities: list[str] = []
        if entities:
            # If the output mentions a capitalised ticker-like token not declared.
            for token in set(re.findall(r"\b[A-Z]{2,5}\b", output)):
                if token.lower() not in entities and token not in ("SEC", "EPS", "P/E", "GDP", "IPO", "ETF", "AI"):
                    # Only flag when the task declares entities and the token is absent.
                    wrong_entities.append(token)
                    break

        # Temporal hallucinations: a date after "now".
        temporal: list[str] = []
        if current_date:
            for y, m, d in _DATE_RE.findall(output):
                if f"{y}-{m}-{d}" > str(current_date):
                    temporal.append(f"{y}-{m}-{d}")

        total_claims = max(1, len(sentences))
        total_sources = max(1, len(citations) + len(extra_withheld))
        fabricated_source_rate = len(fabricated_sources) / total_sources
        unsupported_claim_rate = len(unsupported) / total_claims
        hallucination_rate = (
            len(fabricated_sources) + len(unsupported) + len(wrong_entities) + len(temporal)
        ) / (total_claims + total_sources)

        failures: list[str] = []
        if hallucination_rate > max_halluc:
            failures.append(f"hallucination_rate {hallucination_rate:.3f} > {max_halluc}")
        if fabricated_source_rate > max_fabricated_sources:
            failures.append(f"fabricated_source_rate {fabricated_source_rate:.3f} > {max_fabricated_sources}")
        if unsupported_claim_rate > max_unsupported:
            failures.append(f"unsupported_claim_rate {unsupported_claim_rate:.3f} > {max_unsupported}")

        passed = not failures
        return GraderResult(
            self.name, 1.0 - min(1.0, hallucination_rate), passed,
            details={
                "hallucination_rate": round(hallucination_rate, 4),
                "unsupported_claim_rate": round(unsupported_claim_rate, 4),
                "fabricated_source_rate": round(fabricated_source_rate, 4),
                "fabricated_sources": fabricated_sources,
                "unsupported_claims": unsupported,
                "wrong_entities": wrong_entities,
                "temporal": temporal,
            },
            failures=failures,
            evidence=[{"fabricated_sources": fabricated_sources}],
        )
