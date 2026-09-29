"""Milestone 5 — the trivial-prompt gate.

A pure predicate: empty input, slash commands and bare greetings/acknowledgements
skip the memory decision/retrieval path without changing any stored state or the
user's reply. An explicit remember/forget/correct is never trivial.
"""

from __future__ import annotations

import pytest

from harness.eclipse_memory.is_trivial import is_trivial_turn

TRIVIAL = [
    "", "   ", "\n",
    "hi", "Hi!", "hello", "hey", "yo", "sup",
    "ok", "okay", "k", "cool", "nice", "great", "sure", "yes", "no", "nope",
    "thanks", "thank you", "thx", "ty", "cheers",
    "good morning", "good evening", "good night",
    "bye", "goodbye", "later", "np",
    "/clear", "/help", "/compact now",
]

NOT_TRIVIAL = [
    "history", "okx", "hi there, analyze NVDA", "highest price",
    "what is the price of AAPL",
    "hello, can you compare RELIANCE and TCS",
    "thank you for the analysis, now show me the chart",
    "note", "yesterday", "kite",
    "Remember that I prefer charts",
    "forget my preference",
    "correct this: I prefer Excel",
    "save this preference",
    "ok now do X",
    "thanks, that helped",
]


@pytest.mark.parametrize("text", TRIVIAL)
def test_trivial_matches(text):
    assert is_trivial_turn(text) is True


@pytest.mark.parametrize("text", NOT_TRIVIAL)
def test_near_misses_and_real_content_do_not_match(text):
    assert is_trivial_turn(text) is False


def test_none_is_trivial():
    assert is_trivial_turn(None) is True


def test_explicit_memory_directive_is_never_trivial():
    # Even a turn whose only content is a directive must reach the intent path.
    assert is_trivial_turn("remember") is False
    assert is_trivial_turn("forget") is False
    assert is_trivial_turn("correct this") is False


def test_gate_writes_no_state():
    # The predicate has no store/service argument and returns a plain bool.
    assert isinstance(is_trivial_turn("hi"), bool)
