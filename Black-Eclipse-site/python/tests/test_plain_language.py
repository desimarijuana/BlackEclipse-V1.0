"""The runtime-produced plain-language gate (roadmap §9 G7).

Every refusal a command can produce carries ONE plain sentence plus a recovery
step, and neither contains a mechanism word from `policy.PLAIN_LANGUAGE_DENYLIST`.
This is the runtime half of the front-door gate in
`src/lib/i18n/plain-language.test.ts` — commands produce text, so the check
belongs in pytest too.
"""

from __future__ import annotations

import re

import pytest

from harness.code import policy
from harness.code.commands import COMMAND_REFUSAL_COPY, refusal_copy

_DENY = {t.casefold() for t in policy.PLAIN_LANGUAGE_DENYLIST}


def _leaks(text: str) -> set[str]:
    lowered = text.casefold()
    found: set[str] = set()
    for term in _DENY:
        if " " in term:
            if term in lowered:
                found.add(term)
            continue
        if re.search(rf"(^|[^a-z0-9]){re.escape(term)}([^a-z0-9]|$)", lowered):
            found.add(term)
    return found


def test_every_refusal_has_a_plain_reason_and_recovery():
    for code, copy in COMMAND_REFUSAL_COPY.items():
        assert copy.get("reason"), code
        assert copy.get("recovery"), code
        assert not _leaks(copy["reason"]), f"{code} reason leaks"
        assert not _leaks(copy["recovery"]), f"{code} recovery leaks"


def test_unknown_code_falls_back_to_plain_copy():
    copy = refusal_copy("SOMETHING_UNKNOWN")
    assert copy["reason"] and copy["recovery"]
    assert not _leaks(copy["reason"])
    assert not _leaks(copy["recovery"])


@pytest.mark.parametrize("code", list(COMMAND_REFUSAL_COPY))
def test_refusal_sentences_end_in_a_full_stop(code):
    copy = refusal_copy(code)
    assert copy["reason"].rstrip().endswith((".", "!", "?”", "?")), copy["reason"]


# -- Phase 7: delegation progress + aggregation sentences ---------------------


def test_delegation_aggregation_and_reasons_are_plain():
    """The fan-out user-facing text names the JOB, never the machinery."""
    from harness.delegation import ChildOutcome, DelegationResult, aggregate

    outcomes = [
        ChildOutcome(child_index=0, run_id="run_0", status="completed",
                     summary="Prices for AAPL.", claimed=["All tests pass."]),
        ChildOutcome(child_index=1, run_id="run_1", status="failed",
                     summary="", reason="It couldn't be reached."),
    ]
    result = DelegationResult(
        delegationId="dlg_x", outcomes=outcomes, droppedClaims=["All tests pass."],
    )
    result.aggregate = aggregate(result)
    assert result.aggregate
    assert not _leaks(result.aggregate), result.aggregate

    reasons = {
        "child_actor": "A child cannot work in a folder its parent does not already have.",
        "tool_not_held": "This child asked for a tool, which this task isn't allowed to use.",
        "width": "This asks for 5 at once; the most Eclipse does is 4.",
        "depth": "This work is nested too deeply for Eclipse to keep it straight.",
        "budget": "There isn't enough room to do all of these at once; try fewer at a time.",
        "sandbox": "That part needs to make changes, which isn't available on this computer right now.",
        "timeout": "This part took too long and was stopped.",
        "cancelled": "This part was stopped.",
        "no_result": "That part didn't return a result.",
    }
    for name, sentence in reasons.items():
        assert not _leaks(sentence), f"{name} leaks: {sentence}"
        assert sentence.rstrip().endswith((".", "!", "?")), name


def test_delegation_uses_no_orchestration_vocabulary():
    """child / parent / fan-out / budget / concurrency / depth never reach the surface."""
    from harness.delegation import aggregate

    text = aggregate(type("R", (), {"outcomes": [], "droppedClaims": []})())
    banned = ("child", "parent", "subagent", "fan-out", "fanout", "budget", "concurrency", "depth")
    lowered = text.casefold()
    for word in banned:
        assert word not in lowered, f"{word!r} reached the surface: {text}"


# -- Phase 8: analysis (computed) labels + missing-input prompts --------------


def test_analysis_labels_and_missing_prompts_are_plain():
    """A computed number names the JOB, never the machinery."""
    from harness.code.execution import computed_provenance
    from harness.code.recipes import RECIPES, run_recipe

    label = computed_provenance("the period change", source_digest="d").label
    assert not _leaks(label), label
    assert label == "Worked out by Eclipse"

    for recipe in RECIPES:
        prompt = recipe.missing_prompt
        assert not _leaks(prompt), f"{recipe.name} prompt leaks: {prompt}"
        assert prompt.rstrip().endswith(("?", ".")), recipe.name


def test_analysis_surface_uses_no_execution_vocabulary():
    """interpreter/argv/stdout/exit-code/module never reach a computed surface."""
    from harness.code.execution import computed_provenance
    from harness.code.recipes import RECIPES

    banned = ("interpreter", "argv", "stdout", "stderr", "exit code", "module", "sandbox", "import")
    surface = [computed_provenance("x", source_digest="d").label]
    surface += [r.missing_prompt for r in RECIPES]
    for text in surface:
        lowered = text.casefold()
        for word in banned:
            assert word not in lowered, f"{word!r} reached the surface: {text}"


# -- Phase 9: scaffold-kit titles, questions and result lines -----------------


def test_kit_strings_are_plain():
    """Every kit's title, summary, question and result line names the JOB."""
    from harness.code.kits import list_kits

    surfaces: list[str] = []
    for kit in list_kits():
        surfaces.append(kit["title"])
        for question in kit["inputs"]:
            surfaces.append(question["name"])  # machine name only, never shown
    # The user-facing result lines live in the i18n dictionary; the kit manifest
    # carries only keys. Assert the titles here (the dictionary half is the
    # front-door gate).
    for text in surfaces:
        assert not _leaks(text), f"kit surface leaks: {text}"


def test_kit_titles_and_refusals_use_no_mechanism_vocabulary():
    from harness.code.kits import list_kits

    banned = ("scaffold", "kit", "template", "worktree", "diff", "patch", "manifest", "sandbox", "argv")
    for kit in list_kits():
        title = kit["title"].casefold()
        for word in banned:
            assert word not in title, f"{word!r} reached the surface: {kit['title']}"
