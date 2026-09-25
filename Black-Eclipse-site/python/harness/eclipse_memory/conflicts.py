"""Deterministic contradiction / replacement handling for durable memory.

A personal memory system must not let two mutually-exclusive facts coexist as
active truth. Before a second active record is created, the write path asks this
module what disposition the new statement has relative to an existing one.

The decision is deterministic and authority-aware:

  * **explicit replacement** ("I prefer X *now*", "instead", "changed my mind"):
    the old record is superseded (retained, linked) and the new one is active;
  * **explicit beats automatic**: an explicit statement that contradicts an
    automatic one wins even without replacement wording (supersede the learned
    record); an automatic statement that contradicts an explicit one becomes
    inert (`proposed`) — an automatic observation never overrides an explicit
    fact;
  * **ambiguous explicit contradiction** (two explicit statements, no replacement
    wording): the new one is stored inert (`proposed`) for review — no second
    active truth and no silent supersede;
  * **same statement** (same dimension, same polarity, high normalized overlap):
    a confirmation, not a conflict — the caller refreshes the existing record;
  * **unrelated scope / subject**: never a conflict.

Detection is lexical and explainable — subject identity, subject aliases,
controlled normalized tokens, known opposing-polarity pairs and explicit
replacement language. No model call, no embeddings. A missed conflict is
preferred over replacing unrelated memory, so broad word overlap is never enough
on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Explicit replacement / correction language. When present alongside a conflict,
# the user's intent to replace (not merely add) is unambiguous.
REPLACEMENT_PATTERNS = (
    r"\bnow\b",
    r"\bfrom now on\b",
    r"\binstead\b",
    r"\bchanged my mind\b",
    r"\bno longer\b",
    r"\bactually,?\b",
    r"\bupdate[sd]?\b",
    r"\bcorrect(?:ion|ed)?\b",
    r"\breplace[sd]?\b",
    r"\bswitch(?:ed|ing)? to\b",
    r"\bprefer .* (?:now|instead)\b",
)

# Opposite preference polarity pairs. A statement matching the left and another
# matching the right are contradictory ON THE SAME DIMENSION. Kept intentionally
# small and human-reviewed — a wrong pair is worse than a missed one. Note the
# `always`/`never` pair deliberately does NOT include bare `do`, which matched
# almost any sentence and produced false conflicts.
OPPOSING_PAIRS: tuple[tuple[str, str], ...] = (
    (r"\b(concise|brief|short|terse|succinct)\b", r"\b(detailed|verbose|in[- ]depth|elaborate|long)\b"),
    (r"\b(always|include|including|with)\b", r"\b(never|exclude|excluding|without|omit|hide|do not|don'?t|avoid)\b"),
    (r"\b(simple|plain|minimal)\b", r"\b(advanced|technical|comprehensive)\b"),
    (r"\b(buy|long)\b", r"\b(sell|short)\b"),
    (r"\b(before|prior)\b", r"\b(after|following)\b"),
    (r"\b(daily|every day)\b", r"\b(weekly|monthly|quarterly)\b"),
    (r"\b(conservative|low[- ]risk)\b", r"\b(aggressive|high[- ]risk)\b"),
)

# Decision outcomes (what the caller should do).
DECISION_SUPERSEDE = "supersede"
DECISION_PROPOSE = "propose"
DECISION_CONFIRM = "confirm"
DECISION_NONE = "none"

# Reasons (requirement 12): concrete, machine-readable + human-readable.
REASON_REPLACEMENT = "explicit replacement"
REASON_AUTHORITY_OVERRIDE = "explicit authority overrides automatic"
REASON_AUTOMATIC_NEEDS_REVIEW = "automatic conflict requires review"
REASON_AMBIGUOUS_EXPLICIT = "ambiguous explicit contradiction"
REASON_CONFIRMATION = "same statement confirmation"
REASON_UNRELATED_SCOPE = "unrelated scope"
REASON_UNRELATED_SUBJECT = "unrelated subject"
REASON_TEMPORARY = "temporary task-scoped instruction"

_STOPWORDS = frozenset(
    {"the", "a", "an", "of", "to", "and", "or", "for", "in", "on", "is", "are",
     "i", "my", "me", "we", "you", "it", "that", "this", "be", "with", "do",
     "does", "should", "would", "could", "prefer", "prefers", "preferred",
     "like", "likes", "want", "wants", "use", "using", "answers", "answer"}
)

# Same-dimension token overlap required to treat two texts as the same statement
# (a confirmation) when no subject is supplied.
_CONFIRM_OVERLAP = 0.6

# Minimum shared normalized tokens to link two subject-less memories at all.
_RELATED_OVERLAP = 2


@dataclass
class ConflictAssessment:
    decision: str = DECISION_NONE
    replacement: bool = False
    related: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""

    @property
    def conflict(self) -> bool:
        """True when the new statement is a contradiction of an existing one
        (supersede or propose). A confirmation is not a conflict."""
        return self.decision in (DECISION_SUPERSEDE, DECISION_PROPOSE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "conflict": self.conflict,
            "replacement": self.replacement,
            "related": [m.get("id") for m in self.related],
            "reason": self.reason,
        }


def is_replacement_intent(text: str) -> bool:
    return any(re.search(p, text or "", re.IGNORECASE) for p in REPLACEMENT_PATTERNS)


def _normalized_terms(text: str) -> set[str]:
    """Controlled normalized content tokens (synonyms + light stemming), so a
    same-dimension restatement is recognised across surface-form differences."""
    from .normalize import canonical_tokens  # noqa: PLC0415

    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {t for t in canonical_tokens(raw) if t not in _STOPWORDS and len(t) > 2}


def _content_terms(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if t not in _STOPWORDS and len(t) > 2
    }


def opposing(text_a: str, text_b: str) -> bool:
    """True when the two texts sit on opposite sides of a known polarity pair.

    Two layers, both deterministic: the legacy regex pairs (kept for exact
    wording) and the reviewed concept axes in `normalize` (which fold synonyms,
    stemming and negation, so paraphrases like "keep it punchy" vs "full
    deep-dive" are recognised). Unknown wording fires neither.
    """
    from .normalize import axes_contradict  # noqa: PLC0415

    a, b = (text_a or "").lower(), (text_b or "").lower()
    for left, right in OPPOSING_PAIRS:
        if re.search(left, a) and re.search(right, b):
            return True
        if re.search(right, a) and re.search(left, b):
            return True
    return axes_contradict(a, b)


def _same_subject(subject: Optional[str], other_subject: Optional[str]) -> bool:
    return bool(subject) and bool(other_subject) and subject.strip().lower() == other_subject.strip().lower()


def same_dimension(subject: Optional[str], other: Optional[str]) -> bool:
    """Whether two subject keys identify the same dimension.

    Equal keys always match. Otherwise the shared subject-alias vocabulary is
    consulted, so a dimension stated under a different key ("charts" vs a
    "chart-style" alias) is still recognised. Unknown keys never match.
    """
    if _same_subject(subject, other):
        return True
    if not subject or not other:
        return False
    from .normalize import SUBJECT_ALIASES, canonical_tokens  # noqa: PLC0415

    a = set(canonical_tokens(SUBJECT_ALIASES.get(subject.strip().lower(), ())))
    b = set(canonical_tokens(SUBJECT_ALIASES.get(other.strip().lower(), ())))
    return bool(a & b)


def detect_conflict(
    *,
    memory_type: str,
    scope: str,
    scope_id: Optional[str],
    subject: Optional[str],
    content: str,
    existing: list[dict[str, Any]],
    new_authority: str = "explicit",
) -> ConflictAssessment:
    """Assess the disposition of `content` relative to eligible existing memory.

    Eligibility mirrors retrieval authorization: same memory type, same scope +
    owner, and the same dimension (subject identity via equality or alias, or
    enough shared normalized tokens). A different scope can never be a conflict.
    """
    # A task-scoped instruction ("for this task, …") is run-only: it never
    # changes a durable preference, so it is not a conflict at all.
    from .normalize import is_temporary_instruction, shared_axes  # noqa: PLC0415

    if is_temporary_instruction(content):
        return ConflictAssessment(decision=DECISION_NONE, reason=REASON_TEMPORARY)

    replacement = is_replacement_intent(content)
    new_terms = _normalized_terms(content)

    related: list[dict[str, Any]] = []
    for memory in existing:
        if memory.get("status") != "active":
            continue
        if memory.get("memoryType") != memory_type:
            continue
        if (memory.get("scope") or "") != (scope or ""):
            continue
        if (memory.get("scopeId") or None) != (scope_id or None):
            continue
        other_subject = memory.get("subject")
        by_subject = same_dimension(subject, other_subject)
        # When BOTH statements declare a subject, subject identity is
        # authoritative: two different subjects are different dimensions even if
        # they share value words ("dark" theme vs "dark" candlestick charts). Only
        # when a subject is absent on either side may content overlap link them.
        if subject and other_subject and not by_subject:
            continue
        other_content = memory.get("content") or ""
        overlap = len(new_terms & _normalized_terms(other_content))
        # A shared concept axis alone is deliberately NOT enough to link two
        # memories (a missed conflict is safer than replacing unrelated memory).
        # Axes are used below only to judge polarity once two memories are linked.
        if not by_subject and overlap < _RELATED_OVERLAP:
            continue
        related.append(memory)

    if not related:
        return ConflictAssessment(decision=DECISION_NONE, reason=REASON_UNRELATED_SUBJECT)

    # 1. Explicit replacement wins outright.
    if replacement:
        return ConflictAssessment(
            decision=DECISION_SUPERSEDE, replacement=True, related=related,
            reason=REASON_REPLACEMENT,
        )

    conflicting = [m for m in related if opposing(content, m.get("content") or "")]
    if not conflicting:
        # Same dimension, same polarity → a confirmation. Recognition is broad:
        # high token overlap, or a shared concept axis with no opposing polarity
        # (a same-pole paraphrase such as "keep answers brief" vs "I like short
        # responses"). Only a genuinely different dimension is `none`.
        from .normalize import axes_contradict  # noqa: PLC0415

        close = []
        for m in related:
            other = m.get("content") or ""
            if axes_contradict(content, other):
                continue
            if _jaccard(new_terms, _normalized_terms(other)) >= _CONFIRM_OVERLAP:
                close.append(m)
            elif shared_axes(content, other):
                close.append(m)
        if close:
            return ConflictAssessment(
                decision=DECISION_CONFIRM, related=close, reason=REASON_CONFIRMATION,
            )
        return ConflictAssessment(decision=DECISION_NONE, reason=REASON_UNRELATED_SUBJECT)

    # 2. Authority decides a contradiction without replacement wording.
    if new_authority == "explicit":
        automatic = [m for m in conflicting if (m.get("authority") or "explicit") == "automatic"]
        explicit = [m for m in conflicting if (m.get("authority") or "explicit") != "automatic"]
        if automatic and not explicit:
            # Explicit contradicts automatic → explicit wins.
            return ConflictAssessment(
                decision=DECISION_SUPERSEDE, related=automatic, reason=REASON_AUTHORITY_OVERRIDE,
            )
        # Two (or more) explicit statements contradict → ambiguous, needs review.
        return ConflictAssessment(
            decision=DECISION_PROPOSE, related=explicit or conflicting,
            reason=REASON_AMBIGUOUS_EXPLICIT,
        )

    # New automatic contradicts an explicit fact → store inert for review.
    explicit = [m for m in conflicting if (m.get("authority") or "explicit") != "automatic"]
    if explicit:
        return ConflictAssessment(
            decision=DECISION_PROPOSE, related=explicit, reason=REASON_AUTOMATIC_NEEDS_REVIEW,
        )
    # Automatic vs automatic → still needs review, never a silent supersede.
    return ConflictAssessment(
        decision=DECISION_PROPOSE, related=conflicting, reason=REASON_AUTOMATIC_NEEDS_REVIEW,
    )


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


__all__ = [
    "ConflictAssessment",
    "DECISION_CONFIRM",
    "DECISION_NONE",
    "DECISION_PROPOSE",
    "DECISION_SUPERSEDE",
    "OPPOSING_PAIRS",
    "REASON_AMBIGUOUS_EXPLICIT",
    "REASON_AUTOMATIC_NEEDS_REVIEW",
    "REASON_AUTHORITY_OVERRIDE",
    "REASON_CONFIRMATION",
    "REASON_REPLACEMENT",
    "REASON_TEMPORARY",
    "REASON_UNRELATED_SCOPE",
    "REASON_UNRELATED_SUBJECT",
    "detect_conflict",
    "is_replacement_intent",
    "opposing",
    "same_dimension",
]
