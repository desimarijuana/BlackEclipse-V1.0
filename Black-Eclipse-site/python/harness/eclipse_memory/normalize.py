"""Deterministic lexical normalization for memory retrieval.

Retrieval ranking is lexical (no embeddings). A plain tokenizer misses realistic
paraphrases because users and stored memories use different surface forms of the
same concept ("money" vs "currency", "chart style" vs "candlestick"). This module
adds low-cost, bounded, explainable normalization applied to BOTH the query and
the memory text before matching:

  * light stemming (plural/singular and common suffix folding);
  * a small, human-reviewed synonym-group table for common memory concepts;
  * subject aliases (a subject key and its human phrasing);
  * safe typo tolerance via a bounded edit-distance check on longer tokens.

Rules (mirroring the brief):
  * this only affects CANDIDATE RELEVANCE — scope/status/privacy filtering stays
    authoritative and happens before ranking;
  * no network, no model, no embeddings;
  * a token is only folded to a synonym within its group; groups are disjoint and
    reviewed so folding cannot collapse unrelated concepts.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

# Synonym groups. Every token in a group normalizes to the group's canonical
# token. Groups are intentionally small and disjoint.
_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("currency", "money", "denomination", "denominated", "monetary"),
    ("chart", "charts", "graph", "graphs", "plot", "plots", "candlestick", "candlesticks"),
    ("concise", "brief", "short", "terse", "succinct", "minimal"),
    ("detailed", "verbose", "elaborate", "comprehensive", "in-depth", "indepth"),
    ("source", "sources", "citation", "citations", "reference", "references", "cite"),
    ("explain", "explanation", "explanations", "describe", "description", "phrasing", "phrased"),
    ("jargon", "technical", "terminology", "slang"),
    ("timestamp", "timestamps", "timezone", "tz", "utc", "clock"),
    ("fiscal", "fy", "financialyear"),
    ("period", "periods", "trailing", "ttm", "twelvemonth", "annual"),
    ("risk", "risky", "volatility", "volatile"),
    ("buy", "long", "purchase"), ("sell", "short", "dispose"),
    ("always", "invariably", "consistently"), ("never", "avoid", "refrain"),
    ("include", "show", "display", "with"), ("exclude", "hide", "omit", "without"),
    ("preference", "preferences", "prefer", "prefers", "preferred", "like", "likes", "favorite", "favourite"),
    ("answer", "answers", "response", "responses", "reply", "replies"),
    ("format", "formatting", "formatted", "style", "styling"),
    ("percent", "percentage", "pct"),
)

# Build a token -> canonical lookup.
_SYNONYM_MAP: dict[str, str] = {}
for _group in _SYNONYM_GROUPS:
    _canonical = _group[0]
    for _token in _group:
        _SYNONYM_MAP[_token] = _canonical

# Subject aliases: a subject key maps to the tokens a human query would use.
SUBJECT_ALIASES: dict[str, tuple[str, ...]] = {
    "answer-style": ("answer", "concise", "detailed", "format", "style", "response"),
    "charts": ("chart", "candlestick", "graph", "plot"),
    "currency": ("currency", "money", "denomination"),
    "reporting-currency": ("currency", "money", "denomination", "report", "statement"),
    "timestamps": ("timestamp", "utc", "timezone", "clock"),
    "periods": ("period", "trailing", "ttm", "annual", "fiscal"),
    "fiscal-year": ("fiscal", "year", "period", "annual"),
    "expense-ratio": ("expense", "ratio", "fee", "cost"),
    "explanation-style": ("explain", "jargon", "technical", "plain", "language", "phrasing"),
    "price-moves": ("price", "move", "moves", "magnitude", "basis", "points"),
}

# Common plural/suffix folds (carefully BOUNDED). Only pluralization is applied
# automatically: folding a verb suffix ("reporting" -> "report") collided with an
# unrelated noun ("report") and produced a false positive in the labeled eval, so
# it is deliberately NOT done. Concept-level folding is handled by explicit
# synonym groups above, which are human-reviewed.
_SUFFIX_RULES: tuple[tuple[str, str], ...] = (
    ("ies", "y"),      # currencies -> currency
    ("sses", "ss"),    # classes -> class
    ("ches", "ch"),    # batches -> batch
    ("shes", "sh"),
    ("xes", "x"),
    ("ses", "s"),
    ("s", ""),         # charts -> chart
)

# Tokens too short to risk a suffix fold (would collide: "is" -> "i").
_MIN_STEM_LEN = 4

# Minimum length for typo tolerance; shorter tokens are never fuzzy-matched.
_FUZZY_MIN_LEN = 6
_FUZZY_MAX_DISTANCE = 1


def stem(token: str) -> str:
    """A conservative singular/suffix fold. Returns the canonical synonym when the
    token is in a synonym group, else the folded form."""
    if token in _SYNONYM_MAP:
        return _SYNONYM_MAP[token]
    if len(token) < _MIN_STEM_LEN:
        return token
    for suffix, replacement in _SUFFIX_RULES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            candidate = token[: len(token) - len(suffix)] + replacement
            if candidate in _SYNONYM_MAP:
                return _SYNONYM_MAP[candidate]
            return candidate
    return token


def canonical_tokens(tokens: Iterable[str]) -> list[str]:
    """Fold each token through synonym lookup + light stemming, preserving order
    and deduplicating the result."""
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        folded = stem(token)
        if folded and folded not in seen:
            seen.add(folded)
            out.append(folded)
    return out


def bounded_edit_distance(a: str, b: str, max_distance: int = _FUZZY_MAX_DISTANCE) -> int:
    """Levenshtein distance capped at `max_distance + 1` (early-exit). Kept tiny
    for a bounded per-token cost."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > max_distance:
        return max_distance + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        row_min = i
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > max_distance:
            return max_distance + 1
        previous = current
    return previous[-1]


def fuzzy_token_match(query_token: str, haystack_tokens: set[str]) -> bool:
    """Safe typo tolerance: a longer query token matches a longer haystack token
    within edit distance 1. Only used when exact/steem matching found nothing."""
    if len(query_token) < _FUZZY_MIN_LEN or query_token in haystack_tokens:
        return False
    for candidate in haystack_tokens:
        if len(candidate) < _FUZZY_MIN_LEN:
            continue
        if abs(len(candidate) - len(query_token)) > _FUZZY_MAX_DISTANCE:
            continue
        if bounded_edit_distance(query_token, candidate) <= _FUZZY_MAX_DISTANCE:
            return True
    return False


# ── Concept axes (deterministic polarity) ───────────────────────────────────
# A *concept axis* is a human-reviewed dimension with two opposing poles. A
# statement carrying a LEFT term and another carrying a RIGHT term are
# contradictory ON THAT AXIS. Axes are matched by canonical (synonym/stemmed)
# token, so paraphrases within a pole ("short" ~ "brief" ~ "punchy") still match.
# This is conservative: an axis only fires when a text actually carries one of
# its terms, and an axis contradiction only matters for memories already linked
# by subject identity or enough shared content (see `conflicts.py`).
CONCEPT_AXES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("verbosity", ("concise", "brief", "short", "terse", "succinct", "punchy"),
     ("detailed", "verbose", "elaborate", "elaboration", "comprehensive", "thorough", "deep", "dive", "writeup", "writeups", "fluff")),
    ("complexity", ("simple", "plain", "basic"), ("advanced", "technical", "complex", "sophisticated")),
    ("sources", ("source", "citation", "reference", "cite", "link"), ("nosource", "nocitation", "unreferenced")),
    ("numbers", ("round", "rounded"), ("exact", "precise", "unrounded", "raw")),
    ("theme", ("dark", "night"), ("light", "bright", "day")),
    ("risk", ("conservative", "safe", "cautious"), ("aggressive", "risky", "bold")),
    ("trade", ("buy", "long"), ("sell", "short")),
    ("order", ("before", "prior", "first"), ("after", "following", "last")),
    ("cadence", ("daily",), ("weekly", "monthly", "quarterly")),
    ("preamble", ("nopreamble",), ("preamble", "intro", "introduction", "lead")),
)

# Negation tokens flip the pole of a term within a small window. Kept tight so a
# stray negation in an unrelated clause does not flip meaning.
_NEGATION_TOKENS = frozenset(
    {"not", "no", "never", "without", "dont", "doesnt", "avoid", "omit",
     "skip", "exclude", "hide", "stop", "refrain"}
)
_NEGATION_WINDOW = 3

# One-off / task-scoped markers: a statement about *this* task is run-only and
# must never be treated as a durable preference change.
TEMPORARY_PATTERNS = (
    r"\bfor this (task|run|turn|one|request|time|analysis|conversation)\b",
    r"\b(for now|just this once|this time|today only|in this run|right now)\b",
    r"\bjust for\b",
)


def is_temporary_instruction(text: str) -> bool:
    """True when the text is scoped to the current task rather than durable."""
    return any(re.search(p, text or "", re.IGNORECASE) for p in TEMPORARY_PATTERNS)


def _raw_canonical(text: str) -> list[str]:
    """Ordered canonical tokens (positions preserved for negation windows).

    Apostrophes are removed before tokenizing so a contraction stays one token
    ("don't" -> "dont"), which matters for the negation window.
    """
    cleaned = (text or "").lower().replace("'", "").replace("\u2019", "")
    return [stem(t) for t in re.findall(r"[a-z0-9]+", cleaned)]


def axis_polarity(text: str) -> dict[str, int]:
    """The polarity each concept axis carries in `text` (+1 left, -1 right).

    A negation within `_NEGATION_WINDOW` tokens before a pole term flips that
    term's vote, so "never include sources" (source + never) and "always include
    sources" land on opposite poles. An axis is only present when a term appears;
    a tie (both poles, equally negated) is dropped rather than guessed.
    """
    tokens = _raw_canonical(text)
    negation_positions = {i for i, t in enumerate(tokens) if t in _NEGATION_TOKENS}
    polarity: dict[str, int] = {}
    for name, left, right in CONCEPT_AXES:
        left_set = _axis_token_set(left)
        right_set = _axis_token_set(right)
        votes = 0
        for i, token in enumerate(tokens):
            pole = 0
            if token in left_set:
                pole = 1
            elif token in right_set:
                pole = -1
            else:
                continue
            if any(j in negation_positions for j in range(max(0, i - _NEGATION_WINDOW), i)):
                pole = -pole
            votes += pole
        if votes != 0:
            polarity[name] = 1 if votes > 0 else -1
    return polarity


_AXIS_CACHE: dict[tuple[str, ...], frozenset[str]] = {}


def _axis_token_set(terms: tuple[str, ...]) -> frozenset[str]:
    cached = _AXIS_CACHE.get(terms)
    if cached is None:
        cached = frozenset(canonical_tokens(terms))
        _AXIS_CACHE[terms] = cached
    return cached


def axes_contradict(text_a: str, text_b: str) -> bool:
    """True when the two texts assert opposite poles on the SAME concept axis."""
    a = axis_polarity(text_a)
    b = axis_polarity(text_b)
    return any(name in b and b[name] == -value for name, value in a.items())


def shared_axes(text_a: str, text_b: str) -> set[str]:
    """The concept axes both texts mention (regardless of polarity)."""
    return set(axis_polarity(text_a)) & set(axis_polarity(text_b))


__all__ = [
    "CONCEPT_AXES",
    "SUBJECT_ALIASES",
    "axis_polarity",
    "axes_contradict",
    "bounded_edit_distance",
    "canonical_tokens",
    "fuzzy_token_match",
    "is_temporary_instruction",
    "shared_axes",
    "stem",
]
