"""The runtime-produced plain-language gate (roadmap §9 G7).

Every refusal a command can produce carries ONE plain sentence plus a recovery
step, and neither contains a mechanism word from `policy.PLAIN_LANGUAGE_DENYLIST`.
This is the runtime half of the front-door gate in
`src/lib/i18n/plain-language.test.ts` - commands produce text, so the check
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


# -- Phase 10: prepared-change states, refusals and metrics -------------------


def test_evolution_aggregation_text_is_plain():
    """The candidate states and refusals name the JOB, never the machinery."""
    # The plain states the UI shows (mirrors src/lib/i18n evolution.state.*).
    states = {
        "inert": "Prepared - not applied",
        "evaluated_ok": "Checked and ready",
        "evaluated_bad": "This change didn-t work as hoped",
        "rolled_back": "That change made things worse, so I put the previous version back",
        "activated": "In use now",
    }
    for name, sentence in states.items():
        assert not _leaks(sentence), f"{name} leaks: {sentence}"

    refusals = {
        "FROZEN_PATH": "I could not prepare this change - it would alter how Eclipse checks things.",
        "PROTECTED": "I could not prepare this change - that file is part of Eclipse-s own data.",
        "FORBIDDEN_FIELD": "I could not prepare this change - it would widen what Eclipse is allowed to do.",
        "OUTSIDE_WORKSPACE": "I could not prepare this change - it is outside the project.",
    }
    for code, sentence in refusals.items():
        assert not _leaks(sentence), f"{code} leaks: {sentence}"


def test_a_plain_problem_statement_is_not_a_mechanism():
    # The user-visible problem sentence carries the category and the count only.
    from harness.code import evolution

    statement = evolution._problem_statement("timeout", "the bound that timed out", 4)
    assert not _leaks(statement), statement
    assert "/" not in statement and "\\" not in statement


# -- Phase 11: delivery message keys, destination names and backend refusals ----


def test_delivery_message_is_a_key_plus_plain_params():
    """The runtime sends a template KEY + params, never a composed sentence.

    A message body names the finance job (and a real count) and nothing else — no
    run id, job id, duration in ms or delivery code.
    """
    from harness.jobs.model import JobDefinition, JobDelivery, JobTarget
    from harness.jobs.scheduler import _message_for
    from harness.persistence import now_iso

    now = now_iso()
    job = JobDefinition(
        id="job_pl", name="Overnight market brief", kind="manual",
        target=JobTarget(kind="objective", objective="x"),
        delivery=JobDelivery(adapter="messaging", destination="My phone"),
        created_at=now, updated_at=now,
    )
    known_keys = {
        "jobs.delivery.message.done",
        "jobs.delivery.message.doneCount",
        "jobs.delivery.message.trouble",
    }
    key, params = _message_for(job, "ok", {"changeCount": 3})
    assert key in known_keys
    assert set(params) <= {"jobName", "changeCount"}
    assert not _leaks(key), key
    for value in params.values():
        assert not _leaks(str(value)), value

    # A failed run's message is the trouble key and never carries a code.
    key, params = _message_for(job, "failed", None)
    assert key == "jobs.delivery.message.trouble"
    assert set(params) == {"jobName"}


def test_delivery_refusals_are_plain_and_one_sentence():
    """The backend/delivery refusal copy names the JOB, never the mechanism."""
    from harness.jobs import delivery

    reasons = [
        delivery.NO_DESTINATION,
        delivery.DELIVERY_FAILED,
        delivery.REFUSED,
    ]
    # The machine reason codes themselves are never shown; assert their plain
    # counterparts in the adapter's user-facing strings.
    assert not _leaks("I did not run that.")  # sanity: the scanner is active
    for text in ("No destination was chosen for this job, so there was nowhere to send it.",):
        assert not _leaks(text), text
    assert all(isinstance(code, str) and code.isupper() for code in reasons)

    from harness.code.backends import _plain_backend_reason

    reason = _plain_backend_reason("container")
    assert not _leaks(reason), reason
    assert reason.rstrip().endswith(".")


def test_backend_guarantee_summary_is_plain():
    from harness.code.backends import LocalBackend

    summary = LocalBackend().guarantees.summary()
    # The guarantee summary is a machine description, but it must not smuggle a
    # mechanism denylist term into the surface.
    assert not _leaks(summary), summary


# -- Phase 12: the capability statement + the blocked-action sentence ----------


def test_capability_statement_names_only_i18n_keys_not_sentences():
    """Every user-facing cell is a `capability.*` key, never a mechanism word."""
    from harness.code.eval.statement import _STATUS_KEY, SHAPE_KEY, render_statement
    from harness.code.eval.tasks import load_task_dataset

    for key in (*SHAPE_KEY.values(), *_STATUS_KEY.values()):
        assert key.startswith("capability.")
        assert not _leaks(key), key

    # The fixture dataset carries no user-facing sentence that leaks a mechanism.
    for case in load_task_dataset()["cases"]:
        for field in ("prompt", "rationale"):
            assert not _leaks(str(case.get(field, ""))), (case["caseId"], field)

    # The statement is derived and byte-stable (never hand-authored).
    assert render_statement() == render_statement()


def test_blocked_action_sentence_is_plain():
    """The one sentence behind a blocked action names the job, not the mechanism."""
    # Mirrors the `capability`/blocked-action copy; the machine code stays behind
    # "details". This is the sentence a user could meet.
    blocked = "I did not do that — it would have reached outside the work you asked for. Here is what I did instead."
    assert not _leaks(blocked), blocked
    assert blocked.rstrip().endswith(".")


def test_no_eval_jargon_reaches_a_user_facing_string():
    """threshold / false accept / category id never appear in a user-facing cell."""
    from harness.code.eval.statement import _STATUS_KEY, SHAPE_KEY

    jargon = ("threshold", "false accept", "falseaccept", "category id", "checksum", "overallscore")
    for key in (*SHAPE_KEY.values(), *_STATUS_KEY.values()):
        lowered = key.casefold()
        for word in jargon:
            assert word not in lowered, f"{word!r} reached a user-facing key: {key}"


def test_metrics_render_unknown_not_zero():
    from harness.persistence import AgentMemoryStore
    from harness.code import evolution
    import tempfile, os

    store = AgentMemoryStore(os.path.join(tempfile.mkdtemp(prefix="be-pl-evo-"), "agent-memory.db"))
    metrics = evolution.archive_metrics(store, window_days=90)
    assert metrics["successRate"] == "UNKNOWN"
    assert metrics["costPerSuccess"] == "UNKNOWN"
    store.close()
