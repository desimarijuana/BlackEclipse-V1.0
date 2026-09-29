"""Trivial-prompt gate (Milestone 5).

A small, PURE predicate that identifies a turn not worth walking the memory
decision/retrieval path: empty input, slash commands, and bare
greetings/acknowledgements. It is anchored so real content never matches
(`hi` matches, `history` does not; `ok` matches, `okx` does not).

It changes no stored state and never affects the user's reply. An explicit
remember/forget/correct is ALWAYS handled by the always-on intent path and is
therefore never suppressed by this gate: `is_trivial_turn` returns False for any
turn that carries an explicit memory directive.
"""

from __future__ import annotations

import re

# Bare greetings / acknowledgements. Anchored: the WHOLE trimmed turn must be a
# greeting token (with optional punctuation), so "hi" matches and "history" or
# "hi there, analyze NVDA" do not.
_GREETING_RE = re.compile(
    r"^\s*(hi+|hello+|hey+|yo|sup|thanks?|thank you|thx|ty|cheers|"
    r"good (morning|afternoon|evening|night)|"
    r"ok(ay)?|k|cool|nice|great|sure|yep|yes|no|nope|"
    r"bye|goodbye|see ya|later|np|you'?re welcome|yw)"
    r"[\s!.,]*$",
    re.IGNORECASE,
)

# Slash commands (e.g. "/clear", "/help extra args"). Treated as control input,
# never memory-relevant.
_SLASH_RE = re.compile(r"^\s*/\S+")

# Any explicit memory directive disqualifies a turn from being trivial — the
# always-on intent path must still see it.
_EXPLICIT_MEMORY_RE = re.compile(
    r"\b(remember|forget|correct(?:\s+this)?|save (?:this|that|my)|"
    r"note (?:this|that|down)|keep (?:this )?in mind|from now on)\b",
    re.IGNORECASE,
)


def is_trivial_turn(text: str | None) -> bool:
    """True when the turn should skip the memory decision/retrieval path.

    Empty input, a slash command, or a bare greeting/acknowledgement. An explicit
    memory directive (remember/forget/correct/…) is never trivial.
    """
    if text is None:
        return True
    stripped = text.strip()
    if not stripped:
        return True
    if _EXPLICIT_MEMORY_RE.search(stripped):
        return False
    if _SLASH_RE.match(stripped):
        return True
    return bool(_GREETING_RE.match(stripped))


__all__ = ["is_trivial_turn"]
