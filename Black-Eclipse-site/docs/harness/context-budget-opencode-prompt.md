# OpenCode Prompt — Model-Aware Context Budget & Honest Overflow

You are continuing work in the BlackEclipse repository. Fix a correctness bug in
the existing Python agentic runtime: **the runtime bounds conversation history
with a hardcoded guess and never learns its model's real context window.**

This is **a targeted bug fix with a visibility requirement**, not a context
management rewrite. It adds no tokenizer dependency, no summarization engine, and
no TypeScript agent logic.

Do not stop after proposing a plan. **Reproduce first** (Milestone 0), then
implement the milestones in order, run the required checks, update the progress
doc and changelog, and finish with a concise report of files, behavior, checks,
and limitations.

## Product and architecture context

- The agentic runtime is **Python** under `Black-Eclipse-site/python/harness/`
  (FastAPI + LangChain + LangGraph). Agents, tools, prompts, model invocation,
  context assembly, and events are Python-authoritative. Next.js is a thin front
  door/proxy; do not implement context budgeting or provider classification in TS.
- One retrieval seam, one decision gate, one memory store, one skill execution
  path. Reuse existing services and contracts.
- Providers are declared as **data** in `PROVIDER_CATALOG`
  (`python/harness/models.py`) — adding a field to `ProviderSpec` is the
  intended extension point, not a new branch.
- Model + credentials are resolved by the TS vault and passed per run in
  `ModelSettings` (`python/harness/schemas.py`). The Python service must never
  read env for secrets except as the existing explicit fallback.

## Non-negotiable repository rules

1. Read root `AGENTS.md`, `docs/NAVIGATION.md`, `docs/harness/architecture.md`,
   `docs/harness/memory-maintenance-progress.md`, `docs/DECISIONS.md`, and
   applicable skills under `Black-Eclipse-site/skills/` before edits.
2. Inspect `git status` and `git diff` first. **`jdds.db` is modified in the
   working tree and must stay untouched and uncommitted.** Preserve all unrelated
   user changes. Do not commit, push, or open a PR.
3. Read code before changing it. Keep files small; do not re-bloat `graph.py`
   (already large) — prefer a new sibling module for the budget logic.
4. Never fabricate numbers. Every token/window figure you emit must come from a
   real computation or a declared catalog value; an unknown window stays unknown
   and must be reported as such, never invented.
5. No new dependency. Do **not** add `tiktoken` or any tokenizer package. Reuse
   the existing estimator (see Milestone 1).
6. Append a dated entry to `docs/CHANGELOG.md` for every change, ending with
   `docs updated: <file(s)>` or `no doc change — <reason>`.
7. After each change, from `Black-Eclipse-site/`, run `npm run test` **and**
   `npx tsc --noEmit`, plus the targeted Python suites.

**Interpreter note:** the project's checks use the vendored interpreter. From
`Black-Eclipse-site/`:

```bash
npx tsc --noEmit
npx vitest run
./scripts/vendor/python/python.exe -m pytest python/tests -q
# module CLIs need the package root on sys.path:
cd python && ../scripts/vendor/python/python.exe -m <module>
```

## Objective

Two defects share one root cause. Fix both, and make the loss visible.

**Defect A — the bound is a guess, applied before assembly.**
`python/harness/graph.py` defines `MAX_HISTORY_TURNS = 20` /
`MAX_HISTORY_CHARS = 40_000` and `_bounded_history()` trims to those constants.
`ModelSettings` carries no context size, and `PROVIDER_CATALOG` declares no
context window. **Nothing measures what the assembled request actually costs** —
the system prompt, tool schemas, the four per-run context blocks, the history and
the user turn are never summed. A 40 000-char history is roughly 10–13k tokens on
its own, which overflows a small-context model and wastes most of a large one.

**Defect B — overflow is indistinguishable from any other failure.**
`HarnessErrorCode` (`python/harness/schemas.py`) has fourteen codes and none for
context overflow. A provider's context-length rejection falls through to a
generic `PROVIDER_ERROR` / `INTERNAL_ERROR`, with no recovery and no explanation.

**Defect C — the loss is silent.**
`_bounded_history` computes `dropped` precisely, but the only related event is
`memory.dropped_context_failed`, emitted on **failure only**. There is no success
event, no dropped count, and no UI surface. A user whose follow-up depends on a
trimmed turn is told nothing and concludes the agent forgot.

**Target behaviour.** For a supported run, the runtime should know the resolved
model's context window (or honestly not know it), budget the request against it,
trim history to what actually remains, tell the user when it trimmed, and — when
a provider still rejects the request for length — classify that specifically,
retry once with a tighter budget, and otherwise fail with a precise, honest
error.

## Milestone 0 — Reproduce before changing anything

**This milestone gates the rest.** Do not skip it and do not assume the premise.

1. Configure a **small-context** model (a local `ollama`/`lmstudio` model, or
   any provider model with a small window is acceptable for a probe; a test
   double in `python/tests/` that raises the provider's native overflow error is
   also acceptable and preferred for determinism).
2. Drive a conversation past the history bound with a long enough transcript
   that the assembled request exceeds the window. A deterministic fixture is
   fine — the point is to observe the real code path, not to use a live API.
3. Record **exactly** what happens today: the run's terminal status, the error
   code and message the user sees, whether any event was emitted, and whether any
   retry occurred.
4. Also confirm the other half: with a **large-context** model and a 40-turn
   history, confirm the bound discards turns the model could have held.

Record the observed behaviour in `docs/harness/context-budget-progress.md`
(create it), with the exact fixture and command used.

**If the premise does not reproduce** — e.g. the provider client already raises a
clean, specific error that the runtime handles well — **stop and report that
honestly.** Do not invent a bug. In that case implement only Milestones 1, 4 and
5 (the registry, the honest bound reporting, and the visibility work), state in
the progress doc that Defect A/B did not reproduce, and say what you actually
observed. A truthful "the premise does not hold" is an acceptable outcome.

## Milestone 1 — Context-window knowledge (declared, not guessed)

Add context-size knowledge as **data**, following the existing catalog pattern.

1. Add an optional `context_window: Optional[int] = None` field to `ProviderSpec`
   in `python/harness/models.py`.
2. Populate it for the catalog entries with a **documented, conservative** value
   per provider/model family. Where a provider's models vary widely, prefer a
   conservative floor over a best-case maximum, and note the value's provenance
   in a comment. Where you genuinely do not know, leave it `None` — do not guess
   a number.
3. Add a resolver, e.g. `resolve_context_window(provider: str, model: str) ->
   Optional[int]`. It must:
   - prefer a model-specific value when the catalog can express one;
   - fall back to the provider's declared window;
   - return `None` (never a fabricated number) when nothing is known;
   - be a pure function, unit-tested, with no network call.
4. Define the **unknown-window policy** explicitly and document it: when the
   window is unknown, the budget must fall back to today's conservative
   behaviour (the existing `MAX_HISTORY_TURNS` / `MAX_HISTORY_CHARS` ceiling)
   rather than assuming a large window. Unknown must be safe, and every place
   that reports it must say "unknown".
5. Reuse the **existing** token estimator
   (`python/harness/eclipse_memory/profile.py::estimate_tokens`) rather than
   writing a second one. Document it as an approximation, and require the budget
   to keep margin because of that.

**Tests** (`python/tests/test_context_window.py`): resolver returns the declared
value for a known provider; returns `None` for an unknown one; model-specific
beats provider-level; unknown-window policy selects the conservative ceiling; the
resolver is pure and makes no network call.

## Milestone 2 — Measured, model-aware budgeting

This is the core fix. **Requirements 1 and 2 must land together** — raising the
bound without measuring first would turn today's silent forgetting into a hard
provider failure.

1. Add a small module (e.g. `python/harness/context_budget.py`) that computes the
   budget for a run. It must **measure the actual request**, not estimate the
   history in isolation:
   - the resolved system prompt (the one actually sent, after surface filtering);
   - the tool schemas actually advertised for this run;
   - every per-run context block actually present (`profile`, skill manifest,
     retrieved memory, dropped-context);
   - the user turn (including any attached document text);
   - the reserved output allowance.
2. Derive the history allowance from what remains: `window − measured_overhead −
   reserved_output`, converted to the estimator's unit, then converted to a turn
   budget. Keep the existing `MAX_HISTORY_CHARS` as an **absolute ceiling** so a
   pathological history can never exceed it even on a huge window.
3. Wire it into `graph.py` so the history bound is derived per run from the
   **resolved** model, not from module constants. The per-run read must follow
   the existing convention (the same way `memory_enabled` /
   `session_history_enabled` are already resolved per run) — never an
   import-time or `AgenticService.__init__`-time decision.
4. **Do not break prompt caching or byte-stability.** The system-prompt head and
   the tool schema must stay byte-stable within a run. This change alters only
   how much history is included, which is already per-run.
5. **Preserve today's behaviour exactly when the window is unknown** — same
   trimming, same message list. A short conversation must remain byte-identical
   to the pre-change output. This is the safety property that makes the change
   reviewable.

**Tests** (`python/tests/test_context_budget.py`): a large window keeps more
history than today's bound; a small window keeps less; an unknown window
reproduces today's bound exactly; the overhead measurement includes the real
per-run blocks; the absolute char ceiling still holds on a huge window; a run
whose history is under the bound produces an identical message list to before.

## Milestone 3 — Classify overflow as its own failure

1. Add a `CONTEXT_OVERFLOW` code to `HarnessErrorCode` in
   `python/harness/schemas.py`.
2. Add a classifier that recognises a context-length rejection across the
   supported provider families (OpenAI-compatible, Anthropic, Google, Mistral,
   Groq). Match on the provider's error type/code **and** bounded message
   patterns — do not match a bare substring so loosely that an unrelated error is
   misclassified. Put it beside the model layer, not inline in `graph.py`.
3. When the classifier fires, the run must not report `PROVIDER_ERROR` or
   `INTERNAL_ERROR`. It must report `CONTEXT_OVERFLOW` with a message stating
   what happened and what the runtime is doing about it.
4. Classify **before** any generic catch-all so the specific code wins.

**Tests**: each provider family's canonical overflow error classifies as
`CONTEXT_OVERFLOW`; an unrelated provider error still classifies as its existing
code (false-positive guard); a rate-limit/timeout/auth error is never
misclassified as overflow.

## Milestone 4 — Bounded recovery (one retry, then honest failure)

1. On a classified `CONTEXT_OVERFLOW`, retry **once** with a materially tighter
   history budget (e.g. a reduced fraction of the window, or half the current
   history allowance). One retry only — do not loop.
2. If the retry succeeds, the run completes. Record honestly that a retry
   happened and what the budget was reduced to.
3. If it still overflows, return `CONTEXT_OVERFLOW` with the specific reason and
   do not attempt further retries.
4. The retry must not duplicate side effects: do not re-run tools that already
   executed, and do not persist a second terminal run status. Exactly one
   terminal status per run.
5. Respect cancellation and the run timeout throughout.
6. Every branch must be observable in events with no secrets and no raw prompt
   contents.

**Tests**: overflow → tighter retry → success (the message list on retry is
strictly smaller); overflow → retry → overflow → honest `CONTEXT_OVERFLOW` with
no third attempt; exactly one terminal status persisted; a tool with side effects
is not re-executed across the retry; cancellation during the retry still
cancels.

## Milestone 5 — Make the trimming visible

**Why.** Defect C. The run knows it dropped context and does not say so.

1. Emit a `memory.history_bounded` event on the **success** path whenever history
   was actually trimmed. Include: dropped turn count, kept turn count, the
   estimated tokens of the dropped window, the resolved window and whether it was
   known or unknown, and whether a tighter retry was used. Never emit memory
   content or the dropped text itself — counts and estimates only.
2. Emit nothing when nothing was dropped. A short conversation must produce no
   new event.
3. Surface it in chat. The generic streaming event passthrough in
   `src/lib/agent/use-agent-run.ts` already carries `name`/`summary` for
   activity items — use that path; do not build a parallel event system and do
   not add a new heavyweight component unless the existing one genuinely cannot
   carry a single line.
4. When a run **did** drop turns, the user must be able to tell. Keep it honest
   and non-alarming: it is a statement of fact about context, not an error.
5. When the run failed with `CONTEXT_OVERFLOW`, the chat must show the specific
   reason and the remedy (a shorter conversation, or a larger-context model) —
   not a generic failure string.
6. Extend the TypeScript run/result contracts **additively** so old persisted
   runs and old clients still work. Confirm backward compatibility with a test.

**Tests**: a trimmed run emits exactly one `memory.history_bounded` with correct
counts and no content; an untrimmed run emits none; the event carries
`windowKnown: false` when the model is unknown; the TS type accepts a legacy run
row with no such metadata; the overflow error surfaces its specific message
through the run result contract.

## Milestone 6 — Verification and documentation

1. Re-run the Milestone 0 fixture and confirm the previously-failing case now
   behaves correctly. Record before/after side by side in the progress doc.
2. Confirm no regression in: general chat, skill execution, memory recall and
   injection, research/evidence-gated runs, cancellation, and the honest 503 when
   Python is unavailable.
3. Confirm the retrieval and contradiction eval gates are unchanged (this work
   must not move them):
   - `python -m harness.eclipse_memory.eval`
   - `python -m harness.eclipse_memory.eval.contradictions_cli`
4. Update `docs/harness/architecture.md` if context assembly is described there,
   and `docs/harness/decisions.md` with an ADR if you made a real decision
   (unknown-window policy, the retry contract, the estimator choice).
5. Add a `docs/NAVIGATION.md` row for context budgeting pointing at the owning
   modules, so the next reader finds it without re-deriving this analysis.
6. Append every change to `docs/CHANGELOG.md`.
7. Maintain `docs/harness/context-budget-progress.md` throughout: baseline
   observation, per-milestone state, files, checks, known limits, next action.

## Checks

From `Black-Eclipse-site/`:

```bash
npx tsc --noEmit
npx vitest run
./scripts/vendor/python/python.exe -m pytest python/tests -q
# eval gates (need the package root on sys.path):
cd python && ../scripts/vendor/python/python.exe -m harness.eclipse_memory.eval
cd python && ../scripts/vendor/python/python.exe -m harness.eclipse_memory.eval.contradictions_cli
```

Report exact pass counts and every gate result. If a failure is pre-existing and
unrelated, say so explicitly with the evidence — never silently exclude it.
Confirm `jdds.db` is untouched.

## Explicit non-goals

- **No summarization / compaction engine.** A token-aware summariser with a
  compaction threshold and an overflow→summarise→retry ladder is a *follow-up*,
  gated on the event data this work emits. Do not build it here.
- **No new dependency** (no `tiktoken`, no tokenizer package, no network call).
- **No second token estimator** — reuse `estimate_words`/`estimate_tokens` from
  `eclipse_memory/profile.py`.
- **No context-window guessing.** Unknown stays unknown and is reported as such.
- No TypeScript context budgeting, model adapter, or agent loop.
- No change to the memory decision gate, retrieval ranking, skill lifecycle, or
  any operator gate.
- No multi-user/auth/tenancy work.
- Do not "fix" the existing `dropped_context.py` fail-closed behaviour, the
  per-run profile materialization, or the surface-honesty gate — those are
  correct as shipped.

## Final report

Report:

- **The Milestone 0 reproduction**, verbatim: what was observed before the fix,
  or an honest statement that the premise did not reproduce.
- Per milestone: what changed, files touched, and the evidence it works.
- Before/after behaviour for the reproduced case.
- Exact checks and pass counts, and both eval gate results.
- Every honest limitation: providers whose window you could not establish, cases
  where you used a conservative floor rather than a real value, anything the
  estimator approximates, and anything you measured as inconclusive.
- Confirmation that the safety invariants still hold: one decision gate, one
  memory store, one skill execution path, byte-stable system prompt within a run,
  unknown-window safety, exactly one terminal run status, no fabricated numbers.
- `docs updated: <file(s)>` / `no doc change — <reason>` for each change.
