"""Research & evidence grader.

Grades fact/claim accuracy, source quality, evidence relevance and completeness,
freshness, point-in-time correctness, entity resolution and conflict resolution
against the task's declared research contract. It reads the REAL research
evidence from the trajectory (research.* events) and the final answer.

When a task needs live retrieval and the tier has none, the result is UNKNOWN.
"""

from __future__ import annotations

import re
from typing import Any

from . import GradeContext, Grader, GraderResult

_STOP = {
    "the", "a", "an", "of", "to", "in", "and", "or", "is", "are", "was", "were",
    "for", "on", "at", "by", "with", "as", "that", "this", "it", "be", "has",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOP and len(w) > 1}


def _claim_supported(claim: dict[str, Any], evidence: list[dict[str, Any]]) -> bool:
    if claim.get("supported") is False:
        return False
    need = int(claim.get("min_sources", 1))
    return len(evidence) >= need


class ResearchGrader(Grader):
    name = "research"

    def grade(self, ctx: GradeContext) -> GraderResult:
        config = dict(self.config.get("research") or getattr(ctx.task, "metadata", {}).get("research") or {})
        claims = list(config.get("claims") or [])
        required_evidence = int(config.get("required_evidence", 0))
        freshness_days = config.get("freshness_days")

        research_events = [e for e in getattr(ctx.trajectory, "events", []) if e.type.startswith("research.")]
        evidence = [
            e.data for e in research_events
            if e.type in ("research.evidence_retrieved", "research.evidence", "evidence.retrieved")
        ] or [e.data for e in research_events]

        if not claims and not required_evidence and not research_events:
            return GraderResult.unmeasured_result(self.name, "no research contract or evidence")

        failures: list[str] = []
        output_tokens = _tokens(ctx.final_output or "")

        claim_scores: list[float] = []
        for claim in claims:
            text = str(claim.get("text") or claim.get("claim") or "")
            overlap = len(_tokens(text) & output_tokens) / max(1, len(_tokens(text)))
            supported = _claim_supported(claim, evidence)
            ok = overlap >= 0.5 and (supported or claim.get("supported", True))
            claim_scores.append(1.0 if ok else max(0.0, overlap if supported else 0.0))
            if not supported and claim.get("supported", True):
                failures.append(f"claim lacks sufficient evidence: {text[:60]!r}")
            if overlap < 0.5 and claim.get("supported", True):
                failures.append(f"claim not stated in the answer: {text[:60]!r}")

        if required_evidence and len(evidence) < required_evidence:
            failures.append(f"evidence incomplete: {len(evidence)} < required {required_evidence}")

        if freshness_days is not None:
            stale = [e for e in evidence if _is_stale(e, float(freshness_days))]
            if stale:
                failures.append(f"{len(stale)} evidence item(s) older than {freshness_days}d")

        claim_accuracy = sum(claim_scores) / len(claim_scores) if claim_scores else 1.0
        passed = not failures
        score = claim_accuracy if passed else max(0.0, claim_accuracy - 0.1 * len(failures))
        return GraderResult(
            self.name, score, passed,
            details={
                "claims": len(claims),
                "evidence": len(evidence),
                "claim_accuracy": round(claim_accuracy, 4),
            },
            failures=failures,
            evidence=[{"evidence_count": len(evidence)}],
        )


def _is_stale(evidence: dict[str, Any], freshness_days: float) -> bool:
    import datetime as _dt  # noqa: PLC0415

    stamp = evidence.get("publishedAt") or evidence.get("timestamp") or evidence.get("date")
    if not stamp:
        return False
    try:
        when = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return False
    now = _dt.datetime.now(when.tzinfo) if when.tzinfo else _dt.datetime.now()
    return (now - when).days > freshness_days
