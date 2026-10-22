---
title: Round 4 — Closing the Last Two Dimensions (9.01 → 9.50)
status: Active
last-verified: 2026-10-22
---

# Round 4 — Closing the Last Two Dimensions (9.01 → 9.50)

**What this is.** Round 3 finished every workstream in
[round-3-parity-plan.md](./round-3-parity-plan.md). Five of the seven
dimensions are at the target. This plan closes the two that are not:
**Evaluation (9.0)** and **Operations (4.0)**. It is short on purpose — it is
six workstreams, and four of them are one session each.

**Status.** `Draft` — written from the merged tree on 2026-10-21. Every gap
below was read out of the code or measured, not recalled.

---

## 0. A correction to the earlier number

I previously reported **~9.42** with Ops at **7.5**. That was optimistic about
the *process* criteria, and re-deriving it against its own sub-criteria gives a
lower number:

| Ops sub-criterion (target = 9.5) | Now | Why |
|---|---|---|
| Tagged releases | **1.0** | `v0.2.0` is *prepared* (version, release note) — `git tag -l` is empty |
| A shrinking surface | **3.0** | The ratchet is enforced, but the tree is 375,997 lines and rose this round |
| Clean, unique ADRs | **8.0** | 303 headings / 303 distinct — but 15 legacy entries lack the canonical shape |
| A second pair of eyes | **1.0** | `CODEOWNERS` exists with **placeholder** owners; zero external reviews |
| Landed, clean tree | **5.0** | The branch is clean and gate-green, and is **not on `main`** |
| Distributable | **2.0** | `pyproject.toml` is ready; nothing is published |
| **Ops** | **4.0** | |

A tag is not a tag until it exists, and a second pair of eyes is not a file.
The published number is **9.01**, and this plan is what moves it.

## 1. The arithmetic — why only these two

| Dimension | Weight | Now | Target | Points available |
|---|---|---|---|---|
| Loop | 20 | 9.5 | 9.5 | 0 |
| Ctx | 18 | 9.5 | 9.5 | 0 |
| ACI | 15 | 9.5 | 9.5 | 0 |
| Safe | 17 | 9.5 | 9.5 | 0 |
| Ext | 12 | 9.5 | 9.5 | 0 |
| **Eval** | 10 | **9.0** | 9.5 | **+0.05** |
| **Ops** | 8 | **4.0** | 9.5 | **+0.44** |
| | | **9.01** | **9.50** | **+0.49** |

Two consequences shape the whole plan:

1. **Further work on Loop/Ctx/ACI/Safe/Ext cannot help.** They are at target.
   Any effort there is polish, and this plan spends nothing on it.
2. **Ops carries 90% of the remaining gap at 8% weight.** It is the cheapest
   points in the entire programme, and every one of them is discipline.

## 2. The gap ledger

### 2.1 Evaluation — 9.0 → 9.5

| # | Gap | Evidence |
|---|---|---|
| E1 | **No live number has ever been published.** The lane exists and runs, and the file says `NOT MEASURED`. | `docs/harness/benchmarks.md` § "Live tier"; `evaluation/live_gate.py`; no provider secret in this environment |
| E2 | **No external suite.** Eclipse is comparable only to a harness that publishes the same way — which is none. | no `swe.?bench` / `vals` / `swe-rebench` adapter in the repo |
| E3 | **Four dimensions are measured but ungated**: `cost`, `latency`, `token_usage`, `reliability`. | `evaluation/scoring.py::DEFAULT_THRESHOLDS` — six entries, none of them these four |
| E4 | **The offline tier measures the runtime, not the agent.** `ScriptedAgentInvoker` replays `metadata.agent_script`. | `evaluation/runner.py:281`; 51 of 68 tasks carry a script |
| E5 | **The corpus is curated, not observed.** 68 tasks, hand-written; production failures arrive only through `evaluation/mining.py`. | `evaluation/datasets/*.json` |

### 2.2 Operations — 4.0 → 9.5

| # | Gap | Evidence |
|---|---|---|
| O1 | **The branch is not landed.** 11 commits ahead of `main`, gate-green. | `git rev-list --count main..feature/round-3-harness-parity` |
| O2 | **No tag.** `v0.2.0` version + release note exist; `git tag -l` is empty. | `git tag -l` |
| O3 | **The surface is bounded, not shrinking.** 375,997 lines; the total ceiling rose twice this round. | `scripts/size-budget.json` |
| O4 | **No second pair of eyes.** `CODEOWNERS` names `@harness-owner` etc. — placeholders. 90% of the history is one author. | `CODEOWNERS`; `git shortlog -sn` |
| O5 | **15 legacy ADRs lack the canonical shape**, so the gate reports rather than enforces them. | `node scripts/check-adr-numbers.js` |
| O6 | **Nothing is published.** The package is declarable, not installable. | no PyPI release |
| O7 | **No host interop.** ACP is unimplemented, so Eclipse cannot join a multi-agent session. | no ACP code |
| O8 | **One flaky test** (`test_cancellation_during_retry_still_cancels`) is order-dependent. | fails alone, passes in a suite |

---

## 3. The workstreams

Six workstreams, four waves. Each ends with a gate that must exit zero.

### V1 — Land it, and tag it

> **DONE 2026-10-22.** `main` fast-forwarded to `b3e08d1c`; annotated tag
> `v0.2.0` pushed (`8068674e`); `check:all` passed on the landed tree. O1 and
> O2 are closed. Two things happened that this plan did not anticipate, and
> both are recorded rather than smoothed over: the other stream's `main` had
> diverged from `origin/main` with an inconsistent pair of commits
> (`boot.py` imported `session_watch`, the module lived only on the other
> lineage), and the merge consumed ADR numbers H306–H308, so V1–V6 below
> now reserve **H309–H314**. The other stream's local `main` is behind and
> must `git pull` (their tree had 84 uncommitted files at landing time).

> Closes **O1, O2** · Moves **Ops +0.20** · ADR-H309
> **Priority 1 — one command, and it makes everything else real.**

**Why.** The work is finished, verified, and on a branch nobody else is
using. Until it is on `main` and tagged, none of it counts: an untagged commit
is not a release, and a branch is not a product.

**Work items.**

1. Merge `feature/round-3-harness-parity` into `main` (a fast-forward after the
   last merge; re-merge `main` first if it moved).
2. Push `main` and the branch to `origin`.
3. `git tag -a v0.2.0 -m "<the release note's opening>"` on the merge commit.
4. Push the tag. `docs/releases/` becomes the release index; the next release
   adds `v0.3.0.md`.
5. Tell the other stream to `git pull` — their local `main` is behind.

**Contracts.**

- A tag names a **merged** state. Never a branch, never a dirty tree.
- The release note exists before the tag, and the tag's message comes from it.

**Gates.**

- `git tag -l` contains `v0.2.0`; `git merge-base --is-ancestor v0.2.0 main` is
  true.
- `git status --short` on `main` is empty.
- `npm run check:all` passes **on `main`**, after the merge — not only on the
  branch.

---

### V2 — Shrink it, one merge per release

> Closes **O3** · Moves **Ops +0.10** · ADR-H310
> **Priority 2 — the structural fix, and the only one that is multi-release.**

**Why.** The harness is 375,997 lines. The enforcement is real (a per-module
ratchet and a committed total ceiling), and enforcement is not reduction: a
ceiling that rises twice in one round is a ceiling that is being treated as a
formality. The named duplicates are still there.

**Work items — one per release, in this order.**

1. **The terminal merge.** `terminal/` (5,334 lines: PTY sessions, processes,
   ports) and `code/terminal.py` + `code/terminal_tools.py` (the allow/ask/deny
   classifier and the tools). Target: one terminal subsystem with one policy
   decision path. The tool names stay; the duplicate execution machinery goes.
2. **The execution merge.** `execution/` (17,872) and `code/execution.py` (the
   analysis sandbox). They are not the same thing — one runs *applications*,
   one runs *analysis* — but they overlap in process management and result
   envelopes. Target: one result envelope, one process supervisor.
3. **The git surface.** ~115 `git_*`/`vcs_*` tools against the 8 `command_run`
   classes. Target: one git surface — the closed command table plus the tools
   that express something it cannot.

**Contracts.**

- **Do not merge `browser/` into `computer/`.** Web automation and native
  desktop automation are different domains. They were listed together in the
  Round 3 plan by *size*, not by duplication. Merging them would remove
  capability.
- Every merge keeps a deprecation shim for one release, and a CHANGELOG
  migration note naming what moved.
- A merge must **lower** the total ceiling. A release that raises it is not a
  shrink release.

**Gates.**

- `node scripts/size-budget.js` passes **and** `totalLines` is lower than the
  previous release's.
- `npm run check:all` passes.
- The deprecated names still resolve (a test asserts the shim).

---

### V3 — A second pair of eyes

> Closes **O4, O5, O8** · Moves **Ops +0.10** · ADR-H311
> **Priority 2 — the risk item, and the one that cannot be automated.**

**Why.** 90% of this harness's history is one author, and the harness is the
part of the tree where a mistake is hardest to see: a tool that quietly stops
being reachable, a policy that stops narrowing, a size that grows back. A
`CODEOWNERS` file with placeholder owners does not change that.

**Work items.**

1. **Replace the placeholders** in `CODEOWNERS` with real owners, and enable
   "require review from code owners" on the repository.
2. **Two external reviews** on `python/harness/` — scoped to the policy engine
   (`code/policy.py`, `security/gateway.py`), the tool registry (`tools.py`) and
   the run graph (`graph.py`). Findings become issues, not silent fixes.
3. **Close the 15 legacy ADR shape gaps** — by **re-labelling prose that is
   already there**, never by inventing a rationale. Where an entry genuinely has
   no `Why`, add it to an explicit `EXEMPT` set in `check-adr-numbers.js` with
   the reason "the rationale was never written".
4. **Fix the flaky test.** `test_cancellation_during_retry_still_cancels` is
   order-dependent; make it deterministic or quarantine it with a reason.
5. **The outside re-measurement** (Round 3 §8.8): a reviewer outside this
   repository re-scores the seven dimensions against this document's rubric.
   The result is published, whatever it is.

**Contracts.**

- A review finding is recorded as an issue; it is never fixed silently inside
  the review.
- An ADR is never rewritten to satisfy a linter. Re-labelling existing prose is
  allowed; inventing a rationale is not.
- The re-measured score replaces the estimate **even if it is lower**.

**Gates.**

- `check-adr-numbers.js` reports zero un-exempted legacy entries.
- `CODEOWNERS` has no placeholder owner; branch protection requires code-owner
  review.
- The flaky test is deterministic (fails nowhere) or quarantined with a reason.
- A published re-measurement exists.

---

### V4 — Distribute it

> Closes **O6, O7** · Moves **Ops +0.04** · ADR-H312
> **Priority 4 — reach, not score. Do it after V1–V3.**

**Why.** The harness has a declared public surface, a portable tool manifest
(956 tools) and package metadata. None of it is installable, and Eclipse cannot
join a multi-agent session.

**Work items.**

1. **Publish `black-eclipse-harness`** to PyPI: `python -m build` then
   `twine upload` (needs a credential and the name).
2. **A host plugin** for opencode / Claude Code / Codex that **reads
   `docs/harness/tool-registry.json`** — never a second copy of the schemas.
3. **ACP**, when the specification is available. Until then the manifest is the
   interop surface, and that is stated.

**Contracts.**

- The published package carries no app data, no vault, no credentials (the
  packaging test already asserts it).
- A plugin reads the manifest; it does not restate the tool schemas.

**Gates.**

- `pip install black-eclipse-harness` in a clean venv, then
  `python -c "from harness.public import tool_manifest; print(tool_manifest()['toolCount'])"`.
- An ACP smoke across two hosts (or an explicit "not implemented, here is why").

---

### V5 — The first live number

> Closes **E1, E3, E4** · Moves **Eval +0.03** · ADR-H313
> **Priority 1 for Eval — the only thing that turns `NOT MEASURED` into a number.**

**Why.** The offline tier replaces the model with a recorded script, so
`task_success = 1.0` measures *the runtime*. It says nothing about the agent.
The live lane exists, runs, and has never been run: `docs/harness/benchmarks.md`
publishes `NOT MEASURED` with the reason. A benchmark table with an empty live
row is honest and it is not evidence.

**Work items.**

1. Run `npm run eval:live -- --model <provider>/<model> --limit 12` against a
   real provider. Record the run id.
2. `npm run eval:benchmarks -- --live-run <id>` so the published file carries
   the live tier **with** its dataset checksum, agent version, commit and grader
   version.
3. **Gate the four measured-but-ungated dimensions** from that baseline:
   `cost` (a per-run maximum), `latency` (a per-run maximum), `token_usage` (a
   per-run maximum) and `reliability` (a minimum). The ceilings come from the
   measured number plus headroom — never a guess.
4. Compare live against offline per dimension and publish the delta, with the
   note that the difference is what the model contributes.

**Contracts.**

- A published number is **generated**, carries provenance, and is never
  hand-edited (the drift test already enforces this).
- An unmeasured dimension stays `UNKNOWN`. It never becomes `0`.
- A threshold is derived from a measured baseline, never picked to fit.

**Gates.**

- `docs/harness/benchmarks.md` shows the live tier with a real number and its
  provenance.
- `DEFAULT_THRESHOLDS` includes `cost`, `latency`, `token_usage` and
  `reliability`, each with a description naming the baseline it came from.
- `npm run check:all` passes with the new thresholds.

---

### V6 — An external suite

> Closes **E2** · Moves **Eval +0.02** · ADR-H314
> **Priority 2 for Eval — the only route to a number anyone else can compare.**

**Why.** Nothing in this repository matches `swe.?bench`, Vals or SWE-rebench.
So Eclipse's numbers are its own, and "comparable to a harness that publishes
the same way" is comparable to none. The honest current state is that this
harness has never been measured on a task set it did not write.

**Work items.**

1. **A dataset adapter** — `evaluation/external.py` — that reads the OFFICIAL
   SWE-bench Lite/Verified JSON (or JSONL) and maps it to `EvaluationTask`s. The
   mapping must state what it cannot carry (SWE-bench grades by applying a patch
   and running the repo's tests; Eclipse's graders are its own).
2. **A bounded subset** through the live lane — 20 tasks, published with the
   dataset's checksum and the exact commit of the harness.
3. **Publish the comparison** next to the field's numbers, with the caveat that
   a scaffold difference is part of the score.

**Contracts.**

- The adapter is **graded**, not asserted: if the dataset file is absent, the
  suite reports `NOT MEASURED` with the reason, never a fabricated pass.
- The published row names the external dataset, its checksum and the subset size.

**Gates.**

- `python -m harness.evaluation.report` produces a row whose tasks come from an
  external dataset.
- The dataset file is fetched by a documented command, and its checksum is
  verified before use.

---

## 4. Sequencing and the critical path

```
WAVE A — land it (one session)
  V1  land + tag                                  → +0.20 Ops
        │
        ├──► WAVE B — measure it
        │      V5  the first live number           → +0.03 Eval  (needs a provider key)
        │      V6  an external suite               → +0.02 Eval  (needs the dataset)
        │
        └──► WAVE C — make it trustworthy
               V3  a second pair of eyes           → +0.10 Ops   (needs a human)
               V2  shrink, one merge per release    → +0.10 Ops   (multi-release)
               V4  distribute                       → +0.04 Ops   (needs credentials)
```

**Critical path to 9.5:** `V1 → (V5 + V6) → V3`. That is **0.49 points**:
V1 0.20, V5 0.03, V6 0.02, V3 0.10, V2 0.10, V4 0.04.

**The order is not negotiable in one respect:** **V1 first.** Every other
workstream's "done" claim is measured against a landed, tagged tree. V3's
re-measurement cannot happen on a branch.

**V2 is the only long one.** One merge per release, three releases. It can run
in parallel with V5/V6 because it touches different files.

## 5. What needs YOU — the blocking external inputs

Four workstreams cannot start without something only you can provide. They are
marked so they are never reported as "blocked, unknown".

| Needed by | What | Why it cannot be done here |
|---|---|---|
| **V5** | A **provider key** (`BLACK_ECLIPSE_PROVIDER` + `BLACK_ECLIPSE_API_KEY`, or `--model`) | A live run calls a real model; there is no key in this environment |
| **V6** | **Network access** to fetch the official SWE-bench dataset | The dataset is not in the repo, and inventing one would be a fabricated benchmark |
| **V3** | **A second human** for the reviews and the outside re-measurement | The point of a second pair of eyes is that they are not the first pair |
| **V4** | A **PyPI credential** and a decision on the package name; the **ACP spec** | Publishing is an identity action; ACP from memory would be a claim |

**If you can only unblock one:** the **provider key** (V5). It is the smallest
input and it turns the entire Evaluation dimension from "measured internally" to
"measured".

## 6. Gates

Every workstream ends with the one release gate (`README §3.8`):

```bash
cd Black-Eclipse-site
npm run check:all
```

Plus, per workstream:

| V | Extra gate |
|---|---|
| V1 | **PASSED 2026-10-22** — `v0.2.0` exists locally and on `origin`, points at `b3e08d1c`, which is `origin/main`; `check:all` passed on that tree |
| V2 | `size-budget.js` passes **and** `totalLines` fell |
| V3 | `check-adr-numbers.js` reports zero un-exempted legacy entries; CODEOWNERS has no placeholder |
| V4 | a clean-venv `pip install` then `tool_manifest()['toolCount'] > 0` |
| V5 | `benchmarks.md` carries a live number with provenance; four new thresholds exist |
| V6 | `report.py` emits a row from an external dataset with its checksum |

## 7. Non-goals

Inherits the Round 3 non-goals, plus three:

- **No further work on Loop/Ctx/ACI/Safe/Ext.** They are at 9.5. Effort there
  cannot move the total.
- **No new capability.** V2 removes duplication; it adds nothing.
- **No rewriting history to look tidy.** Legacy ADRs are re-labelled or
  exempted, never rewritten.

## 8. Definition of done

1. `git tag -l` contains `v0.2.0`, and it is an ancestor of `main`.
2. `npm run check:all` passes on `main`.
3. `node scripts/size-budget.js` passes with a `totalLines` **lower** than
   today's 379,756.
4. `node scripts/check-adr-numbers.js` reports zero un-exempted legacy entries.
5. `docs/harness/benchmarks.md` carries a **live** number with dataset checksum,
   agent version, commit and grader version.
6. `DEFAULT_THRESHOLDS` gates `cost`, `latency`, `token_usage` and
   `reliability`, each naming its baseline.
7. `report.py` emits a row from an **external** dataset.
8. An **outside reviewer** has re-measured the scorecard and the result is
   published — **even if it is lower than 9.01**.
9. `pip install black-eclipse-harness` works in a clean venv.

> Point 8 is the only one that can falsify this document. Until it exists,
> **9.01 is the published number** and "9.5" is a target, not a claim.

## 9. Risks

| Risk | Why it is real | Mitigation |
|---|---|---|
| **A live run is expensive and slow** | 68 tasks with a real model; a bad run wastes both | 12-task limit first; the full suite only after the smoke is clean |
| **An external benchmark scores badly** | SWE-bench grades a different shape (patch + repo tests); Eclipse's scaffold is not built for it | Publish the caveat with the number. A low external number is a *measurement*, and the alternative is no number at all |
| **V2 breaks a subsystem nobody measured** | `execution/` and `terminal/` are security-sensitive and lightly covered | One merge per release, deprecation shims, the ratchet must fall, and the full gate between each |
| **The other stream keeps moving `main`** | It committed 33 times during Round 3 | Land V1 promptly; re-merge before each release, never carry a long-lived branch |
| **The outside re-measurement comes back lower** | My rubric is mine | That is the point. Publish it and re-plan from the real number |
| **A second reviewer never materialises** | It needs a human | Until then Ops cannot pass 7.0, and this document says so rather than scoring around it |

## 10. The one-line version

**Land and tag it (V1), get one live number (V5), bring in a second pair of eyes
(V3).** Those three are 0.33 of the 0.49, they need no refactor, and two of them
need only a command and a key. The surface cut (V2) is the honest long game; the
external suite (V6) is the credibility long game.
