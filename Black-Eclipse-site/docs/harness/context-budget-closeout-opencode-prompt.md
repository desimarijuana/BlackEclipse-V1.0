# OpenCode Prompt — Close Out the Context-Budget Work

You are finishing the model-aware context-budget work in the BlackEclipse
repository. The functional work is **already implemented, committed and
verified** (commit `df12d975`); the six milestones in
`docs/harness/context-budget-opencode-prompt.md` are all done. This prompt closes
the **remaining loose ends**: one stale document status, stale check figures in
that document, one unimplemented visibility surface, and a scope reconciliation.

This is a **small, precise close-out**, not new feature work. Do not redesign
anything. Do not reopen the six milestones. Do not add a compaction engine.

Do not stop after proposing a plan. Implement every item below, run the required
checks, update the docs and changelog, and finish with a concise report.

## Read first

- Root `AGENTS.md`, `docs/NAVIGATION.md`.
- `docs/harness/context-budget-opencode-prompt.md` (the seven-section plan this
  work implements).
- `docs/harness/context-budget-progress.md` (the implementation log — items 1
  and 2 below are edits to this file).
- `docs/harness/architecture.md` § "Model-aware context budgeting".
- `python/harness/context_budget.py`, `python/harness/models.py`,
  `python/harness/graph.py`.
- `src/lib/agent/events.ts`, `src/lib/agent/response-model.ts`,
  `src/components/chat/activity-item.tsx`.

Inspect `git status` and `git diff` before editing. **`jdds.db` is modified in
the working tree and must stay untouched and uncommitted.** Preserve all
unrelated user changes. Do not commit, push, or open a PR.

## Verify the current state first

Do not trust the figures in the progress doc or in this prompt — **measure
them.** This is the whole point of items 2 and 4. Run, from
`Black-Eclipse-site/`:

```bash
npx tsc --noEmit
npx vitest run
./scripts/vendor/python/python.exe -m pytest python/tests -q
```

and record the exact totals you observe. (The vendored interpreter is the one
the project's own `scripts/test-python.js` uses; the bare `python` shim does not
have the agent stack installed.)

## Item 1 — Correct the progress doc's status

`docs/harness/context-budget-progress.md` declares `status: In Progress` in its
frontmatter, but all six milestones are complete and verified.

Set it to `Complete` — **but only after you have re-confirmed that is true**
(all six milestone sections present and their stated tests passing, and the
Milestone 0 reproduction reproduced on this checkout). If you find any milestone
genuinely incomplete, leave the status truthful and say so in your report rather
than marking it Complete to close the task. A doc that admits it is in progress
is useful; a doc that lies is not.

## Item 2 — Correct the progress doc's stale check figures

The same file reports numbers that no longer match reality. Last measured:

| Doc says | Actually observed |
|---|---|
| `147 files, 1828 tests passed` (vitest) | **148 files, 1831 tests** |
| `1429 passed` (pytest) | **1430 passed** |

Replace the stale figures with the totals **you measure in this run**, and do not
hand-copy the numbers above — they may have moved again. If a figure you measure
still differs from the commit message or the changelog, note the discrepancy in
your report instead of silently picking one.

Also reconcile the same document's test-count breakdown if it no longer adds up
against the actual per-file counts.

## Item 3 — Surface memory recall in the UI

**Why.** `memory.retrieved` is emitted by the runtime
(`python/harness/graph.py`, in `_memory_context`) with a real, bounded payload —
`selected`, `candidates`, `usedChars`, `budgetChars`, `selectedIds`,
`selectionReasons`, `excludedCount`, `excluded`. It is **never surfaced**: a grep
of `src/lib/agent/events.ts` and `src/components/chat/activity-item.tsx` finds no
mapping for it. So the runtime now tells the user when history was *trimmed*
(`memory.history_bounded` → a `bounded` activity line with a `Scissors` icon) but
never when memory was *recalled*. Recall happens invisibly.

This is the last asymmetry in the run's own observability. Close it by mirroring
the pattern that already works — **do not invent a second mechanism.**

**Requirements.**

1. In `src/lib/agent/events.ts`, add a mapping for `memory.retrieved` that returns
   one activity item, using the **same shape** as the existing
   `memory.history_bounded` branch (which returns `{kind: 'activity_start', item:
   {...}}` with `id`, `kind`, `name`, `label`, `status`, `summary`).
2. Emit **nothing** when `selected` is 0 or absent — a run that recalled no
   memory must produce no new line, exactly as an untrimmed run produces no
   `bounded` line. Returning `null` is the established pattern; follow it.
3. Use a **new distinct `kind`** (e.g. `'recall'`) rather than reusing
   `'bounded'` or `'retrieval'` — the three mean different things and the icon
   lookup is keyed on `kind`. Add the new member to the kind union in
   `src/lib/agent/response-model.ts` (`kind: 'tool' | 'retrieval' | 'bounded' | ...`).
4. In `src/components/chat/activity-item.tsx`, add a distinct icon for the new
   kind, following the existing one-line pattern in the `kind → icon` helper
   (`bounded` → `Scissors`, `retrieval` → `Globe`). Pick an existing `lucide-react`
   icon that reads as "remembered/recalled"; do not add a dependency.
5. The label and summary must be **counts and estimates only** — never memory
   content, never the selected memory text, never an excluded record's text.
   Mirror the honest, compact tone of the trimmed-history line, e.g. a label
   naming how many memories were recalled and a summary of the character budget
   used. Do not expose `selectedIds` or `excluded` in the UI line.
6. Respect the existing detail-panel behaviour: the `retrieval` kind already has
   an expandable source detail. Decide deliberately whether recall should be
   expandable and **state your decision and reasoning** in the progress doc —
   if you make it expandable, the expanded payload must still be content-free
   (counts, reasons, ids are acceptable; memory text is not).
7. Do not regress the existing `bounded` or `retrieval` rendering. Keep the
   activity feed's ordering and de-duplication behaviour intact.
8. If the runtime should also carry a structured recall blob on the run result
   (the way `context` was added for budgeting), add it **additively only** —
   absent for older rows and old clients must still compile and read. If you
   decide the activity line is sufficient, say so and skip the contract change; do
   not add a contract field nobody reads.

**Tests.** Extend `src/lib/agent/events.test.ts` (which already covers
`memory.history_bounded`) with the mirror cases: a populated `memory.retrieved`
maps to exactly one item with the new kind; `selected: 0` returns `null`; a
malformed/absent payload returns `null` rather than throwing; the label/summary
contain no memory content. If you touch the run-result contract, add a legacy-row
compatibility assertion alongside `src/lib/harness/context-budget-contract.test.ts`.

## Item 4 — Reconcile the scope delta between prompt and implementation

The implemented commit bundled a **model picker** that the original prompt did not
request: `PROVIDER_MODELS` declared in `python/harness/models.py`, exposed via
`GET /api/harness/models` (`src/app/api/harness/models/route.ts`), consumed by
`src/lib/agent/model-catalog.ts`, and rendered as a datalist Model field in
`Settings > AI / LLM` (`src/components/screens/settings.tsx`). It is also the
reason the test counts moved.

1. **Verify it works and is tested.** It is legitimate adjacent scope, but it
   shipped without a corresponding milestone. Confirm the route returns the
   catalog, the client hook consumes it, the field accepts both a listed id and a
   free-text custom value, and the context-window hint it shows comes from the
   real `resolve_context_window` rather than a hardcoded string. If any of that is
   missing or broken, fix it.
2. **Document it.** Add a short, accurate note to
   `docs/harness/context-budget-progress.md` recording that the model picker was
   delivered as adjacent scope beyond the original six milestones, with its
   owning modules. Do not rewrite history or retro-fit it into a milestone it was
   not part of.
3. **Add the NAVIGATION entry** for the model catalog if it is missing — the
   existing row (line ~84) covers the context budget but may not name the
   catalog route/client/hook. Update it or add a row so a reader finds the
   picker without re-deriving it.

## Item 5 — Confirm the deliberate omissions are documented

Do **not** implement these. Confirm each is stated as a deliberate, documented
decision (in the progress doc's "Known limitations" and the ADRs), and add the
note if it is missing:

- No summarization / compaction engine — the emitted
  `context.overflow` / `context.retry` / `memory.history_bounded` /
  `memory.retrieved` data is what a future compaction ladder would build on.
- Unknown windows stay unknown (`ollama`, `lmstudio`, `openrouter`, `together`,
  `fireworks`, `custom`) — conservative ceiling, never a guess.
- Conservative floors for `groq` (8 192) and `mistral` (32 000) under-use a
  larger model's window; deliberate and safe.
- Recovery is first-call only; an overflow after a tool ran is reported honestly
  but not retried, to avoid re-executing side effects.
- The token estimator is approximate (~4 chars/token), absorbed by a 10% margin
  and the absolute character ceiling.

## Checks

From `Black-Eclipse-site/`:

```bash
npx tsc --noEmit
npx vitest run
./scripts/vendor/python/python.exe -m pytest python/tests -q
```

And the two eval gates, which **must be unchanged** by this work (it touches no
retrieval or contradiction logic — a moved gate means something is wrong):

```bash
cd python && ../scripts/vendor/python/python.exe -m harness.eclipse_memory.eval
cd python && ../scripts/vendor/python/python.exe -m harness.eclipse_memory.contradictions_cli
```

Report exact pass counts and every gate result. If a failure is pre-existing and
unrelated, say so explicitly with the evidence — never silently exclude it.
Confirm `jdds.db` is untouched.

## Documentation obligations

- `docs/harness/context-budget-progress.md` — status (item 1), figures (item 2),
  the recall-surface decision and its reasoning (item 3.6), the model-picker
  scope note (item 4.2), and any missing omission note (item 5).
- `docs/CHANGELOG.md` — a dated entry for every change, ending with
  `docs updated: <file(s)>` or `no doc change — <reason>`. Append only; never
  rewrite past entries.
- `docs/NAVIGATION.md` — the model catalog row (item 4.3), and adjust the
  context-budget row if the recall surface changes its owning modules.
- `docs/harness/decisions.md` — only if you make a genuine decision (e.g. making
  recall expandable, or choosing not to carry a recall contract field). Mirror
  any new ADR into `docs/DECISIONS.md` per the authority hierarchy.
- Bump `last-verified` **only** on docs you actually re-read against the code.

## Explicit non-goals

- No compaction / summarization engine.
- No new dependency (no tokenizer, no UI library).
- No change to the memory decision gate, retrieval ranking, skill lifecycle, or
  any operator gate.
- No reopening of the six context-budget milestones.
- No TypeScript agent logic; no second event system.
- No fabrication: every number in a doc or a UI line must come from a real
  measurement or a real payload field.

## Final report

Report:

- The exact check totals **you measured**, and any discrepancy found between the
  progress doc, the changelog and the commit message.
- The progress doc's true pre-edit status and whether marking it Complete was
  justified.
- The recall surface: what you mapped, the new kind and icon, the label/summary
  text, your expandable-or-not decision with reasoning, and the tests added.
- The model picker: what you verified, what you fixed (if anything), and where it
  is now documented.
- Confirmation that each deliberate omission is documented, or the note you added.
- Both eval gate results, unchanged.
- Every honest limitation and anything you could not complete.
- `docs updated: <file(s)>` / `no doc change — <reason>` for each change.
