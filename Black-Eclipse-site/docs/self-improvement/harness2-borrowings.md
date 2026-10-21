---
title: Borrowings from Harness² — Techniques for Eclipse's Self-Improvement System
status: Stale
last-verified: 2026-10-20
superseded-by: docs/self-improvement/rsl-v3-plan.md
---

> **Withdrawn (2026-10-20).** Eclipse is building its own RSL. The native
> mechanisms that were implemented from this list (verdict guard, contrastive
> evidence, selection, lesson gate) now live in `evaluation/` and
> `self_improvement/` as Eclipse-owned code. This document is retained for
> history; do not add the upstream framework or its executor.

# Borrowings from Harness² — Techniques for Eclipse's Self-Improvement System

**Who this is for:** anyone implementing the "steal-list" workstreams that give
Eclipse's self-improvement system the parts of Harness² that are worth having,
without adopting the upstream framework.

**Source reviewed:** `google-research/harness2` at pinned revision
`1cfe254e8d25b15f37048c3730134686abe60335` — `harness2/core/`
(`recursion.py`, `selection.py`, `library.py`, `tree.py`, `context.py`,
`proposer.py`, `prompts.py`), plus `docs/EXPERIMENTS.md`. Apache-2.0; ideas are
re-implemented natively, no upstream code is vendored.

**What is deliberately NOT adopted** (per `architecture-audit.md`): the
framework itself, its OpenCode/Codex executors, its benchmarks, its network
defaults. This document is the mechanism-by-mechanism extraction: what upstream
actually does, what Eclipse already has, and which pieces to re-implement in
our own owners. Everything lands inert; promotion stays evaluation- and
operator-gated.

---

## 1. The verified mechanism (what upstream actually does)

### 1.1 Evidence-as-files + a short mission pointer

`core/context.py` builds an evidence **tree on disk** — `context/task.md`,
`context/rollouts/<label>.md` (FULL trajectories, "no prompt-budget
truncation"), `context/deliverables/…`, `context/harness/…` (the tree being
edited), `context/library/…`, `context/pool/<label>/` (candidate harness +
its rollout, an auto-generated `harness.diff`, `produced.md`) — and the prompt
is only a **pointer**: `mission()` returns the job, the layout of what actually
landed, and the rules: *read it, do not answer from the message alone*; *every
trajectory event is present*; *tool-result truncation markers are ours, not a
solver failure*; and the citation rule:

> "Cite the specific trajectory moment behind every change; one you cannot
> trace to a moment is speculation."

Deliverables are rendered **through the reader the work is assessed through**
("an artifact that does not survive that conversion is treated as unreadable
however good it looks").

### 1.2 Contrastive Propose–Probe–Compose (no ground truth)

`core/recursion.py`: `k` **reference executions** of the base harness are shared
evidence for every proposal. Each stage gets a typed job — `INV` (invariant /
general) or `DOM` (domain-specific) — builds candidates from the shared base
rollouts, rolls each candidate once, and records its decision note (the
proposer's own `<notes>`) and error. The composition stage then receives the
**full pool**: every candidate's harness, a unified diff against the current
harness, its rollout, its produced artifact, and a `decisions` map
(`{label: notes or error}`). The composer is instructed to compare "what
changed from its editing baseline, what behavior changed in its rollout, what
improved, and what regressed or remained unresolved" — all without ever seeing
a grader score. Parallel mode = `2k` candidates from shared evidence → `k`
independent compositions; sequential mode carries the composed harness and
accumulated evidence into the next round.

### 1.3 Verdict isolation (tripwires, not trust)

`core/context.py`: `GRADER_VERDICT_MARKERS` scanned **by file name and by
content**; `assert_no_grader_verdicts` fires on any evidence tree or
agent-authored harness before it can be rolled, stored, or served — "this is a
leak, not a false positive to widen around; find the read path that produced
it." `assert_no_leak_paths` refuses benchmark-declared answer-key paths.
`library.add()` re-runs the tripwire on the lesson text itself. On one benchmark
they even **withhold deliverable contents entirely** (names only) because the
trial directory co-locates grader output with artifacts.

### 1.4 Anonymized behavioral selection

`core/selection.py`: candidates are renamed to stable anonymous IDs (`A`, `B`,
`C`, …) by a **seeded shuffle** (seed = `task|k|mode`), so reruns are stable and
brand/position bias is impossible. Non-answers are dropped before anonymizing,
**each drop recorded with its cause** in `selection.json` plus `n_candidates`.
The selector reads the rendered evidence on disk and answers with a ```choice```
block plus `<why>`; a selector failure falls back **neutrally to a delivered
base**, and never raises. `k=1` uses `trivial_selection` — no selector session
at all. The full decision record (`chosen_label`, `id_map`, `why`, `dropped`,
`evidence: deliverable|trajectory`) is persisted.

### 1.5 The per-domain experience library

`core/library.py` + `selection._distil`: after adoption, a reflection session
distills the task-local record into a lesson with **mandatory fields** — `cue`,
`lesson`, `evidence` (all must be non-empty or the lesson is discarded) — plus
optional `confidence` and a `what each edit did` section. The library stores the
**full adopted harness tree + `EXPERIENCE.md`** (why it was chosen, edits, the
transferable lesson) and rebuilds a browsable `INDEX.md`. Retrieval is **by
construction** (a domain's directory only holds same-domain entries); libraries
are scoped per run/mode and `retain` keeps only entries preceding the current
task in the stream — no future leakage. The lesson text passes the
verdict tripwire before it is written.

### 1.6 Editable-surface spec + validation

`core/tree.py`: the editable surface is **data** (`SurfaceSpec`: always-on
files, skill dir, sub-agent dir, scripts, plugins, hooks; char caps; name
rules). Edit contract: **omitted is inherited** — a proposal emits only what it
changes. `read_tree` collects off-surface files as `rejected` so the proposal
can be told exactly what was refused and retried. `validate` checks: always-on
char cap; skill frontmatter (`description` missing ⇒ the skill is dropped
**silently** at load; `name:` mismatch warnings); **untriggered skill = dead
weight** (every skill must be named in the always-on text); python compiles;
hooks schema; and **script references must resolve** ("A invokes X but X is not
in the harness"). `autotrigger` repairs an untriggered skill by adding a
trigger line within the cap. `diff_summary` (added/removed/modified +
always-on char delta) and `diversity` (pairwise line-Jaccard over candidates —
collapse to one body is visible) close the loop.

### 1.7 Session hygiene

`core/proposer.py`: every improver session is (a) **content-addressed** — the
cache key hashes the mission, the system prompt, the resolved evidence path and
every file's bytes, so an interrupted run resumes for free and two modes are
independent draws; (b) **audited** — `mission/system/response/meta.json/
workspace` files per session; (c) strict — an empty reply is an error, never
swallowed; (d) **retried once with the rejection quoted** into the next attempt;
(e) the edited workspace is **harvested out before the temp dir is deleted**.

### 1.8 Failure-neutral policy + accounting

Dead rollouts are **recorded, never raised** (`RunView.ok/delivered/error`); an
invalid proposal falls back to the base harness and the stage is marked
`fell_back` with the error kept (truncated); the selector falls back neutrally;
only adapter bugs raise. The `Ledger` records rollouts and per-stage sessions
(cost, attempts, cached) and `assert_identity()` verifies the accounting.

---

## 2. Mapping to Eclipse's existing system

| Harness² mechanism | Eclipse today | Verdict |
|---|---|---|
| Evidence-as-files + mission pointer | `EvaluationTrial.trajectory` (JSON in DB); proposals get bounded prompt blobs; `TrialResult` in memory | **Adopt** — a file-based bundle + citation rule |
| Contrastive P–P–C, INV/DOM typing | `evaluation/improvement.py` (apply → suite → score gate, in-memory, unwired); `experiments.py` A/B (no contrast, no notes) | **Adopt the contrast + typing**; keep our score gates on top |
| Verdict isolation tripwires | none in the learning path; `evaluation/taxonomy.py` labels feed `improvement` proposals directly | **Adopt** — tripwire before bundles/lessons |
| Anonymized selection | `experiments.py` A/B compares scores; no anonymization, no recorded why, no drop-with-cause | **Adopt** — for no-ground-truth tasks and model matrices |
| Per-domain experience library | `LearningCandidate` (+ evidence, limitations), `skills/draft.py` SKILL.md, `LearningRecurrence`; no `cue` gate, no adopted-artifact store per lesson | **Adopt** — cue/evidence validation + artifact ref |
| Editable-surface spec + validation | `code/evolution.py` FROZEN_PATHS/FORBIDDEN_FIELDS; skills manifest + `content_scan`; `test_size_budget` | **Partial** — add prompt-cap, trigger-line and script-ref checks |
| Session hygiene (cache/audit/repair) | evaluation runner swallows persist errors silently; model review in `learning_review` is best-effort | **Adopt** — for model-backed proposal sessions |
| Ledger + failure-neutral policy | `EvaluationScore`/`EvaluationTrial` rows; `runner._persist_*` silently swallow errors | **Adopt** — record-not-raise + no silent persistence |
| Grading, executors, benchmarks, network defaults | Our evaluator, our runtime, our gates | **Skip** — see §4 |

---

## 3. The steal list (implementation tickets)

Design rules for every ticket: deterministic cores are pure and unit-testable;
model-backed steps are inert; no new runtime/DB; operator gates unchanged.

### T1 — Verdict-leak tripwire — **first slice implemented** (un-wired)

`python/harness/evaluation/verdict_guard.py`: `VERDICT_MARKERS`
(`pass_rate`, `weighted_composite`, `critical_dimensions`, `expected_output`,
`expected_state`, `EvaluationScore`, …), `find_verdict_leaks`,
`assert_no_verdict_leaks`, `assert_text_has_no_verdict_leaks`; scans file names
and text content (suffix allowlist), raises `VerdictLeakError`.
**Wire (T1b):** call before serving any bundle to a model and before persisting
a lesson (`skills/learning`, `learning_review` model assist). *Where:* new file
(sibling call sites later). *Gate:* unit tests.

### T2 — Contrastive evidence bundle — **first slice implemented** (un-wired)

`python/harness/evaluation/contrast.py`: `contrast_trajectories(baseline,
candidate)` — behavior tokens (tool identity survives, not just event type),
unified tool-sequence diff, metric deltas, first divergence index, deterministic
summary; `render_evidence_bundle(directory, …)` — `task.md`, full
`rollouts/<label>.md`, `diffs/<label>.md` vs baseline, `produced/`, `decisions/`,
`MISSION.md` with the citation rule; runs the T1 tripwire before returning.
**Wire (T2b):** `improvement.propose_improvements` / `evaluate_candidate`
proposal inputs; `learning_review` model review; future harness-candidate
proposals. *Gate:* unit tests.

### T3 — Anonymized behavioral selection — **implemented by R7**

Landed as `python/harness/self_improvement/selection.py` (not in
`evaluation/experiments.py`): `anonymous_labels` (seeded, stable, order-
independent), drop non-answers with recorded causes, a selection record
(`chosen`, `why`, `dropped`, `nCandidates`, `evidence`), neutral base fallback,
`k=1` trivial path. It is wired by `recursion.run_recursive` for RSL recursive
experiments. *Gate:* deterministic id tests + a scripted selection test.

### T4 — Lesson upgrade: cue + evidence gate + adopted artifact — **implemented by R6**

`LearningCandidate` gained `cue` and the adoption columns (migration 31); the
mandatory triple gate and verdict tripwire live in
`python/harness/self_improvement/lessons.py`, with scoped retrieval wired into
the prompt (`prompt.lesson_injected`). Operator promotion is unchanged.

### T5 — Harness-surface validator (Phase-4 enabler)

A `SurfaceSpec`-equivalent for Eclipse's editable harness allowlist: system
prompt segment char budget, skill frontmatter/trigger-line checks ("a skill
never named in the injected manifest is dead weight"), scripts compile, tool-ref
resolution, one-line `diff_summary`, `diversity` across candidates. Land:
extends `code/evolution.py` constraints + `skills/manifest.py` validation;
needed before any automated harness-editing candidate is accepted.
*Gate:* validator unit tests + existing evolution tests unchanged.

### T6 — Proposal-session cache + audit + repair retry

Content-addressed cache over (mission, system, evidence bytes, path), per-
session audit files, empty-reply-is-error, one repair retry with the rejection
quoted. First call site: `learning_review` model assist (currently inert).
*Gate:* cache-hit/corrupt-workspace tests. *Blocked by:* T2 wired (a stable
evidence bundle to hash).

### T7 — Diversity metric for experiments

Pairwise line-Jaccard + distinct-count across candidate artifacts in an
experiment run; warn (metric, not gate) when candidates collapse. Land:
`experiments.py`. *Gate:* unit test.

### T8 — Typed candidates + budget discipline — **implemented by R7**

`proposer.propose_many` tags candidates `invariant`/`domain`; `selection.py`
has the `k=1` trivial path; `recursion.budgeted_k` caps `k` by the remaining
daily budget and the recursive experiment records `k`/`requestedK` in
`EvaluationRun.config`. *Gate:* config/identity tests (`test_rsl_recursion.py`).

---

## 4. Deliberately NOT stealing

- **Grading** — our 17 graders, thresholds and regression gates are stronger
  than upstream's; their judge is benchmark-specific.
- **The executor/framework** — OpenCode/Codex substrates, benchmark deps,
  unrestricted network, disabled Codex sandbox: all incompatible with the ONE
  runtime and the security floor.
- **LLM free-hand editing of the active harness** — upstream edits a harness
  *tree in a workspace*; every Eclipse harness change stays typed, validated,
  inert, and operator-promoted (`code/evolution` + ADR-H112).
- **Adoption without operator** — upstream's selector adopts autonomously; for
  Eclipse, selection picks a *candidate for verification*, never a production
  change (invariant §5.3 of the self-evolution roadmap).
- **Selector sessions everywhere** — `k=1` trivial path and no selector session
  when the pool is one; cost discipline over ceremony.

---

## 5. First-slice status (landed in this change)

| File | What | Wired? |
|---|---|---|
| `python/harness/evaluation/verdict_guard.py` | T1 tripwire (names + content, `VerdictLeakError`) | Wired — R6 lesson gate + R7 selection/composition/bundles |
| `python/harness/evaluation/contrast.py` | T2 `contrast_trajectories` + `render_evidence_bundle` (runs the T1 tripwire) | Wired — R7 `recursion.run_recursive` |
| `python/tests/test_evaluation_verdict_guard.py` | tripwire tests | — |
| `python/tests/test_evaluation_contrast.py` | contrast + bundle tests | — |

The wiring landed in R6/R7: `self_improvement/lessons.py` guards adoption text;
`selection.py`/`composition.py` guard their records; `recursion.run_recursive`
guards every contrast bundle before it is recorded. No model proposer consumes
these bundles yet (v1c remains deferred).

## Related

- `docs/self-improvement/architecture-audit.md` — why the framework is not
  adopted; the component map and phase gates.
- `docs/harness/agent-evaluation.md` — the evaluator these tickets extend.
- `docs/harness/memory-skills-evolution-plan.md` — lesson/skill contracts T4
  must respect.
- `docs/harness/self-evolution-roadmap.md` — W3 verification spine + §5
  invariants (no new infra; operator-confirmed landing).
- Upstream: `google-research/harness2` @ `1cfe254e…`
  (`harness2/core/{recursion,selection,library,tree,context,proposer}.py`).
