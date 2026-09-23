# OpenCode Follow-up Prompt — Wire and Harden Phase 4 in Live Chat

Continue the existing BlackEclipse Phase 4 evidence-grounded answering work.
The research engine, endpoints, mandate/coverage/claim contracts, calculations,
and receipt persistence have been added, but the current progress report lists
live chat wiring, semantic evaluation, source restatement links, and receipt UI
as deferred. Audit the current checkout first because code may have changed
since that report. Then implement the remaining work in dependency order.

Do not stop at a plan. Preserve unrelated user changes, implement in small
reviewable steps, run the required checks, update progress docs and changelog,
and report exact outcomes. Do not commit, push, or open a PR.

## Read first

Read root `AGENTS.md`, `docs/NAVIGATION.md`, and:

- `docs/harness/phase-4-progress.md`
- `docs/harness/phase-4-opencode-prompt.md`
- `docs/harness/architecture.md`, `docs/harness/decisions.md`, and
  `docs/DECISIONS.md`
- `python/harness/research/{engine,mandate,coverage,claims,citations,receipt,calculations}.py`
- `python/harness/{graph,main,models,schemas,persistence,events,service}.py`
- `python/harness/retrieval/{contract,cache,layer,normalize,structured,web}.py`
- The existing run/chat API routes and clients, run result types, SSE handling,
  chat response components, and tests.

Inspect `git status` and `git diff` before edits. Treat current source as
authoritative if it disagrees with the progress report. In particular, verify
the alleged coverage and hash bugs against the exact current code before
changing them; if already fixed, preserve that fix and add/retain regression
coverage instead of reapplying it.

## Architecture constraints

- Python under `python/harness/` owns all agent decisions, model invocation,
  retrieval planning, evidence validation, and receipt creation.
- Next.js remains a thin front door/proxy and resolves model settings from the
  existing vault. Do not add a TypeScript agent loop or second model adapter.
- Reuse the existing `FinancialRetrievalLayer`, JDdS bridge, `run_research`,
  model factory, run/event persistence, and response metadata contracts.
- JDdS remains the single market-data vault path. Reuse the shared web research
  implementation; do not add a second search system or database.
- Unsupported/general chat continues through the existing agent graph.
- Do not claim semantic entailment is verified just because citations exist.
  Preserve `needs_review` / unverified where support cannot be checked.
- No fabricated facts, dates, source authority, citations, or confidence.
  Research remains read-only; no order placement or external writes.
- Skills and Eclipse-Memory remain operator-gated; this work must not enable
  automatic promotion or mutate learning policy.

## Workstream 1 — Fix deterministic evidence matching and stable identifiers

Audit and fix these conditions if they remain:

1. In `research/coverage.py`, a mandate leg with a required unit must not be
   covered if the evidence omits that unit. Return `unknown` (or an equally
   honest non-covered status) for missing metadata; return `unavailable` or
   conflicting only when appropriate.
2. A leg requiring an instrument must not be covered by an observation whose
   instrument/canonical identity is absent. Compare canonical identity, market,
   and symbol using the strongest fields actually supplied. Missing identity is
   unknown, never a wildcard match.
3. Replace substring-of-digits period matching with explicit canonical parsing
   and rules for annual, quarter, and date-range periods. Prevent an annual leg
   from matching an arbitrary quarter or a malformed/adjacent year. Preserve
   legitimate aliases through tests.
4. Audit any other “missing required field passes” behavior for basis,
   currency, source tier, and point-in-time publication metadata.
5. Replace Python built-in `hash()` values used for receipt evidence hashes or
   calculation IDs with stable cryptographic digests over canonical serialized
   data. An evidence hash must include a bounded canonical representation of
   evidence content and relevant provenance, not merely the evidence ID.
   Calculation identity must include the calculation version, formula, inputs,
   and assumptions; distinct values for the same dates must not collide.

Add focused regression tests for every corrected case, including deterministic
IDs/hashes across fresh processes or equivalent independent invocations.

## Workstream 2 — Integrate the validated research flow into live chat

Wire a supported `financial_comparison` request into the normal Python run path.
Use the existing run’s `ModelSettings` with `build_chat_model`; do not retrieve
secrets or choose a different model in TypeScript. Use a structured synthesis
contract (provider-supported structured output where reliable, otherwise strict
JSON parsing plus Pydantic validation) to produce `Synthesis` claims, evidence
IDs, gaps, assumptions, and estimates.

Expected flow for a supported request:

```text
chat run created
  → parse/validate research mandate
  → retrieve each required fact through existing Python retrieval bridge
  → deterministic coverage
  → model synthesizes only from the bounded evidence packet + mandate
  → deterministic claim validation
  → at most one bounded repair pass
  → render only validated/qualified claims + explicit gaps
  → persist receipt and attach research metadata to the run result
```

Implementation requirements:

- Select supported runs before the ordinary agent graph performs its own
  financial tool loop, to avoid duplicate retrieval and contradictory answers.
- General/unsupported requests must retain the existing Phase 1–3 path.
- Do not classify all chats as research. Audit and harden the classifier so
  symbol-shaped acronyms, company names, two companies vs two periods, vague
  “growth” wording, unsupported concepts, and follow-up turns cannot be
  misrouted. If the request lacks an unambiguous supported mandate, fall back
  safely to the existing path or ask through existing clarification behavior.
- Scope the first synthesis to period comparisons; do not broaden metric support
  implicitly. Include prior chat context only as context for resolving the ask,
  never as financial evidence. Label attached/user-provided data distinctly.
- The synthesis model receives only the research prompt, mandate, bounded
  evidence packet, coverage report, and repair feedback. Do not send memory as
  evidence or give this synthesis call tools that can bypass retrieval.
- Use the configured model and bounded time/token limits. Record synthesis
  failure and return an honest partial/unavailable research result; do not
  silently fall through to an ungated model answer for a request already routed
  into the evidence gate.
- Emit useful persisted events for mandate classification, research start,
  coverage, synthesis, validation, repair, and final status. Do not expose
  secrets or unbounded raw source contents in events.
- Respect cancellation and the run timeout. Persist exactly one terminal run
  status. Avoid invoking the full agent graph after successful gated synthesis.
- Track model token usage where the provider reports it. Do not invent usage.
- Persist the final answer, validated metadata, and research receipt coherently;
  on persistence failure expose a diagnostic and never imply the receipt was
  saved when it was not.

Add integration tests through `execute_run` or the closest real run seam using
fake deterministic bridge/model implementations. Cover supported success,
partial coverage, unsupported request fallback, invalid synthesis JSON,
unsupported claim, one repair then success, repair still rejected, provider
failure, timeout/cancellation, and no duplicate retrieval. Preserve existing
general chat regression tests.

## Workstream 3 — Surface evidence metadata and receipts

Extend the existing Python/TypeScript run result contracts additively so a gated
run can return:

- Final research status (`accepted`, `partial`, `rejected`, or equivalent).
- Validated claims and their support status/evidence IDs.
- Citations derived only from retrieved evidence.
- Coverage gaps, unresolved conflicts, assumptions, estimates, interpretations,
  temporal cutoff status, and calculation inputs/assumptions.
- Receipt reference/availability and a safe persistence diagnostic, if needed.

Wire through the existing `GET /runs/{id}` / event flow and TypeScript proxy. Do
not route the live chat through an unneeded second `/research/run` call when the
normal run can own the same flow. Reuse existing typed run/UI contracts and
frosted-glass components. In chat, show compact citations/coverage status inline
with a clear affordance to inspect evidence and missing legs. Ensure content
does not claim “verified” when claims are `needs_review`.

For detailed receipts, add a guarded read-only run receipt route/client/UI only
if existing run details cannot reasonably carry the information. Enforce run
ownership/authorization according to current API conventions. Bound list/detail
payloads and do not expose raw secrets or entire retrieved documents. Include
loading, empty, unavailable, and partial-result states.

Test TypeScript contracts/proxies/UI rendering as well as Python serialization.
Maintain backward compatibility for old persisted run rows and clients that
have no research metadata.

## Workstream 4 — Semantic-support evaluation (not an “AI truth detector”)

Create a small versioned, human-reviewed evaluation set of claim/evidence pairs
from synthetic fixtures and permitted, stable examples. Label each as
`supported`, `unsupported`, `conflicting`, or `indeterminate`, with a short
rationale and evidence span/reference. Do not place fabricated examples in live
financial data or present synthetic evaluation data as market facts.

Evaluate separately:

- Citation ID/URL correctness (deterministic).
- Entity, metric, period, basis, unit, currency, and temporal match
  (deterministic).
- Semantic entailment/support (human-labeled and potentially model-assisted).
- Conflict disclosure and gap honesty.

If adding an LLM critic, treat its result only as an advisory signal. Compare it
against human labels; measure precision/false-accept rate and recall/false-
reject rate, stratified by claim type and source. Document model/version and
prompt version. Keep production claim status at `needs_review` unless the
deterministic checks pass and the product’s explicit support policy permits the
claim status. Do not market evaluation performance as a guarantee of truth.

Add a command/script or existing test harness integration that reports counts,
confusion matrix, false accepts, false rejects, and per-slice results. Fix label
leakage: the judge must not see the gold label/rationale while judging. Record
dataset version and checksums. Any threshold changes require a test and ADR or
documented decision update.

## Workstream 5 — Evidence supersession and restatement chain

First identify which current providers expose stable document/filing IDs,
amendment indicators, filing dates, accession numbers, or explicit restatement
relationships. Do not infer a restatement because a later number differs.

Add provider-neutral optional provenance fields only when the source can support
them, such as document ID, version ID, `supersedesEvidenceId`, relationship kind
(`amends`, `restates`, `corrects`, `withdraws`), and source publication time.
Preserve both old and new observations with their periods and availability
times. A chain must be source-grounded, auditable, and cycle-checked.

For “as of” research, only use a revision available by the cutoff. For current
research, expose the latest source-backed version while retaining the history
and showing that it superseded a prior record. If providers do not supply enough
metadata, leave the chain absent and report restatement coverage as unavailable;
never manufacture links. Add fixtures for a valid amendment, unrelated changed
observation, missing publication time, cyclic/bad link, and point-in-time query
before/after the amendment. No provider expansion is required if existing
sources lack a reliable revision contract; record that blocker and defer safely.

## Verification and documentation

Before each change inspect `git diff` and protect unrelated work. After changes:

- Run relevant targeted Python tests during implementation.
- Run the repository-required `npm run test` and `npx tsc --noEmit` from
  `Black-Eclipse-site/`.
- Run any added evaluation command and report its exact dataset/version and
  metrics. Do not report only aggregate pass/fail if semantic evaluation was
  run.
- Test general chat, supported research chat, partial/unavailable data,
  conflicts, point-in-time cutoff, cancellation, and receipt reads end to end.
- Verify no second search/data path, duplicate retrieval loop, automatic skill
  promotion, secrets in receipts/events, or fabricated numeric output.

Update `docs/harness/phase-4-progress.md` with milestone states, files, checks,
known limits, and the next action. Update `docs/harness/architecture.md`,
`docs/harness/decisions.md`, `docs/DECISIONS.md`, `docs/NAVIGATION.md`, and
`QUICKSTART.md` only when the implemented behavior triggers those docs. Append
every change to `docs/CHANGELOG.md`; do not rewrite past entries. Mark a
limitation resolved only after the complete live path and its regression test
prove it.

## Completion criteria

- The current audited coverage gate rejects or classifies missing required
  identity/unit/period metadata honestly; period matching is canonical and
  tested.
- Evidence/calculation identifiers are stable and content-sensitive across
  processes.
- Supported financial comparisons in live chat use the research engine and the
  configured model synthesizer; unsupported chat remains on the existing path.
- Final chat output and stored run detail expose validated citations, gaps,
  conflicts, temporal limitations, calculations, and receipt availability.
- Repair is bounded; provider/model failure cannot bypass the gate.
- Semantic evaluation is versioned and human-labeled; `needs_review` remains
  honest wherever semantic support is not proven.
- Restatement links are created only from source-backed metadata; unavailable
  source metadata remains a documented limitation.
- Tests/checks pass, docs/changelog are updated, and unrelated working-tree
  changes remain untouched.

Final report: what is wired/fixed, which limitations remain (especially any
provider metadata gaps), changed files, exact checks and evaluation metrics,
documentation status, and any baseline failures.

