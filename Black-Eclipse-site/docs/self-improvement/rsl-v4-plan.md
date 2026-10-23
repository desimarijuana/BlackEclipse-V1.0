---
title: "RSL v4 — archive-guided search, evaluation rigor, supervised autonomy"
status: Current
last-verified: 2026-10-22
---

# RSL v4 — plan and P0 status

v3 closed the post-landing and operator loop. v4 is about **where the search
looks, what counts as evidence, and how much the loop may close on its own**.
The safety floor is unchanged: the judge is frozen, a critical regression always
vetoes, `UNMEASURED` never passes, and nothing here auto-promotes a change.

## P0 — the archive and the sampler (implemented)

The hill climb used to propose only from the current champion. A measured
candidate that did not beat the champion was recorded and then discarded, which
is exactly the "greedy, no archive" configuration DGM's ablation reports as the
weakest. P0 separates two decisions that were previously one:

- **Where to explore** — `StateArchive.parent_for(...)` samples a measured state
  from the archive. It may sample a `stepping_stone` (a candidate that lost) or
  the champion.
- **What may be accepted** — `utility.acceptance(...)` is unchanged and always
  compares the candidate against the **champion**, never against the sampled
  parent. A candidate that beats a weak parent but not the champion is
  **retained, not accepted**.

### `self_improvement/sampler.py`

Pure, seeded, deterministic. Draws one parent from a pool:

- `uniform` — every state equally likely (a diversity floor).
- `weighted` — softmax over utility, `cmpScore` (reserved for v4 P1) and
  novelty; a new snapshot identity is maximally novel.
- `uct` — the same score plus an exploration bonus for under-sampled states
  (`visitCount`).

The sampler never writes and never decides acceptance.

### `self_improvement/archive.py`

`StateArchive` is a thin layer over the ONE `HarnessState` table (no second
store):

- `retain(state, status=...)` keeps a **measured** state. An unmeasured state is
  refused (`reason="unmeasured"`); the snapshot digest is the identity, so
  retaining the same state twice returns the existing row.
- `parent_for(scope=..., rng=..., mode=...)` samples and increments
  `visitCount`.
- `_evict(scope)` bounds the archive and retires **only** `stepping_stone` rows,
  least useful first. A `current`/`candidate`/`superseded` row is never evicted
  by the archive.
- A stepping stone is never promotable, never activatable and never current.
  `HarnessStateStore.promote`/`activate_surface` already refuse any status other
  than `candidate`/`current`.

### `HarnessState` additive columns

`visitCount`, `novelty`, `island`, `cmpScore`, `lastSampledAt`, migrated in
place (`ALTER TABLE` guarded by `PRAGMA table_info`). A row written before the
archive keeps its identity and reads `0`/NULL.

### `hillclimb.run_hillclimb`

New optional `archive=` and `rng=`. When `archive_mode != "off"`:

- each generation proposes from the sampled parent (recorded as
  `proposalParentId` on the generation and `proposalParentId` on every record);
- every measured rejected candidate is retained as a `stepping_stone`;
- an accepted candidate is retained as a `candidate` (the `on_accept` write
  already exists, so the archive dedupes by digest);
- the result carries `archive: {enabled, mode, sampled, retained}`.

With `archive_mode="off"` (the default) behavior is byte-identical to v3 and the
existing tests pass unchanged.

### Config

| env | default | meaning |
|---|---|---|
| `HARNESS_RSL_ARCHIVE` | `off` | enable archive sampling |
| `HARNESS_RSL_ARCHIVE_MAX` | `200` | cap (2–500; clamps like every budget) |
| `HARNESS_RSL_ARCHIVE_SAMPLE` | `weighted` | `uniform` / `weighted` / `uct` |

Hot config accepts the same three fields through `POST /evolution/rsl/config`.

## P1 — metaproductivity (implemented)

The archive now ranks a state by what its descendants achieved, not only by the
state's own score (the HGM result: benchmark performance is a poor proxy for
self-improvement potential).

### `self_improvement/cmp.py`

- `descendant_lift(state, children=..., config=...)` walks measured descendants
  breadth-first up to `horizon`, and returns the depth-discounted mean of
  `utility(descendant) - utility(state)`.
- The result carries `lift`, `samples`, `std`, an approximate `ciLow`/`ciHigh`,
  the bounded descendant rows and an explicit `coldStart`.
- A state with too few measured descendants, or no measured utility, is
  `coldStart: true` with `lift: null` — never a fabricated zero.
- It is a **sampling signal only**. `utility.acceptance` does not read it.

### Wiring

- `StateArchive` gained `refresh_cmp(...)`: after a measured state is retained,
  the state and its ancestors (up to `horizon`) are re-estimated and their
  `cmpScore` is persisted. On the read path, `parent_for` attaches a fresh
  estimate to pool rows that predate the feature (without writing).
- `sampler.scores` already blended `cmpScore` (weight 0.30); cold-start states
  contribute nothing.
- The archive summary reports the CMP setting, horizon and minimum sample.

### Config

| env | default | meaning |
|---|---|---|
| `HARNESS_RSL_CMP` | `off` | enable descendant-lift sampling |
| `HARNESS_RSL_CMP_HORIZON` | `3` | descendant depth (1–6) |

Both are accepted by hot config and clamped like every other setting.

## P2 — typed operators, novelty veto, and islands (implemented)

### `self_improvement/operators.py`

A proposal is now typed by what it mutates: `prompt`, `tool_guidance`,
`tool_subset`, `ceilings`, `context_policy`, `guardrail`, `subagent_prompt`,
`model_identity`, `skill_draft`, `code_patch`, `composition` or `unknown`.

- `classify_ops(target, ops)` types a code proposal; `classify_snapshot(base,
  candidate)` returns the changed surface fields, their operators and
  normalized novelty tokens.
- `tokens_for_ops` / `jaccard_novelty` / `is_near_duplicate` define novelty as
  the distance from the closest already-tried proposal.
- `CandidateProposal` carries `operator`; it is evidence about what is being
  tried, never authority.

### Novelty veto in `propose_many`

`propose_many(..., novelty_min=..., exclude_signatures=...)` drops a candidate
whose op set is a near-duplicate of one already kept or a tabu signature. With
the knob off (the default) behavior is unchanged; if every candidate is
filtered it raises `PROPOSAL_ALL_DUPLICATES` rather than silently returning a
smaller comparison.

### Islands and migration

`StateArchive` treats a non-global `scope` as an island:

- `ArchiveConfig.islands` / `island_migration_every` (off by default);
- every N measured states retained in a scope, `migrate_best(scope)` copies the
  island's best measured state into `global` as a `stepping_stone` (same
  snapshot digest, new row, `island = "migrated:<scope>"`). A digest already in
  `global` is not copied twice, and a migrated copy is never re-migrated;
- `parent_for(..., island=...)` can restrict sampling to one island;
- `islands()` and the archive summary report the per-island count and best
  measured utility.

The existing per-scope lease already allows two scopes to climb at once; P2
proves it with a concurrency test rather than adding a second scheduler.

### Config

| env | default | meaning |
|---|---|---|
| `HARNESS_RSL_NOVELTY_MIN` | `0` | Jaccard distance floor (0 = off) |
| `HARNESS_RSL_ISLANDS` | `off` | enable island migration |
| `HARNESS_RSL_ISLAND_MIGRATION` | `5` | measured states per migration (0 = off) |

## P3 — evaluation rigor foundation (implemented)

The corpus now has a committed source of truth and an explicit split-access
contract. Growing it to 250+ oracle-backed tasks remains a separate authoring
effort.

### `evaluation/corpus.py`

- `build_manifest()` recomputes each dataset's checksum and records task counts
  by split, oracle coverage, canary count and live-only count.
- `baselines/corpus_manifest.json` is committed (88 tasks, 8 datasets).
- `verify_manifest()` recomputes the corpus and compares; the new
  `corpus-manifest` gate in `scripts/test-evals.js` fails on drift.
- `validate_tasks(strict=...)` audits authoring: missing oracle, missing
  contamination metadata, unknown split. The legacy corpus reports `0.0` oracle
  coverage honestly; `--strict` is the rule for new work.
- CLI: `npm run rsl:manifest -- --build | --verify | --audit [--strict]`.

### `evaluation/contamination.py`

- Each purpose reads exactly one split: `optimization`→optimization,
  `validation`→validation, `canary`→held_out, `release`→release.
- `access_guard` raises `CONTAMINATION_SPLIT` on a cross-split read;
  `select_for_purpose` returns allowed and refused-with-reason.
- Decoy canaries (`metadata.canary`) make a PASS a `CANARY_HACK`
  (`assert_no_canary_hack`); a canary may live in optimization, never in
  validation.

## P4 — paired significance (implemented)

A Wilson interval says how precise one arm is. The acceptance decision needs a
different question: is the DIFFERENCE between the candidate and the champion
bigger than noise? The comparison is paired because both arms run the same tasks.

### `evaluation/significance.py`

- `paired_bootstrap(base_rates, candidate_rates, n=10000, seed=0)` resamples
  TASKS, returns the delta, a percentile CI, a one-sided bootstrap p-value and
  the paired-task count. Fewer than two paired tasks is `insufficient`, not a
  win.
- `mcnemar(...)` is the exact paired pass/fail test (normal approximation above
  200 discordant pairs).
- `required_trials(effect)` is a coarse planning estimate, printed so a corpus
  can be judged too small before it is used as evidence.
- `paired_rates(...)` reads per-task rates from a metrics dict OR a
  `SuiteResult` (TaskResult + measured trials), so callers do not project first.
- `ablation.compare_arms` now reports `deltaCi`, `pValue` and `pairedTasks` and
  renders the CI in the Markdown table.

### Acceptance

`utility.acceptance(..., require_significance=...)` is **opt-in**
(`HARNESS_RSL_SIGNIFICANCE`, off by default). When enabled:

- at least `HARNESS_RSL_SIGNIFICANCE_MIN_TASKS` paired tasks are required;
- the paired-bootstrap CI low bound must be above zero;
- otherwise the candidate is rejected with a named reason and the rejection is
  recorded with the CI.

A two-task "win" is therefore refused. Significance never applies to the
archive/CMP sampling signals; it is part of the acceptance decision only.

### Config

| env | default | meaning |
|---|---|---|
| `HARNESS_RSL_SIGNIFICANCE` | `off` | require a paired significant lift |
| `HARNESS_RSL_SIGNIFICANCE_MIN_TASKS` | `5` | minimum paired tasks (2–200) |

## P5 — pinned live-tier baselines and the published report (implemented)

Only the live tier measures a real model, so only the live tier may be pinned as
a model baseline. `evaluation/live_baseline.py`:

- keys a baseline by **provider + model + base URL + temperature + prompt hash +
  corpus checksum** - a changed prompt or corpus is a new experiment, never a
  silent update;
- `build_live_baseline(suite, ..., tier="live")` refuses a scripted suite and an
  empty provider/model; it stores the Wilson CI, per-category rates, task rates,
  cost/latency and provenance, and never an API key;
- `write_live_baseline` / `read_live_baselines` / `find_live_baseline` maintain
  the committed registry (`baselines/live_v1.json`, created on first write);
- `compare_live_baseline` runs the existing per-dimension regression gates and
  adds a paired CI + p-value; a critical regression fails the session;
- `publish_report` writes a Markdown report that always names the tier,
  provider, model, prompt hash, corpus checksum and verdict. No pinned baseline
  is `NOT COMPARED`, never `PASS`.

`nightly.py` gained `--live-baseline`, `--write-live-baseline` and `--publish`
(all require `--live`). The operator command is:

```bash
npm run rsl:nightly -- --live --provider <p> --model <m> \
  --write-live-baseline --publish
```

The gate ("one recorded live run") remains an operator action: it needs a real
provider/model/key. The machinery is tested with a synthetic suite; no live
number is fabricated in the repository.

## P6 — supervised autonomy, auto-apply and the kill switch (implemented)

`self_improvement/autonomy.py` separates the decision from the activation:

- **Risk classes.** `L0` (code patches, tool widening, guardrail removal, model
  identity, skill drafts) is never automatic. `L2` (capability-widening: added
  tools, raised ceilings, removed guardrails) requires a human. Only `L1`
  bounded surface changes (prompt wording, tool guidance, narrowed context
  policy, a delegated-child prompt, added guardrails) are auto-eligible.
- **Admission policy.** `decide(...)` requires supervised/bounded level, no kill
  switch, L1 risk, a paired `deltaCiLow > autoMinLift`, no critical regression,
  a clean canary/replay, a predicted direction that matches the measured one,
  and a daily activation budget. It is pure and names every refusal reason.
- **Kill switch.** `AutonomyKillSwitch` persists under `rsl.autonomy.kill` on
  the ONE agent-memory DB. `/evolution/rsl/autonomy/pause|resume` stop/allow
  every automatic decision without a restart; the state survives a reboot.
- **Surfaces.** `GET /evolution/rsl` reports `autonomyStatus`; the
  `routers/evolution_autonomy.py` module owns `GET /evolution/rsl/autonomy`,
  `POST .../pause|resume`, and `POST .../decide` (a preview that NEVER
  activates). It is a separate router so `routers/evolution.py` stays inside its
  size ratchet.

### The one automatic activation path

`RSLLoop.auto_apply_surface(state_id)` applies ONE measured surface state when
the policy allows:

- the state must be a `candidate` whose `EvolutionCandidate` has
  `subjectType == "surface"` and a valid `surfaceConfig` snapshot/base;
- it derives per-task rates from the recorded baseline and candidate
  `EvaluationRun`s, runs `paired_bootstrap`, and computes the per-dimension
  regressions; missing evidence is a refusal (`no_paired_evidence`);
- the risk class, kill switch, daily budget and all admission rules apply;
- on success it calls the existing `HarnessStateStore.activate_surface`, records
  an activation counter, and returns the `HarnessActivation` row - which is the
  rollback handle (`rollback_activation`).

`POST /evolution/states/{state_id}/autonomy-apply` is the operator-triggered
seam; a scheduler may call the same loop method. The policy and kill switch
should still be exercised in a dry run (`HARNESS_RSL_AUTO_MAX_PER_DAY=0`) before
an operator raises the budget. Nothing in this slice widens what an operator has
already approved.

### Config

| env | default | meaning |
|---|---|---|
| `HARNESS_RSL_AUTONOMY` | `off` | `off`/`observe`/`propose`/`verify`/`supervised`/`bounded` |
| `HARNESS_RSL_AUTO_MIN_LIFT` | `0.02` | minimum paired CI low bound |
| `HARNESS_RSL_AUTO_MAX_PER_DAY` | `1` | automatic activations per day (0 = dry run) |
| `HARNESS_RSL_AUTO_RISK` | `low` | only `low` (L1) is eligible |

## v4 slice status

| Slice | Goal | Gate |
|---|---|---|
| ~~P1~~ | ~~`cmp.py` - descendant-lift metaproductivity guides sampling (never acceptance)~~ | done |
| ~~P2~~ | ~~islands + typed operator registry + novelty veto~~ | done |
| ~~P3 (growth)~~ | ~~corpus to 250+ oracle-backed tasks and the quarterly held_out rotation~~ | done: 250 tasks, 162 oracle-tagged (coverage 0.648); `npm run rsl:rotate` (dry run by default) |
| ~~P4~~ | ~~paired-bootstrap significance in acceptance~~ | done |
| ~~P5~~ | ~~live-tier pinned baselines + published report~~ | machinery done; one operator live run remains |
| ~~P6~~ | ~~risk-classed supervised autonomy with kill switch and auto-apply~~ | done; the operator raises `HARNESS_RSL_AUTO_MAX_PER_DAY` after a dry run |

## Tests

- `python/tests/test_rsl_archive.py` — sampler preference, UCT exploration,
  tabu exclusion, novelty, retention/dedupe, unmeasured refusal, eviction,
  visit counting, and the integration invariant that acceptance is relative to
  the champion, not the sampled parent.
- `python/tests/test_rsl_loop.py` — the conductor wires the archive and a
  rejected measured candidate is persisted as a stepping stone.
- `python/tests/test_rsl_cmp.py` — descendant lift, horizon, cold start,
  ancestor refresh, CMP-off writes nothing, and a productive parent is sampled
  more often than a dead end.
- `python/tests/test_rsl_operators.py` — typed operators, snapshot
  classification, novelty distance, the veto, the tabu list, and the
  all-duplicates refusal.
- `python/tests/test_rsl_islands.py` — best-state migration, off-by-default,
  island-restricted sampling, per-island summary, two scopes climbing
  concurrently, and config clamps.
- `python/tests/test_evaluation_corpus.py` — manifest totals, verify, tampered
  checksum/count detection, and the strict/lenient authoring audit.
- `python/tests/test_evaluation_contamination.py` — split access, canary in
  validation, purpose selection, oracle/canary metadata and `CANARY_HACK`.
- `python/tests/test_significance.py` — paired bootstrap, seed determinism,
  `SuiteResult` extraction, McNemar and the planning estimate.
- `python/tests/test_rsl_significance.py` — a real lift accepted, a two-task win
  refused, missing paired data refused, significance-off unchanged, and the
  hill-climb wiring.
- `python/tests/test_live_baseline.py` — live-tier identity, no secret,
  registry roundtrip, prompt-sensitive keys, clean/regressed comparison, the
  published report and the `--live` CLI guard.
- `python/tests/test_autonomy.py` — risk classification, every admission rule,
  the persisted kill switch, the loop wiring and config clamps.
- `python/tests/test_autonomy_apply.py` — a clean L1 state applied and rolled
  back, the daily budget and kill switch stopping a second/third, L2 and
  non-surface refusals, and missing paired evidence.
- `python/tests/test_rsl_hillclimb.py` / `test_rsl_state.py` — unchanged and
  still green (archive-off compatibility).

See ADR-H316 for the decision and `docs/harness/architecture.md` for the module
map.
