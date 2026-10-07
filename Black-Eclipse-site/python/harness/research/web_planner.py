"""Deterministic research planner for the web research engine.

Decomposes a question into sub-questions and targeted search queries. The
planner is deterministic and budget-aware: it produces a small, high-value query
set rather than a blind fan-out. Coverage, source quality, query efficiency,
cost and latency are explicit goals.

A model MAY be layered on top by a caller, but the default planner is pure and
reproducible, so query planning is testable and explainable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .web_contracts import (
    ResearchDepth,
    ResearchIntent,
    ResearchPlan,
    SourceType,
    SubQuestion,
    WebResearchMandate,
)

# Per-intent question templates. Each is a list of (label, template) where the
# template may reference `{q}` (the raw question), `{entity}` (a resolved name)
# and `{year}` (a detected year). Templates are intentionally short and focused.
_TEMPLATES: dict[ResearchIntent, list[tuple[str, str]]] = {
    ResearchIntent.FINANCIAL_RESEARCH: [
        ("valuation", "{entity} valuation current"),
        ("financials", "{entity} revenue earnings latest fiscal"),
        ("filings", "{entity} SEC filing 10-K annual report"),
        ("guidance", "{entity} management guidance outlook"),
        ("risks", "{entity} risks bear case"),
    ],
    ResearchIntent.COMPANY_RESEARCH: [
        ("profile", "{entity} company profile business model"),
        ("financials", "{entity} revenue growth financials"),
        ("leadership", "{entity} leadership executives"),
        ("news", "{entity} latest news"),
    ],
    ResearchIntent.MARKET_RESEARCH: [
        ("size", "{entity} market size growth"),
        ("forecast", "{entity} market forecast CAGR"),
        ("players", "{entity} key players market share"),
    ],
    ResearchIntent.COMPETITOR_RESEARCH: [
        ("landscape", "{entity} competitive landscape"),
        ("competitors", "{entity} main competitors"),
        ("share", "{entity} market share competitors"),
        ("counter", "{entity} competitive threats challenges"),
    ],
    ResearchIntent.NEWS: [
        ("recent", "{entity} news latest"),
        ("coverage", "{entity} latest developments"),
    ],
    ResearchIntent.CURRENT_EVENT: [
        ("current", "{q}"),
        ("context", "{entity} background latest"),
    ],
    ResearchIntent.ACADEMIC_RESEARCH: [
        ("papers", "{q} research paper"),
        ("review", "{q} systematic review evidence"),
    ],
    ResearchIntent.TECHNICAL_RESEARCH: [
        ("overview", "{q}"),
        ("implementation", "{q} documentation"),
        ("comparison", "{q} comparison alternatives"),
    ],
    ResearchIntent.LEGAL_RESEARCH: [
        ("primary", "{entity} court filing lawsuit"),
        ("regulatory", "{entity} regulatory investigation"),
    ],
    ResearchIntent.DOCUMENT_RESEARCH: [
        ("document", "{entity} annual report filing"),
        ("primary", "{entity} official document {year}"),
    ],
    ResearchIntent.VERIFICATION: [
        ("claim", "{q}"),
        ("counter", "{q} fact check true false"),
    ],
    ResearchIntent.COMPARISON: [
        ("a", "{q}"),
        ("b", "{q} comparison"),
        ("c", "{q} differences pros cons"),
    ],
    ResearchIntent.DISCOVERY: [("discover", "{q}")],
    ResearchIntent.OSINT: [("entity", "{q}"), ("records", "{entity} records public")],
    ResearchIntent.DEEP_RESEARCH: [
        ("overview", "{q}"),
        ("details", "{q} detailed analysis"),
        ("evidence", "{q} primary sources"),
        ("counter", "{q} counterarguments criticism"),
    ],
    ResearchIntent.FACT_LOOKUP: [("fact", "{q}")],
}

# Intent → whether a browser escalation is worth planning for.
_BROWSER_INTENTS = {
    ResearchIntent.DOCUMENT_RESEARCH,
    ResearchIntent.LEGAL_RESEARCH,
    ResearchIntent.OSINT,
}

_STOP_ENTITIES = {
    "Analyze", "What", "Who", "When", "Where", "How", "Is", "Are", "The", "A",
    "An", "Determine", "Research", "Find", "Compare", "Give", "Tell", "Explain",
    "Please", "Using", "Based",
}


@dataclass
class PlanInput:
    researchId: str
    question: str
    intent: ResearchIntent
    depth: ResearchDepth
    entityHints: list[str] | None = None
    year: str | None = None


def extract_entity(question: str, hints: list[str] | None = None) -> str:
    """A best-effort entity surface form for query templates.

    Prefers caller hints (e.g. a resolved ticker/company). Otherwise takes the
    most salient capitalized run, falling back to the first few meaningful words.
    This is a query hint only — canonical identity is resolved later.
    """
    if hints:
        return hints[0]
    caps = re.findall(r"\b([A-Z][A-Za-z0-9&.\-]{2,})\b", question or "")
    for candidate in caps:
        if candidate not in _STOP_ENTITIES:
            return candidate
    words = [w for w in re.findall(r"[A-Za-z0-9]{3,}", question or "") if w not in _STOP_ENTITIES]
    return " ".join(words[:3]) if words else (question or "").strip()


def extract_year(question: str) -> str | None:
    import datetime

    match = re.search(r"\b((?:19|20)\d{2})\b", question or "")
    if match:
        return match.group(1)
    return str(datetime.date.today().year)


def _max_queries(depth: ResearchDepth) -> int:
    return {
        ResearchDepth.QUICK: 2,
        ResearchDepth.STANDARD: 4,
        ResearchDepth.DEEP: 8,
        ResearchDepth.FINANCIAL: 6,
        ResearchDepth.FORENSIC: 10,
    }[depth]


def plan_research(plan_input: PlanInput) -> ResearchPlan:
    """Produce a deterministic research plan for the given input.

    The plan is bounded by depth: fewer, higher-value queries at QUICK, a broad
    but still bounded set at DEEP/FORENSIC. It never emits more than
    `_max_queries(depth)` queries.
    """
    question = (plan_input.question or "").strip()
    entity = extract_entity(question, plan_input.entityHints)
    year = plan_input.year or extract_year(question)
    limit = _max_queries(plan_input.depth)

    templates = _TEMPLATES.get(plan_input.intent, _TEMPLATES[ResearchIntent.FACT_LOOKUP])
    sub_questions: list[SubQuestion] = []
    queries: list[str] = []

    for idx, (label, template) in enumerate(templates):
        query = template.format(q=question, entity=entity, year=year).strip()
        query = re.sub(r"\s+", " ", query)
        sub_questions.append(
            SubQuestion(
                id=f"sq_{idx}",
                question=query,
                intent=plan_input.intent,
                required=idx < 3,
            )
        )
        if query and query not in queries:
            queries.append(query)
        if len(queries) >= limit:
            break

    # Always include the raw question as a discovery query when there is room, so
    # a template that misses the exact phrasing still has a chance.
    if question and question not in queries and len(queries) < limit:
        queries.insert(0, question)
        sub_questions.insert(
            0,
            SubQuestion(id="sq_raw", question=question, intent=plan_input.intent, required=True),
        )

    browser_planned = plan_input.intent in _BROWSER_INTENTS or plan_input.depth == ResearchDepth.FORENSIC
    notes = [
        f"depth={plan_input.depth.value}",
        f"queryBudget={limit}",
        f"browserEscalationPlanned={browser_planned}",
        f"entityHint={entity}",
    ]

    return ResearchPlan(
        researchId=plan_input.researchId,
        strategy=plan_input.depth.value,
        queries=queries,
        subQuestions=sub_questions,
        sourcesPlanned=[t.value for t in SourceType],
        estimatedQueries=len(queries),
        notes=notes,
    )


__all__ = ["PlanInput", "plan_research", "extract_entity", "extract_year"]
