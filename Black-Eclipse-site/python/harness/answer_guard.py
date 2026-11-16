"""Bounded answer recovery: do not end on the first blocked route.

The graph accepts a model reply with no tool calls as the final answer. That is
correct for a real answer and wrong for a bare refusal: "I could not retrieve
X" is a ROUTING fact, not a verdict, and the runtime usually still has steps and
an untried route.

This module is PURE: it classifies the reply, decides whether recovery is
permitted, and writes the deterministic directive the model sees next. It never
calls a tool, a model or the clock, and it never widens the allowlist. The graph
owns the loop and the bound (`MAX_ANSWER_RECOVERIES`).

Honesty rules:

* Only a BARE refusal is recovered. A substantive answer that also names one
  missing figure is a finished answer, not a give-up.
* A request that explicitly restricts sources is never recovered around that
  restriction.
* A route the run already tried is never suggested again.
* After the bound is spent, the refusal stands: `UNAVAILABLE` remains a valid
  final answer once the permitted routes are exhausted.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

#: How many extra model turns one run may spend recovering from a refusal.
MAX_ANSWER_RECOVERIES = 2

#: Replies longer than this are treated as substantive even when they mention a
#: gap: a reader can use a partial answer, and another fetch may not change it.
SUBSTANTIVE_CHARS = 1_200

#: Route-specific give-up language. Deliberately excludes generic policy
#: refusals ("I can't give investment advice"), which are not routing failures.
_REFUSAL_MARKERS = (
    "unavailable",
    "no data",
    "not available",
    "no current price",
    "no source",
    "couldn't find",
    "could not find",
    "couldn't retrieve",
    "could not retrieve",
    "couldn't fetch",
    "could not fetch",
    "unable to retrieve",
    "unable to fetch",
    "unable to access",
    "failed to retrieve",
    "failed to fetch",
    "did not return",
    "didn't return",
    "i don't have access to",
    "i do not have access to",
)

#: A user's explicit source restriction. Recovery must respect it.
_RESTRICTION_PATTERNS = (
    re.compile(r"\bonly (?:use|using|from)\b", re.I),
    re.compile(r"\bdo not (?:use|browse|search)\b", re.I),
    re.compile(r"\bdon't (?:use|browse|search)\b", re.I),
    re.compile(r"\bno (?:web|internet|browsing|external) (?:search|access|sources?)\b", re.I),
    re.compile(r"\bwithout (?:web|internet|browsing|external sources?)\b", re.I),
    re.compile(r"\bfrom (?:the|this) (?:attachment|document|file) only\b", re.I),
)

#: Ordered fallback ladder. Each entry is (tool name, one-line instruction).
#: Only names present in the run's allowlist are ever suggested.
_ROUTE_LADDER: tuple[tuple[str, str], ...] = (
    ("tool_search", "Find another bound tool for the same objective (search by need, not by name)."),
    ("web_search", "Search for a page that carries the fact; a snippet is a pointer, not evidence."),
    ("web_extract", "Fetch the page (or the official filing) and turn it into cited evidence."),
    ("page_extract", "Extract the page's text as provenance-carrying evidence."),
    ("pdf_extract", "Extract a PDF/filing (a scanned PDF needs OCR; say so if OCR is unavailable)."),
    ("structured_extract", "Pull one named field from a page with its source span."),
    ("web_scrape", "Collect repeated records from one page with a selector."),
    ("scraper_run", "Write a bounded scraper for the site that has the data; the operator approves the domain once."),
    ("browser_launch", "Drive a rendered/login-gated page the retrieval providers cannot reach."),
    ("get_research_health", "Diagnose which research route is failing before concluding the data is absent."),
    ("get_source_health", "Read which data routes are recorded as failing or stale."),
    ("financial_providers", "List configured providers and their capabilities/credentials."),
    ("get_capability_matrix", "Check whether a capability is recognised/configured for this market."),
    ("analysis_run", "Compute the answer from data already held (a derivation is a real deliverable)."),
    ("finance_calc", "Compute the requested metric from inputs already held."),
    ("finance_metrics", "Compute a ratio/valuation metric from held inputs."),
    ("finance_series", "Compute a risk/return statistic from a held series."),
    ("delegate", "Split independent sub-questions and work them in parallel."),
    ("capability_request", "Name the missing capability so the operator can add it; a one-off can still be computed."),
)


def sources_restricted(query: str) -> bool:
    """Whether the user explicitly narrowed which sources may be used."""
    text = str(query or "")
    return any(pattern.search(text) for pattern in _RESTRICTION_PATTERNS)


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _has_substantive_sentence(answer: str) -> bool:
    """Whether at least one sentence carries content, not just a gap statement.

    A partial answer ("AAPL traded at 211.20; fundamentals were unavailable") is
    finished work. A bare refusal ("No data was returned.") has no value-bearing
    sentence, so recovery may still help.
    """
    for sentence in _SENTENCE_SPLIT.split(answer):
        text = sentence.strip()
        if not text:
            continue
        lowered = text.lower()
        if any(marker in lowered for marker in _REFUSAL_MARKERS):
            continue
        if re.search(r"\d", text):
            return True
        if any(token in lowered for token in ("http://", "https://", "source:", "as of", "retrieved")):
            return True
    return False


def is_bare_refusal(text: str) -> bool:
    """A short, route-specific give-up — not a substantive partial answer."""
    answer = str(text or "").strip()
    if not answer:
        return False
    lowered = answer.lower()
    marker = any(marker in lowered for marker in _REFUSAL_MARKERS)
    if not marker:
        return False
    # A refusal that also carries a value is finished work, not a give-up. A
    # figure (even beside "the primary was unavailable; the backup returned
    # 123.45") is the deliverable the user asked for.
    if len(answer) > 80 and re.search(r"\d", answer):
        return False
    # A long answer that opens by declaring the WHOLE result unavailable is
    # still a give-up; one that carries a sourced value is finished work.
    if len(answer) <= SUBSTANTIVE_CHARS and not _has_substantive_sentence(answer):
        return True
    head = lowered[:160]
    if any(head.startswith(prefix) for prefix in ("unavailable", "# unavailable")):
        return True
    return False


def _untried_routes(
    available: Optional[Iterable[str]], tried: Iterable[str],
) -> list[tuple[str, str]]:
    allowed = set(available) if available is not None else None
    used = {str(name) for name in tried}
    routes: list[tuple[str, str]] = []
    for name, instruction in _ROUTE_LADDER:
        if name in used:
            continue
        if allowed is not None and name not in allowed:
            continue
        routes.append((name, instruction))
    return routes


def recovery_reason(
    *,
    query: str,
    answer: str,
    tools_used: Iterable[str],
    available: Optional[Iterable[str]],
    recoveries: int,
    step: int,
    max_steps: int,
) -> Optional[str]:
    """Why recovery is permitted, or None. Pure and conservative."""
    if recoveries >= MAX_ANSWER_RECOVERIES:
        return None
    if step >= max_steps:
        return None
    if sources_restricted(query):
        return None
    if not is_bare_refusal(answer):
        return None
    # Recovery is for a BLOCKED ROUTE, not a capability/policy refusal with no
    # attempt behind it (the gap/offer path owns that shape). At least one tool
    # must have run and an untried permitted route must remain.
    used = {str(name) for name in tools_used}
    if not used:
        return None
    if not _untried_routes(available, used):
        return None
    return "blocked_answer"


def build_recovery_instruction(
    *,
    query: str,
    answer: str,
    tools_used: Iterable[str],
    available: Optional[Iterable[str]],
    unavailable_tools: Iterable[str] = (),
    attempt: int = 1,
) -> Optional[str]:
    """The deterministic directive for the next model turn, or None.

    It names only permitted, untried routes. The model still chooses; nothing is
    executed for it, and a refusal after the routes are exhausted is accepted.
    """
    if sources_restricted(query):
        return None
    routes = _untried_routes(available, tools_used)
    if not routes:
        return None
    used = sorted({str(name) for name in tools_used})
    failed = sorted({str(name) for name in unavailable_tools})
    lines = [
        "## Do not end on a blocked route",
        "Your previous reply stopped at a blocker. That is a routing fact, not a "
        "final answer: this run still has steps and the routes below have NOT "
        "been tried.",
    ]
    if used:
        lines.append("Already tried: " + ", ".join(used[:12]) + ".")
    if failed:
        lines.append(
            "Returned UNAVAILABLE or failed: " + ", ".join(failed[:12])
            + " — do not call these again with the same arguments."
        )
    lines.append("Next permitted routes (choose the one that fits):")
    for index, (name, instruction) in enumerate(routes[:6], start=1):
        lines.append(f"{index}. `{name}` — {instruction}")
    lines.append(
        "Now do ONE of: (a) call the next untried route above; (b) deliver the "
        "best partial answer from evidence already held and name the exact gap; "
        "(c) compute the answer from held data. Do not repeat the previous "
        "answer, and do not repeat a failed call. If every permitted route is "
        "genuinely exhausted, say UNAVAILABLE and name the exact missing input."
    )
    if attempt > 1:
        lines.append(
            "This is the final recovery attempt; if no route can produce the "
            "fact, deliver what you have with its provenance and the precise gap."
        )
    return "\n".join(lines)


def render_fallback_block(available: Optional[Iterable[str]], query: str) -> str:
    """A short per-run ladder rendered near the user turn, not in the head.

    The long system prompt already says "find another route"; this block says
    WHICH routes are bound RIGHT NOW, so the model does not have to rediscover
    its surface or invent a tool name. A source restriction is stated explicitly
    so the model does not recover around the user's own rule.
    """
    if sources_restricted(query):
        return (
            "# Source restriction\n"
            "The user restricted which sources may be used. If those sources do "
            "not answer, say precisely what is missing; do NOT route around the "
            "restriction with web, scraper or browser tools."
        )
    routes = _untried_routes(available, [])[:8]
    if not routes:
        return ""
    lines = [
        "# Fallback ladder (this run)",
        "A blocked route is a routing fact, not a verdict. Before saying "
        "UNAVAILABLE, work this ladder in order and stop once the fact is "
        "obtained or the marginal route cannot change the answer:",
    ]
    for index, (name, instruction) in enumerate(routes, start=1):
        lines.append(f"{index}. `{name}` — {instruction}")
    lines.append(
        "Keep what is verified, label page-sourced values WEB/SCRAPER/PARTIAL, "
        "and name the exact gap only after the ladder is exhausted."
    )
    return "\n".join(lines)


def recovery_event(
    *,
    attempt: int,
    answer: str,
    tools_used: Iterable[str],
    available: Optional[Iterable[str]],
) -> dict[str, Any]:
    """A bounded, redacted event payload (no model prose beyond a marker)."""
    routes = _untried_routes(available, tools_used)
    return {
        "attempt": int(attempt),
        "reason": "blocked_answer",
        "answerChars": len(str(answer or "")),
        "nextRoutes": [name for name, _ in routes[:8]],
    }


__all__ = [
    "MAX_ANSWER_RECOVERIES",
    "SUBSTANTIVE_CHARS",
    "build_recovery_instruction",
    "is_bare_refusal",
    "recovery_event",
    "recovery_reason",
    "render_fallback_block",
    "sources_restricted",
]
