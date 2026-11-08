---
title: Graph Studio — Trade Learning Loop (mistake → lesson → recurrence → remediation)
status: Implementing (core shipped)
last-verified: 2026-11-04
---

# Trade Learning Loop — plan

> **Implementation status (2026-11-04).** The core is shipped: the
> `python/harness/trade_learning/` domain (detectors, playbook, walk-forward
> replay, recursive climb, store, conductor), the six `trade.*` graph nodes in
> both registries, the `journal_trades` read-only bridge capability, and the
> Python + TS test suites. `trading.risk_check` now accepts the optional
> `policy` input and applies the learned limits it can enforce statelessly. The
> `Trade learning loop` starter template ships. The Journal "Learning" panel and
> the Tier-1 background tick are the remaining pieces; this document is still the
> design of record.

**The ask, restated precisely.** A node (or small node pack) that:

1. takes a trade that was actually made;
2. decides — honestly — whether it was a mistake;
3. learns a lesson from it;
4. checks whether that class of mistake keeps happening;
5. when it does, changes something and fixes it.

**The short answer.** Steps 1–4 already have most of the required machinery in
this repository, and step 5 has a *deliberately narrow* existing mechanism. The
work is to add a **trade domain** in front of that machinery and to add **one
new, bounded self-modification surface**: an append-only **playbook envelope**
that the risk gate enforces. The loop must never rewrite code autonomously and
must never place or modify an order.

This document is the audit, the design, the contracts, the remediation policy,
the work breakdown and the test matrix.

---

## 1. What already exists (reuse before rebuild)

| Capability | Where it lives | What it gives us | What it does **not** do |
| --- | --- | --- | --- |
| Trade journal | JDDS `Trade`, `TradeExecution`, `TradeFill`, `Strategy`/`StrategyRule`, `Setup`, `Tag`, `MarketContext` (`prisma/schema.prisma`) | entry/exit/stop/target, R, MFE/MAE, emotion, confidence, checklist, free-text `mistakes`, execution log (`stop_modified`, `target_modified`, `partial_exit`) | it is app data; the Python runtime cannot read JDDS directly |
| Journal analytics | `src/lib/journal/analytics/` (`discipline.ts`, `performance.ts`, `psychology.ts`) | a deterministic discipline score and behavioural flags from the `mistakes` JSON | presentation/analytics only — it never creates a lesson |
| Eclipse-executed trades | `python/harness/trade/` (broker/paper ledger on `agent-memory.db`) + `graph_runtime/trading_*_nodes.py` | orders, fills, positions, policy (`trade/policy.py`), reconciliation | no journal view, no lesson pipeline |
| Deterministic mistake detection | `python/harness/eclipse_memory/mistakes.py` | category → severity → evidence records, **no model call** | categories are agent-runtime categories, not trading categories |
| Mistake store | `eclipse_memory/store.py` (`MistakeRecord`) + `service.record_mistake` | durable observation with `expected`/`actual`/`evidence`/`correctiveAction` | keyed to `runId`/`skillId`; no trade subject |
| Recurrence ledger | `persistence.py` (`LearningRecurrence`, `LearningRecurrenceRun`) | the **one** deduped `seenCount` per signature | only counts; knows nothing about trades |
| Lesson contract + quarantine | `self_improvement/lesson_contract.py`, `loop_health.py` | structural signatures, recurrence eligibility, nonconforming quarantine | not wired to trades |
| Candidate → proposal | `code/evolution.py` (`record_mistake_recurrence`, `candidates_from_mistakes`, `RECURRENCE_THRESHOLD = 3`) | mistake category → inert candidate after recurrence, frozen paths, refusal codes | not wired to trades |
| Self-modification Tier B | `self_improvement/self_modification.py` | accept/enable a **read-only learned skill** under caps, TTL, shadow, audit, revoke | never enables effectful skills, never edits code |
| RSL / code evolution | `docs/self-improvement/` (`rsl-*`, `SELF_MODIFICATION.md`) | gated code/proposal pipeline | operator-gated; not a trading loop |
| Graph node contract | `src/lib/graph-studio/{registry,manifest,validation}.ts` + `python/harness/graph_runtime/{registry,nodes,node_packs}.py` | typed ports, config schema, capabilities, side-effect class, modes, cross-language manifest parity | no journal or learning nodes |
| Read-only JDDS bridge | `src/app/api/harness/data/route.ts` + `src/lib/harness/data-bridge*` | whitelisted read capabilities for the runtime | no journal capability yet |
| Paper/live envelopes | `run-authorization.ts`, `compiler.py` | test runs cannot trade/write; operator runs are explicit | — |

**Conclusion.** The learning substrate exists and is conservative by design. The
genuine gaps are:

- **G1** a read path from JDDS journal trades into the runtime;
- **G2** trading-specific deterministic mistake detectors;
- **G3** a trade-scoped recurrence ledger entry and lesson;
- **G4** a bounded remediation surface that can actually change behaviour;
- **G5** the surfaces (node pack, template, Journal panel, docs).

---

## 2. Design principles (non-negotiable)

1. **Outcome is not evidence of a mistake.** A losing trade that followed the
   plan is not a mistake. A winning trade with no stop is still a mistake.
   Every finding must point at a recorded field; nothing is inferred from P&L.
2. **Deterministic first, model second.** Detection, counting, thresholds and
   remediation are pure code. A model may *explain* a finding in prose and, in a
   separate opt-in node, *draft* a lesson. A model never decides that a mistake
   occurred and never chooses the remediation.
3. **One recurrence ledger.** Do not build a second counter. Trade findings use
   `LearningRecurrence` with a `trade:`-namespaced structural signature.
4. **The loop cannot touch money or code.** It may tune a pre-authorized,
   numeric, append-only playbook envelope. It may propose a code/skill change
   through the existing gated pipeline. It may never place, modify or cancel an
   order, and never edit a source file.
5. **Tighten-only is autonomous; loosen always needs a human.** Automatically
   reducing risk is recoverable. Automatically *increasing* risk is not.
6. **No silent writes to what the user owns.** Findings live in the learning
   store. `Trade.mistakes`, tags and notes are changed only by an explicit
   operator action ("Apply to journal").
7. **Simulated is always labelled.** A shadow replay is a counterfactual, not a
   measured result.
8. **Insufficient evidence is a valid answer.** Sparse journal data or a small
   sample returns `insufficient_evidence`, never a guess.

### Non-goals

- No autonomous live trading, no order modification as a remediation.
- No autonomous source-code edits, no tool/permission widening.
- No second journal database, no second agent loop, no second scheduler.
- No rewriting the user's historical `mistakes` tags.
- No claims about missed profit (MFE) unless MFE is actually recorded.

---

## 3. What counts as a "mistake" (the taxonomy)

Each detector names the **field**, the **condition** and the **evidence**. If a
required field is missing (common for manual trades: `mfe`, `mae`,
`riskAmount`), the detector returns `unavailable` for that trade — it does not
guess.

### 3.1 Trade-level detectors

| id | Fires when (all deterministic) | Needs | Journal label |
| --- | --- | --- | --- |
| `no_stop` | closed trade, `stopLoss == null`, entry/exit known | `stopLoss` | `No stop` |
| `risk_over_limit` | `riskAmount > envelope.riskPerTradePct × accountEquity`; fallback when no equity: `riskAmount / (entry × qty) > 0.01` | `riskAmount` (+ equity for the true rule) | `Oversized` |
| `stop_widened` | a `stop_modified` execution moved the stop **away** from entry (risk increased) | `TradeExecution.detail` | `Moved stop` |
| `target_reduced` | a `target_modified` execution moved the take-profit closer to entry before the exit | `TradeExecution.detail` | `Moved target` |
| `early_exit` | `rMultiple < 1` **and** recorded `mfe >= 1` (left ≥1R on the table) | `rMultiple`, `mfe` | `Early exit` |
| `held_past_stop` | recorded `mae <= -1` while a stop was set (stop was not honoured) | `mae`, `stopLoss` | `Held loser` |
| `overtraded` | closed trades on a UTC day `> envelope.maxTradesPerDay` | exit times | `Overtraded` |
| `revenge_trade` | entry within `revengeWindowMin` (default 30) of a losing exit, same symbol, or `emotion == "Revenge"` | times, emotion | `Revenge` |
| `no_plan` | `strategyId == null && setupId == null` | ids | `No plan` |
| `checklist_violation` | `checklist` JSON has `false` for a rule whose `StrategyRule.category` is `risk`/`entry` | `checklist` + rules | `Broke rule` |
| `off_session` | trade session/time outside `envelope.sessionAllowlist` | session/entry time | `Off-session` |
| `off_symbol` | symbol in `envelope.symbolBlocklist` (or not in an allowlist when one is set) | symbol | `Off-plan symbol` |
| `duplicate_entry` | same symbol + direction opened within `duplicateWindowMin` (default 60) while the first was open | entries | `Double entry` |
| `unreviewed` | closed for > `reviewGraceHours` (default 24) with no `grade` and no `notes` | grade/notes | `Unreviewed` |

`chased_entry` is deliberately **not** in v1: it needs the watchlist trigger
(`WatchlistItem.trigger`) and that association is not persisted on the trade.
The taxonomy has room for it once a `plannedEntry` field exists — adding a
detector without the data would be a guess.

### 3.2 Severity and cost

- Severity is fixed per category (mirrors `mistakes._SEVERITY`), `high` for
  unprotected risk (`no_stop`, `risk_over_limit`, `held_past_stop`,
  `checklist_violation`, `revenge_trade`), `medium` for the rest.
- **Cost** for ranking is `sum(|rMultiple|)` over the trades that carried the
  finding — but only when R is available. Otherwise cost is `null` and the
  finding is ranked by count only, visibly marked `rUnavailable`.
- A finding is never deleted. It may be `acknowledged` (the trader accepts it as
  a deliberate exception) or `superseded` (the detector was retired).

### 3.3 Explicit non-mistakes

`loss_within_plan`, `stop_out_as_planned`, `missed_trade`, `low_confidence`,
`small_unplanned_win` are **not** findings. The review output should list how
many trades were judged clean — a review that flags everything teaches nothing.

---

## 4. Architecture — one loop, four stages, no new runtime

```
   journal.trades ──┐
   (JDDS, read-only)│
                    ▼
            [ trade.review ]            pure, deterministic
                    │ findings[]
                    ▼
            [ trade.learn ]             local_write (agent-memory)
              │        │
              │        └──► LearningRecurrence (the ONE ledger)
              │                     │
              │                     ▼
              │            eligible signatures (count ≥ N, cost, coverage)
              ▼                     │
        lesson candidate            ▼
        (lesson_contract)   [ trade.remediate ]   operator / bounded
                                    │
                    ┌───────────────┼────────────────┐
                    ▼               ▼                ▼
             Tier 0 record   Tier 1 playbook    Tier 2 proposal
             (always)        (bounded, revert)  (existing pipeline)
                                    │
                                    ▼
                        trade.playbook ──► trading.risk_check
                        (future orders are gated by the learned envelope)
```

The canvas stays the plan: each stage is a node, nothing is hidden in a
monolith, and every stage is independently testable.

### 4.1 Where state lives

| State | Database | Why |
| --- | --- | --- |
| findings, recurrence, lessons | `agent-memory.db` (runtime-owned) | the loop must read/write them without a bridge; they are derived, not the user's book of record |
| playbook versions | `agent-memory.db` (append-only) | the **Python risk gate** must enforce them at order time |
| journal trades / execution log | JDDS | the user's record of truth; runtime reads through the bridge, never writes |
| applied journal annotations | JDDS, via an explicit front-door route | a user-visible edit; operator-initiated only |

**Why the playbook is not in JDDS.** The Python runtime cannot read JDDS, and the
risk gate runs in Python. Putting the envelope in JDDS would force a bridge read
on every order — a new failure mode at the worst moment. The front door exposes
read routes so the Journal UI can still show it.

---

## 5. Data path — `journal.trades` (G1)

### Decision: one new read capability, not a new database or a run-input blob

Add `journal_trades` to the whitelisted `DataCapability` set
(`src/app/api/harness/data/route.ts`), dispatched by `data-bridge.ts`:

```
params: {
  profileId?: string      // resolved server-side; a caller cannot switch owner
  from?: ISO, to?: ISO
  symbols?: string[]
  setupId?: string, strategyId?: string
  status?: 'closed' | 'open'
  limit?: number          // default 200, max 500
  includeExecutions?: boolean
}
returns: {
  trades: TradePayload[],
  executions: { [tradeId]: ExecutionEvent[] },
  completeness: { trades, withStop, withRisk, withMfeMae, withPlan },
  truncated: boolean,
  provenance: { source: 'jdds', readAt, profileId }
}
```

Rules:

- **Read-only and owner-scoped.** The route resolves the same `JournalProfile`
  ownership the journal pages use (guest vs authenticated). `profileId` in the
  payload is ignored; the server decides.
- **Bounded.** ≤ 500 trades, executions capped per trade (last 20). No notes or
  free text beyond what is needed for `unreviewed`.
- **Never fabricated.** Missing fields are `null`, never `0`.
- **Completeness is returned with the payload** so the loop can refuse to
  learn from a thin sample.

The runtime node `trade.journal` is a thin adapter over the bridge (like
`finance.quote` over `MarketDataGateway`), not a second ingestion path.

> Alternative considered and rejected: pre-resolving trades into the run input
> from the front door. It works for one graph but makes the node non-composable,
> leaks the whole journal into the run record, and cannot be reused by a
> subworkflow.

---

## 6. Node contracts

A new registry module `src/lib/graph-studio/registry-learning.ts` and runtime
module `python/harness/graph_runtime/learning_nodes.py`, registered via
`node_packs.py` (`build_learning_nodes`). New category `learning` (update
`types.ts`, `CATEGORY_LABELS`, `node-icons.ts`). If we want a smaller diff, fold
the category into `trading`; the contracts do not change either way.

Every contract change runs `npm run graph:manifest`; the manifest test and
`test_graph_registry_parity.py` must pass. All four nodes are additive additions
(`type@1.0.0`).

### 6.1 `trade.journal` — load the trades

| | |
| --- | --- |
| category | `learning` |
| side effects | `read` |
| capabilities | `journal.read` |
| modes | all |
| inputs | `trades` (array, optional — if wired, it wins over the bridge) |
| outputs | `trades` (array), `executions` (object), `completeness` (object), `provenance` (object) |
| config | `lookbackDays` (90, 1–3650), `status` (`closed`/`open`/`all`), `symbols` (string), `strategyId` (string), `setupId` (string), `limit` (200, 1–500), `includeExecutions` (true) |

A test run may execute it (`read` side effect). It returns `UNAVAILABLE` with a
reason when the bridge is down — never an empty list pretending there were no
trades.

### 6.2 `trade.review` — detect findings

| | |
| --- | --- |
| category | `learning` |
| side effects | `none` (pure) |
| capabilities | — |
| modes | all |
| inputs | `trades` (array, required), `executions` (object, optional), `playbook` (object, optional) |
| outputs | `findings` (array), `summary` (object), `reviewed` (array), `coverage` (object) |
| config | `detectors` (CSV of ids, default = all), `revengeWindowMin` (30), `duplicateWindowMin` (60), `reviewGraceHours` (24), `maxTradesPerDay` (3), `riskPct` (1.0), `minRForEarlyExit` (1.0), `includeOpen` (false) |

Output shape (per finding):

```json
{
  "tradeId": "…",
  "category": "stop_widened",
  "severity": "high",
  "expected": "stop unchanged or tightened",
  "actual": "stop moved 42.10 → 39.20 (risk +1.8R)",
  "evidence": { "kind": "stop_modified", "at": "…", "from": 42.10, "to": 39.20 },
  "rMultiple": -1.9,
  "rAvailable": true,
  "label": "Moved stop",
  "signature": "trade:stop_widened:symbol:EURUSD",
  "detectorVersion": "1"
}
```

`findings` is the only thing downstream needs. `reviewed` lists clean trades and
the reason they were judged clean.

### 6.3 `trade.learn` — persist, count, draft

| | |
| --- | --- |
| category | `learning` |
| side effects | `local_write` (agent-memory only) |
| capabilities | `learning.write` |
| modes | all (a test run may write to the runtime's own store — same class as `data.dataset.save`) |
| inputs | `findings` (array, required), `trades` (array, optional, for context) |
| outputs | `recorded` (number), `recurring` (array), `candidates` (array), `skipped` (array) |
| config | `minOccurrences` (3, 1–100), `windowDays` (90, 1–3650), `minCostR` (1.0), `minCoverage` (0.8), `draftLessons` (true), `scope` (`auto`/`global`/`symbol`/`setup`/`session`/`strategy`) |

Behaviour:

1. Validate each finding against the detector's declared shape (a malformed
   finding is `skipped`, never silently dropped).
2. Persist a `TradeFinding` row (idempotent on `(tradeId, category, detectorVersion)`).
3. Bump `LearningRecurrence` with the scoped signature, passing **`tradeId` as
   the dedupe identity** so re-reviewing the same trade cannot inflate the count.
4. Compute eligibility: `seenCount >= minOccurrences ∧ within window ∧ costR >=
   minCostR ∨ costUnavailable ∧ coverage >= minCoverage`.
5. For eligible signatures, write a **lesson candidate** through
   `lesson_contract` (structural signature, derived confidence, replay test). A
   candidate is inert; nothing is enabled here.

### 6.4 `trade.remediate` — the bounded fix

| | |
| --- | --- |
| category | `learning` |
| side effects | `write` (runtime store) — **never** `trading` |
| capabilities | `learning.write`, `learning.self_modify` |
| modes | all (no broker access) |
| inputs | `recurring` (array, required), `playbook` (object, optional = current) |
| outputs | `actions` (array), `playbook` (object, new version or unchanged), `rejected` (array), `shadow` (object) |
| config | `mode` (`off`/`shadow`/`tighten`/`full`), `maxActionsPerRun` (3, 1–10), `ttlDays` (14, 1–90), `requireConfirmation` (true), `allowLoosen` (false), `minTradesToJudge` (20) |

It returns **actions**, each with `kind`, `knob`, `from`, `to`, `reason`,
`evidence` (signature + counts), `mode`, `status` (`proposed`/`applied`/
`shadowed`/`rejected`), and `revertAt`. It never contacts a broker and never
edits a file.

### 6.5 `trade.playbook` — read the current envelope

| | |
| --- | --- |
| category | `learning` |
| side effects | `read` |
| capabilities | `learning.read` |
| modes | all |
| inputs | — |
| outputs | `playbook` (object), `versions` (array), `provenance` (object) |
| config | `includeHistory` (false), `limit` (10) |

`trading.risk_check` gains one **optional** input port `policy` (object) and one
optional config `usePolicy` (false). When wired, the risk gate evaluates the
learned envelope in addition to its own config — the learned limits can only
make the gate stricter, never looser than the node's own limits. This is an
additive contract change allowed at `type@version` (ADR-H344).

---

## 7. Storage (agent-memory, idempotent DDL)

### 7.1 `TradeFinding`

```
id, tradeId, profileId, category, severity, detectorVersion,
expected, actual, evidence(JSON), rMultiple, rAvailable,
signature, status(open|acknowledged|superseded), createdAt, updatedAt
UNIQUE (tradeId, category, detectorVersion)
INDEX (signature), (tradeId), (status), (createdAt)
```

A finding is an **observation**. It is not a lesson, a candidate or an action.

### 7.2 `TradePlaybookVersion` (append-only)

```
id, version(int), hash, createdAt, reason, mode,
limits(JSON), bounds(JSON), evidence(JSON), actions(JSON),
status(active|shadow|reverted|expired|rejected),
revertsAt, revertedAt, approvedBy
UNIQUE (version)
```

Rules:

- one active version per owner; a new version is a full snapshot, never a diff;
- `hash` is deterministic over the normalised `limits` so the same envelope is
  never stored twice;
- a version outside `bounds` is refused at write time with a structured code
  (`OUT_OF_BOUNDS`), mirroring `EvolutionRefusal`;
- history is never edited.

### 7.3 Reuse, don't duplicate

- `LearningRecurrence` / `LearningRecurrenceRun` — the one counter.
- `LearningCandidate` — lesson candidates (`sourceCategory = "trade_<id>"`).
- `MistakeRecord` — **not** used for trade findings; its subject is a run/skill
  and adding a polymorphic subject would weaken an existing contract. The bridge
  from trade findings to the evolution pipeline is a candidate, not a second
  mistake table.

---

## 8. The remediation ladder (G4) — what "modifies itself" means

Three tiers, each with an explicit authority boundary.

### Tier 0 — Record (autonomous, no behaviour change)

- Persist findings, recurrence, lesson candidate.
- Return a plain-language review to the run (`findings`, `summary`).
- Optionally notify (`output.notify`) or publish a report (`output.chart`).
- Never edits the journal. A separate, explicit operator action applies a
  finding to `Trade.mistakes`.

**Authority:** none. Reversible by deleting derived rows.

### Tier 1 — Tune the playbook (autonomous **tighten-only**, bounded)

The envelope contains numeric/lists knobs the operator pre-authorized **with
bounds** at playbook creation:

| knob | direction | autonomous change |
| --- | --- | --- |
| `riskPerTradePct` | lower is tighter | decrease only |
| `maxTradesPerDay` | lower is tighter | decrease only |
| `maxConsecutiveLosses` | lower is tighter | decrease only |
| `requireStop` | `true` is tighter | set true only |
| `sessionAllowlist` | narrower is tighter | remove only |
| `symbolBlocklist` | longer is tighter | add only |
| `suspendedStrategies` | longer is tighter | add only |

Rules:

1. **One knob per recurring signature per cycle**, and at most
   `maxActionsPerRun` per run.
2. **Never outside `bounds`.** The bounds were set by the operator, not the loop.
3. **Step limit.** One step per change (e.g. `riskPerTradePct` 1.0 → 0.75, never
   straight to the bound).
4. **Shadow first.** When a new finding class appears, the first cycle runs in
   `shadow` and records what it *would* change.
5. **Cooldown.** No further change to the same knob until
   `max(ttlDays, 20 closed trades)` has elapsed, so a tight stop cannot cause a
   cascade of "fixes".
6. **Auto-revert.** On expiry, or when the next window shows the category did
   not improve **or** a new high-severity category appeared, revert to the
   previous version and record `reverted`.
7. **Loosening is a proposal.** Any change that widens risk (higher risk %,
   more trades, `requireStop: false`, removing a block) is `status: proposed`
   and needs an operator accept, regardless of `mode: full`.
8. **Suspension needs confirmation by default.** Disabling a whole strategy is
   high-impact: `requireConfirmation: true` makes it a proposal even in `full`
   mode.

**Enforcement point.** `trading.risk_check` with the `policy` input wired. The
learning loop never touches the broker, so a compromised loop can at worst
over-tighten risk — it cannot trade.

### Tier 2 — Propose a code/skill change (operator-gated, existing pipeline)

For a recurring mistake that cannot be expressed as a numeric knob (e.g. a
detector that keeps firing because a field is never populated, or a strategy
rule that is structurally wrong):

- Create a `LearningCandidate` with the structural signature and evidence.
- The existing `code/evolution.py` candidate → evaluate → activate pipeline
  decides. Frozen paths and forbidden fields apply unchanged.
- `self_improvement/self_modification.py` may accept/enable a **read-only**
  learned skill under its caps, TTL, shadow and audit. It may not enable an
  effectful skill.
- Nothing in this phase is automatic. It is a proposal a human can act on.

### The autonomy setting (one switch, visible)

| `HARNESS_TRADE_LEARNING` | Tier 0 | Tier 1 tighten | Tier 1 loosen/suspend | Tier 2 |
| --- | --- | --- | --- | --- |
| `off` | no | no | no | no |
| `record` | yes | no | no | no |
| `shadow` (default) | yes | records only | proposal | proposal |
| `tighten` | yes | yes (bounded) | proposal | proposal |
| `full` | yes | yes | confirm | proposal |

`off`/`record`/`shadow` must be usable without any operator setup — zero-config
safe default. A kill switch (`POST /learning/trade/pause`) stops all Tier 1
actions immediately, like `self_modification/pause`.

---

## 9. Recurrence engine (G3) — "is this happening regularly?"

### Signature

```
signature = sha256("trade|<category>|<scope>")[:32]
scope     = global | symbol:<S> | setup:<id> | session:<S> | strategy:<id>
```

`scope` is chosen **per category** (data, not code):

| category | scope |
| --- | --- |
| `no_stop`, `no_plan`, `unreviewed` | global (a process failure is not symbol-specific) |
| `stop_widened`, `held_past_stop`, `early_exit` | `symbol:<S>` |
| `revenge_trade`, `duplicate_entry` | global |
| `overtraded` | global |
| `off_session`, `off_symbol` | global |
| `risk_over_limit`, `checklist_violation` | `strategy:<id>` when known, else global |

The signature never contains a trade id, a timestamp, a price or a note.

### Eligibility (all must hold)

1. `seenCount >= minOccurrences` (default 3; never 1, even for one large loss).
2. `lastSeenAt` within `windowDays` (default 90) and at least one occurrence in
   the most recent 50 closed trades (so an ancient habit is not "fixed" today).
3. **Data coverage:** the fields the findings depend on are present for
   `>= minCoverage` (default 80%) of the trades in the window. Below that the
   result is `insufficient_evidence`.
4. **Cost gate:** `sum(|rMultiple|) >= minCostR` when R is available. A frequent
   but costless habit is ranked lower, not hidden — the output shows
   `costRank` and `rUnavailable`.

### Ranking

`priority = count × meanCostR` (or `count` when R is unavailable), then
severity. The output carries the components so a user can disagree with the
ranking.

### Honest labels

`eligible` · `not_yet` (count below threshold) · `stale` (last seen too long
ago) · `insufficient_evidence` (coverage/cost) · `acknowledged` (user accepted
it as deliberate). No silent "no problems".

### Anti-double-count

- `(tradeId, category, detectorVersion)` is unique in `TradeFinding`.
- `LearningRecurrenceRun(runId, signature)` is keyed by `tradeId`, so
  re-reviewing the same trade returns the same count.

---

## 10. Safety, audit and reversibility

| Control | Implementation |
| --- | --- |
| No trading side effect | `trade.remediate` declares `write` + `learning.self_modify`, never `trading`; the compiler's envelope refuses it in a live trading context only in the sense that it cannot touch a broker — it simply has no broker code path |
| No code edits | trade nodes import no `code/*` module; the only code path is a *candidate*, not a patch |
| Frozen authority | playbook `bounds` are operator-owned; the loop may never write them |
| Audit | every action is a `TradePlaybookVersion` + an action row with reason, evidence, actor (`loop`/`operator`), and before/after |
| Revoke | `POST /learning/trade/revoke/{versionId}` reverts immediately; the kill switch pauses all Tier 1 |
| Shadow | `shadow` records `shadow_*` actions and changes nothing |
| Expiry | `revertsAt` is mandatory for an applied action |
| Canary | on every tick, an active version whose evidence signature is now `acknowledged` or whose window regressed is reverted |
| Test-run | a test run cannot apply Tier 1 (it is a `write` side effect); it can review and learn locally |
| Ownership | the bridge and the store are owner-scoped; a run cannot read another profile's trades |
| Determinism | same trades + same playbook ⇒ same findings (tested) |

---

## 11. Graph recipes (what the user actually wires)

### 11.1 `Trade learning loop` (template)

```
trigger.schedule (daily 22:00, after the close)
  → trade.journal (last 90 days, closed)
  → trade.review  (all detectors)
  → trade.learn   (min 3 occurrences, 90-day window)
  → trade.playbook (current envelope)
  → trade.remediate (mode: from the autonomy setting)
  → output.notify (only when actions were applied or proposed)
```

### 11.2 `Review one trade` (on demand)

```
trigger.manual → trade.journal (symbol + limit 1) → trade.review → output.notify
```

`trade.learn` is optional here: a single trade never meets the recurrence gate,
so the value is the deterministic findings plus a lesson *draft*, not a fix.

### 11.3 `Risk gate with learning` (future orders)

```
trading.order_intent → trade.playbook → trading.risk_check (policy wired) → trading.paper_order
```

The learned envelope can only make the gate stricter than the node's own limits.

---

## 12. Surfaces (G5)

- **Journal → Learning** panel (new tab beside Insights/Playbook):
  findings by trade, recurring signatures with `count`, `costR`, `eligibility`
  and a one-line explanation, the lesson drafts, and the playbook version
  history with a **diff** and **Revert**. Frosted glass per the UI skill.
- **Trade detail → Review** block: deterministic findings for that trade with an
  **Add to journal mistakes** button (writes `Trade.mistakes` through the
  existing journal route, operator action).
- **Graph Studio**: the five nodes in the `learning` category, the template, and
  a node subtitle that says what it does.
- **Health/runs**: the existing graph run inspector shows inputs/outputs; no new
  panel needed.

---

## 13. Work breakdown

| Wave | Scope | Files (primary) | Effort |
| --- | --- | --- | --- |
| **0 — data path** | `journal_trades` capability, ownership, bounds, `trade.journal` node, parity | `src/app/api/harness/data/route.ts`, `src/lib/harness/data-bridge*.ts`, `python/harness/graph_runtime/learning_nodes.py`, `registry-learning.ts`, `node_packs.py`, `registry.manifest.json` | 2–3 d |
| **1 — detect** | `trade.review` + all detectors + golden fixtures + `TradeFinding` schema | `learning_nodes.py`, `src/lib/graph-studio/registry-learning.ts`, `eclipse_memory/schema.py`, tests | 4–5 d |
| **2 — learn** | `trade.learn`, recurrence bridge, candidate drafting, eligibility report | `learning_nodes.py`, `skills/learning.py` (reuse), `persistence.py` (no change), `eclipse_memory/*`, tests | 4 d |
| **3 — remediate** | `TradePlaybookVersion`, `trade.playbook`, `trade.remediate`, shadow replay, revert, `risk_check` policy input | `learning_nodes.py`, `eclipse_memory/*`, `graph_runtime/trading_nodes.py`, `registry-trading.ts`, manifest | 5–6 d |
| **4 — surfaces & docs** | template, Journal Learning panel, trade-detail review, docs, ADR | `templates.ts`, `src/components/journal/learning.tsx`, `journal-screen.tsx`, `trade-detail.tsx`, `docs/*` | 3–4 d |

Total ≈ 18–22 focused days. Waves 0–2 deliver steps 1–4 (the honest part) and
are independently useful. Wave 3 is the only behaviour-changing part and should
ship behind `shadow` by default.

---

## 14. Test matrix

| Area | Test |
| --- | --- |
| Detectors | one fixture per category: fires with the exact evidence; a clean trade produces no finding; a missing field yields `unavailable`, not a guess |
| Non-mistakes | a planned stop-out and a planned loss produce zero findings |
| Determinism | same payload twice ⇒ byte-identical findings |
| Recurrence | 2 occurrences ⇒ `not_yet`; 3 ⇒ eligible; the same trade reviewed twice does not increment; a stale series ⇒ `stale` |
| Coverage | 6/10 trades missing `mfe` ⇒ `insufficient_evidence` for `early_exit` |
| Scoping | `stop_widened` on EURUSD and GBPUSD stays separate; `no_stop` is global |
| Playbook | tighten-only applies; a loosen is a proposal; out-of-bounds is refused; expiry reverts; a regression reverts; kill switch blocks |
| Shadow | `shadow` records and changes nothing |
| Authority | the node has no broker path; a test run cannot apply Tier 1; the playbook cannot widen risk autonomously |
| Contract parity | manifest test + `test_graph_registry_parity.py` |
| Ownership | a run for profile A cannot read profile B's trades |
| Bridge | bridge down ⇒ `UNAVAILABLE`, not an empty list; > 500 trades ⇒ `truncated: true` |
| Graph | the template validates; `Trade learning loop` runs end-to-end on fixtures |
| Regression | `npm run test`, `npx tsc --noEmit` |

---

## 15. Acceptance criteria

1. Given a window of journal trades, the loop names each mistake with a field
   citation, and names the trades it judged clean.
2. The same mistake class observed ≥3 times in the window becomes **eligible**;
   one occurrence never does.
3. A recurring `stop_widened` produces a playbook version that tightens the
   relevant knob — visible in history with a diff, expires, and reverts on
   regression.
4. A test run cannot apply a change; a shadow run changes nothing.
5. The loop never places, modifies or cancels an order and never edits a source
   file.
6. Every number shown is measured or explicitly `UNAVAILABLE`/`simulated`.
7. `npm run test` and `npx tsc --noEmit` pass.

---

## 16. Risks and mitigations

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| **Thin journal** | manual trades often lack `mfe`/`mae`/`riskAmount` | coverage gate; `unavailable` instead of inference; the Learning panel shows coverage |
| **Overfitting to noise** | 3 occurrences can be luck | recurrence window + cost gate + `minTradesToJudge`; shadow before apply; label the result as a hypothesis |
| **Feedback cascade** | tightening a stop causes more stop-outs, which look like a new mistake | one knob per cycle, step limit, cooldown, auto-revert |
| **Wrong lesson from a correct process** | a loss that followed the plan | outcome ≠ mistake; clean-trade list; `acknowledged` findings |
| **Polluting the user's record** | auto-writing `Trade.mistakes` | never auto-write; explicit "Apply to journal" |
| **Duplicated learning** | two counters, two lesson systems | reuse `LearningRecurrence`, `LearningCandidate`, `lesson_contract`; namespace `trade_<id>` |
| **Live-trading blast radius** | a "fix" that changes risk while live | no broker path in the loop; risk gate only; suspend is confirm-only; kill switch |
| **Owner/privacy leak** | journal is personal | bridge enforces ownership; bounded payload; no notes in the runtime |
| **Contract drift** | TS and Python registries diverge | manifest generation + parity test in CI |
| **Scope creep into code** | "self-modifying" becomes "self-editing" | Tier 2 is a proposal into the existing gated pipeline; frozen paths unchanged |

---

## 17. Open questions for the owner

1. **Default autonomy.** `shadow` (recommended) or `tighten` out of the box?
2. **Journal scope.** Owner-scoped profile only, or all profiles the user owns?
3. **Suspension.** May a recurring, statistically-negative strategy be suspended
   automatically in `full` mode, or always require confirmation?
4. **Explanations.** Is a model-written prose explanation wanted (a separate
   `agent.*` node) or is the deterministic one-liner enough?
5. **Live.** Should the learned envelope apply to live `trading.broker_*` too
   (recommended yes, tighten-only), or paper only for one release?

---

## 18. Documentation and ADR

When implemented:

- `docs/graph-studio.md` — new node pack + template.
- `docs/trading.md` — the playbook envelope and the risk-gate consumption.
- `docs/journal-broker-sync.md` — the read capability (read-only, bounded).
- `docs/NAVIGATION.md` — a row for "work on the trade learning loop".
- `docs/self-improvement/SELF_MODIFICATION.md` — the trade Tier 1 boundary.
- **ADR-069** (app): *Trade learning may tighten a pre-authorized playbook
  envelope and propose, never widen or trade.* Mirror into `docs/DECISIONS.md`
  and `skills/ARCHITECT.md`.
- `docs/CHANGELOG.md` — one entry per wave.

**Status:** proposed, not implemented. No production behaviour changes with
this document.
