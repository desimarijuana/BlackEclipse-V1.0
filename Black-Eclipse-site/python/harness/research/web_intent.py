"""Deterministic research-intent classification (web research engine).

Classifies a user question into a `ResearchIntent` and derives the routing
requirements (freshness, authority, source types, depth, browser need, financial
need, point-in-time need, cross-validation need).

The classifier is deterministic and explainable: it is a function of the
question text, never a model. A model MAY refine a result (caller-supplied), but
the default path never depends on one, so intent classification is reproducible
and testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .web_contracts import ResearchDepth, ResearchIntent, SourceType

# Keyword families → intent. Order matters: the most specific intent wins.
_INTENT_RULES: list[tuple[ResearchIntent, tuple[str, ...]]] = [
    (ResearchIntent.OSINT, ("osint", "open source intelligence", "threat actor", "attribution")),
    (ResearchIntent.VERIFICATION, ("verify", "fact check", "fact-check", "is it true", "debunk", "confirm whether")),
    (ResearchIntent.COMPARISON, ("compare", "versus", " vs ", "better than", "difference between", "which is")),
    (ResearchIntent.LEGAL_RESEARCH, ("lawsuit", "litigation", "court", "legal", "regulat", "antitrust", "compliance", "sec investigation")),
    (ResearchIntent.COMPETITOR_RESEARCH, ("competitor", "competitive landscape", "market share", "rival", "competition", "dominance", "dominant", "sustainable", "sustainability", "moat", "durable advantage", "ai accelerator")),
    (ResearchIntent.ACADEMIC_RESEARCH, ("paper", "study", "research paper", "journal", "peer-reviewed", "literature", "arxiv", "doi", "academic")),
    (ResearchIntent.FINANCIAL_RESEARCH, ("valuation", "overvalued", "undervalued", "earnings", "revenue", "ebitda", "p/e", "price target", "dividend", "balance sheet", "cash flow", "financial", "valuation", "fiscal")),
    (ResearchIntent.MARKET_RESEARCH, ("market size", "market growth", "tam", "cagr", "demand forecast", "industry outlook", "sector")),
    (ResearchIntent.COMPANY_RESEARCH, ("company", "business model", "founder", "ceo", "employees", "headquarters", "profile", "acquired", "acquisition")),
    (ResearchIntent.NEWS, ("news", "latest on", "what happened", "headlines", "announced today", "breaking")),
    (ResearchIntent.CURRENT_EVENT, ("current", "today", "right now", "this week", "as of", "recent", "just happened")),
    (ResearchIntent.DOCUMENT_RESEARCH, ("filing", "10-k", "10-q", "annual report", "prospectus", "pdf", "document", "transcript")),
    (ResearchIntent.TECHNICAL_RESEARCH, ("how does", "implementation", "architecture", "library", "api", "benchmark", "code", "algorithm", "spec")),
    (ResearchIntent.DISCOVERY, ("find", "discover", "list of", "who are", "examples of", "alternatives to")),
    (ResearchIntent.FACT_LOOKUP, ("what is", "who is", "when did", "where is", "how many", "capital of", "define")),
]

_FRESHNESS_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("1d", ("today", "right now", "breaking", "just", "current", "latest", "live")),
    ("7d", ("this week", "recent", "past week", "news")),
    ("30d", ("this month", "past month")),
    ("1y", ("this year", "past year", "annual report", "fiscal year")),
]

_FINANCIAL_HINTS = (
    "valuation", "overvalued", "undervalued", "earnings", "revenue", "eps",
    "ebitda", "free cash flow", "margin", "p/e", "pe ratio", "dividend",
    "balance sheet", "income statement", "cash flow", "fiscal", "sec filing",
    "10-k", "10-q", "ticker", "stock", "shares", "market cap", "dcf", "wacc",
)
_DEEP_HINTS = ("deep", "comprehensive", "thorough", "in depth", "in-depth", "analyze", "full analysis", "everything about")
_FORENSIC_HINTS = ("forensic", "provenance", "point-in-time", "as of a specified", "source independence", "audit trail")
_QUICK_HINTS = ("quick", "brief", "one sentence", "just tell me", "tldr", "short answer")
_PRIMARY_HINTS = ("official", "primary source", "filing", "sec", "regulator", "government", "annual report", "transcript")
_CROSS_HINTS = ("cross-check", "cross check", "multiple sources", "do not rely on a single source", "verify", "corroborat")


@dataclass
class IntentResult:
    intent: ResearchIntent
    freshness: Optional[str]
    primaryRequired: bool
    crossValidationRequired: bool
    browserLikely: bool
    financial: bool
    pointInTimeRequired: bool
    depth: ResearchDepth
    sourceTypes: list[SourceType] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent.value,
            "freshness": self.freshness,
            "primaryRequired": self.primaryRequired,
            "crossValidationRequired": self.crossValidationRequired,
            "browserLikely": self.browserLikely,
            "financial": self.financial,
            "pointInTimeRequired": self.pointInTimeRequired,
            "depth": self.depth.value,
            "sourceTypes": [s.value for s in self.sourceTypes],
            "reasons": self.reasons,
        }


def _score(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for k in keywords if k in text)


def _detect_point_in_time(text: str, explicit: Optional[str]) -> bool:
    if explicit:
        return True
    import re

    if re.search(r"\bas of\b", text) and re.search(r"\b(19|20)\d{2}\b", text):
        return True
    return bool(re.search(r"\b(on|as of)\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+(19|20)\d{2}\b", text))


def classify_intent(
    question: str,
    *,
    explicit_intent: Optional[ResearchIntent] = None,
    point_in_time: Optional[str] = None,
) -> IntentResult:
    """Classify a question into an intent + routing requirements.

    An explicit intent (from the caller) is trusted and skips keyword voting;
    the derived requirements are still computed.
    """
    text = (question or "").strip().lower()
    reasons: list[str] = []

    intent = explicit_intent
    if intent is None:
        best_score = 0
        best = ResearchIntent.FACT_LOOKUP
        for candidate, keywords in _INTENT_RULES:
            score = _score(text, keywords)
            if score > best_score:
                best_score = score
                best = candidate
        if best_score == 0:
            reasons.append("no intent keyword matched; defaulted to fact_lookup")
        else:
            reasons.append(f"matched intent {best.value!r} ({best_score} keyword hits)")
        intent = best

    # Freshness.
    freshness: Optional[str] = None
    for window, keywords in _FRESHNESS_RULES:
        if any(k in text for k in keywords):
            freshness = window
            reasons.append(f"freshness {window} from keyword")
            break

    financial = intent in (
        ResearchIntent.FINANCIAL_RESEARCH,
        ResearchIntent.MARKET_RESEARCH,
        ResearchIntent.COMPANY_RESEARCH,
    ) and any(h in text for h in _FINANCIAL_HINTS)
    if not financial and any(h in text for h in _FINANCIAL_HINTS):
        financial = True
    if financial:
        reasons.append("financial vocabulary present")

    primary_required = any(h in text for h in _PRIMARY_HINTS) or financial
    cross_required = any(h in text for h in _CROSS_HINTS) or intent in (
        ResearchIntent.VERIFICATION,
        ResearchIntent.DEEP_RESEARCH,
    )

    # Depth.
    if any(h in text for h in _FORENSIC_HINTS):
        depth = ResearchDepth.FORENSIC
    elif financial and intent == ResearchIntent.FINANCIAL_RESEARCH:
        depth = ResearchDepth.FINANCIAL
    elif any(h in text for h in _DEEP_HINTS) or intent == ResearchIntent.DEEP_RESEARCH:
        depth = ResearchDepth.DEEP
    elif any(h in text for h in _QUICK_HINTS) or intent == ResearchIntent.FACT_LOOKUP:
        depth = ResearchDepth.QUICK
    else:
        depth = ResearchDepth.STANDARD

    # Browser is likely needed for JS-heavy or gated sources, or when the intent
    # is one that usually lives behind interaction (filings portals, IR sites).
    browser_likely = intent in (
        ResearchIntent.DOCUMENT_RESEARCH,
        ResearchIntent.LEGAL_RESEARCH,
        ResearchIntent.OSINT,
    ) or "portal" in text or "login" in text

    source_types = _source_types_for(intent, financial=financial, academic=intent == ResearchIntent.ACADEMIC_RESEARCH)

    return IntentResult(
        intent=intent,
        freshness=freshness,
        primaryRequired=primary_required,
        crossValidationRequired=cross_required,
        browserLikely=browser_likely,
        financial=financial,
        pointInTimeRequired=_detect_point_in_time(text, point_in_time),
        depth=depth,
        sourceTypes=source_types,
        reasons=reasons,
    )


def _source_types_for(intent: ResearchIntent, *, financial: bool, academic: bool) -> list[SourceType]:
    types: list[SourceType] = []
    if intent in (ResearchIntent.FINANCIAL_RESEARCH, ResearchIntent.DOCUMENT_RESEARCH) or financial:
        types += [SourceType.OFFICIAL_FILING, SourceType.INVESTOR_RELATIONS, SourceType.FINANCIAL_DATA]
    if intent == ResearchIntent.NEWS:
        types.append(SourceType.NEWS)
    if intent == ResearchIntent.ACADEMIC_RESEARCH or academic:
        types.append(SourceType.ACADEMIC)
    if intent == ResearchIntent.LEGAL_RESEARCH:
        types += [SourceType.REGULATOR, SourceType.GOVERNMENT]
    if intent == ResearchIntent.COMPETITOR_RESEARCH:
        types += [SourceType.NEWS, SourceType.INDUSTRY, SourceType.ANALYST]
    if not types:
        types = [SourceType.NEWS, SourceType.COMPANY, SourceType.INDUSTRY]
    # Deduplicate, preserve order.
    seen: set[SourceType] = set()
    out: list[SourceType] = []
    for t in types:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


__all__ = ["IntentResult", "classify_intent"]
