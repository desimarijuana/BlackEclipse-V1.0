"""Zero-cost collapse and iterative summaries (Phase 4)."""

from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace

from harness import compaction as C
from harness.history import _bounded_history
from harness.schemas import ConversationTurn


# -- collapse_text -----------------------------------------------------------


def test_short_text_is_untouched():
    text = "a" * 100
    out, did, digest = C.collapse_text(text)
    assert out == text and did is False and digest == ""


def test_long_text_keeps_head_tail_and_a_verifiable_marker():
    text = "HEAD" + ("x" * 5_000) + "TAIL"
    out, did, digest = C.collapse_text(text)
    assert did is True
    assert digest == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert out.startswith("HEAD")
    assert out.endswith("TAIL")
    assert "collapsed" in out
    assert digest[:16] in out
    assert len(out) < len(text)


def test_collapse_is_idempotent():
    text = "y" * 4_000
    once, did, _ = C.collapse_text(text)
    twice, did_again, _ = C.collapse_text(once)
    assert did is True and did_again is False
    assert twice == once


def test_a_fold_never_grows_the_text():
    text = "z" * (C.COLLAPSE_MIN_CHARS + 1)
    out, did, _ = C.collapse_text(text)
    assert did is True and len(out) <= len(text)


# -- collapse_turn -----------------------------------------------------------


def test_collapse_turn_copies_without_mutating_the_original():
    original = ConversationTurn(role="assistant", content="q" * 5_000)
    folded, did, _ = C.collapse_turn(original)
    assert did is True
    assert len(original.content) == 5_000
    assert folded.content != original.content
    assert folded.role == "assistant"


def test_collapse_turn_ignores_unknown_shapes():
    class Weird:
        content = "w" * 5_000

    folded, did, _ = C.collapse_turn(Weird())
    assert did is False and folded is not None


def test_collapse_turns_preserves_order_and_reports_savings():
    turns = [
        ConversationTurn(role="user", content="short"),
        ConversationTurn(role="assistant", content="a" * 5_000),
    ]
    out, report = C.collapse_turns(turns)
    assert [t.role for t in out] == ["user", "assistant"]
    assert report.folded == 1
    assert report.saved_chars > 0
    assert "collapsed" not in out[0].content


# -- the real history bound --------------------------------------------------


def _budget(max_turns: int, max_chars: int):
    return SimpleNamespace(effective=True, max_history_turns=max_turns, max_history_chars=max_chars)


def test_a_long_turn_is_folded_instead_of_dropped(monkeypatch):
    monkeypatch.setenv("BE_HISTORY_COLLAPSE", "1")
    history = [
        ConversationTurn(role="user", content="first"),
        ConversationTurn(role="assistant", content="L" * 20_000),
        ConversationTurn(role="user", content="second"),
    ]
    request = SimpleNamespace(input=SimpleNamespace(history=history))
    kept, dropped = _bounded_history(request, _budget(max_turns=20, max_chars=5_000))
    assert dropped == []
    assert len(kept) == 3
    assert "collapsed" in kept[1].content


def test_collapse_is_off_by_default(monkeypatch):
    monkeypatch.delenv("BE_HISTORY_COLLAPSE", raising=False)
    history = [
        ConversationTurn(role="user", content="first"),
        ConversationTurn(role="assistant", content="L" * 20_000),
    ]
    request = SimpleNamespace(input=SimpleNamespace(history=history))
    kept, dropped = _bounded_history(request, _budget(max_turns=20, max_chars=5_000))
    # Today's behaviour: the over-long turn is dropped whole, not folded.
    assert kept == []
    assert len(dropped) == 2


def test_collapse_does_not_change_a_short_history():
    history = [ConversationTurn(role="user", content="hello")]
    request = SimpleNamespace(input=SimpleNamespace(history=history))
    kept, dropped = _bounded_history(request, _budget(max_turns=20, max_chars=5_000))
    assert [t.content for t in kept] == ["hello"]
    assert dropped == []


# -- iterative summary -------------------------------------------------------


def test_prompt_without_prior_asks_for_a_fresh_briefing():
    prompt = C.build_compaction_prompt(("q1",), ("a1",))
    assert "Write a short briefing" in prompt
    assert "prior-briefing" not in prompt


def test_prompt_with_prior_asks_for_an_update_and_carries_the_prior():
    prompt = C.build_compaction_prompt(("q2",), ("a2",), prior="DECISION: keep the hedge")
    assert "UPDATE that briefing" in prompt
    assert "DECISION: keep the hedge" in prompt
    assert "<prior-briefing>" in prompt


def test_compact_dropped_records_iteration():
    turns = [ConversationTurn(role="user", content="q"), ConversationTurn(role="assistant", content="a")]
    result = asyncio.run(C.compact_dropped(turns, use_model=False, prior_summary="prior"))
    assert result.iterated is True
    assert result.used_model is False
    assert "compacted-conversation" in C.render_compaction_block(result)


def test_compact_history_still_builds_a_block():
    turns = [ConversationTurn(role="user", content=f"q{i}") for i in range(4)]
    turns += [ConversationTurn(role="assistant", content=f"a{i}") for i in range(4)]
    result = asyncio.run(C.compact_history(turns, keep_turns=2))
    assert result.ok is True
    assert result.block
    assert result.dropped_turns == 6
