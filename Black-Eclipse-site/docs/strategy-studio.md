---
title: Strategy Studio — the guided quant workspace
status: Current
last-verified: 2026-11-10
---

# Strategy Studio

**Who this is for:** anyone changing the `strategy-studio` tab, the workspace
persistence, the data preflight, or the shared quant result components.

This doc explains **intent and invariants**, not the code. The engine itself is
documented in `docs/quant-engine.md` and audited in
`docs/backtesting-engine.md`; this surface is a client over it.

## The job

A user arrives with an idea in plain English and should leave with a strategy
that has been **tested, graded and tracked** — without writing JSON and without
losing their work. The Studio is therefore a *workspace*, not a form:

```
Idea  →  Spec  →  Test  →  Prove  →  Track
```

`StageRail` shows those five stages and the next action. The rail is a claim
about the evidence, not decoration: an idea is not a strategy, a backtest is not
proof, and paper is not live.

## Studio vs Backtest (two surfaces, one engine)

- **Strategy Studio** (`strategy-studio`) — guided authoring, persistence, one
  strategy's history, robustness, paper. Optimised for a user who wants an
  answer.
- **Backtest** (`backtest`) — the expert bench: raw spec editor, any saved
  strategy, experiments, research controls. Optimised for someone who already
  knows the DSL.

They must not drift. Charts, metric tiles and the trade table live once in
`src/components/screens/backtest/shared/` and both screens import them. A new
result panel belongs there, not in either screen.

## What persists

`src/lib/strategy-studio/workspace.ts` is the only definition of the saved
workspace (schema-versioned, `localStorage`, key
`eclipse.strategy-studio.workspace.v1`). It stores the thesis text, the spec
draft, the bound strategy id/name, symbol/timeframe/window/capital, and the last
experiment id. Invariants:

- A corrupt or stale blob is **discarded**, never surfaced as an error.
- A stored **draft** is never clobbered by reopening its saved strategy. On boot
  the editor is replaced only when there is no draft or the deep link explicitly
  named a strategy.
- The address bar mirrors the workspace as
  `?tab=strategy-studio&strategy=<id>&experiment=<id>`, so a reload, a share and
  a "open in new tab" all land back in the same place.
- Persistence is paused while the boot restore is in flight, so a slow strategy
  load cannot write a `null` binding over a real one.

The strategy itself is **not** stored in the browser: the Python quant store owns
strategy versions and experiments. The workspace only remembers which ones the
user was looking at.

## Data preflight

`src/lib/strategy-studio/preflight.ts` matches the requested symbols and
interval against the stored-series catalogue (`GET
/api/research-data/series`). It answers **before** a run. Two honesty rules:

1. Absence from the stored catalogue is reported as "not stored", never as "no
   such data" — the engine may still fetch it from a configured provider.
2. An unreadable catalogue is `unknown`, not `missing`.

Symbols are compared after normalisation (`BTC/USD`, `btc-usd` and `BTCUSD` are
the same instrument), and when the interval is missing the panel names the
intervals that *are* stored.

## Runs, history and comparison

Every save-and-run writes an immutable strategy version and a saved experiment.
The Studio then lists that strategy's experiments and can compare 2–4 of them
through `/quant/compare`; the runtime's comparability cautions are shown rather
than hidden.

Inline validation is a convenience: the spec validates after a pause in either
view, but the **Validate** button remains the explicit authority. A validation
issue's `path` is copyable so it can be found in the JSON.

## Robustness without JSON

`src/lib/strategy-studio/param-space.ts` derives the tunable axes from the spec
it already has (numeric indicator params, sizing, stop/target values, a few risk
limits). Those are exactly the dotted paths `quant/params.py` already accepts; a
user edits min/max/step and the panel builds `paramSpace` / `paramRanges`.

Invariants:

- **Every axis is opt-in.** The panel proposes all of them selected, but none is
  tuned unless its box is ticked.
- **No hidden thresholds.** The verdict page prints each threshold in the
  check's own label (e.g. “Simulated probability of ruin is below 5%”).
- **A partial suite is inconclusive.** `summarizeResearch` returns `robust` only
  when walk-forward, Monte-Carlo *and* robustness all ran and every scored check
  passed. Any failure is `fragile`; anything else is `inconclusive`.
- **`info` rows are never scored.** Worst simulated drawdown and probability of a
  losing run are reported because they are useful, not because they are pass/fail.
- **The one-button suite** runs walk-forward → Monte-Carlo → robustness through
  the existing `bt.runResearch`, one runtime run at a time.

The Edge Report is rendered by the shared `EdgeReportView` (also used by the
Backtest bench): grade, axes, flags as “flags to clear”, the figures from the
Artifact Center, and the durable markdown document. The browser computes nothing.

The plan itself can be loaded from the runtime
(`POST /strategies/{id}/research-plan`): the hypothesis, assumptions, acceptance
criteria and potential biases. The suite is then run against a stated plan rather
than a vibe — but the plan is a specification, never evidence.

Templates (`src/lib/strategy-studio/templates.ts`) are complete, valid specs to
start from. The UI labels them explicitly as examples, not recommendations.

## Method discovery

`MethodDiscoveryPanel` sits above the spec editor and is the front of the
funnel, not a shortcut past the evidence:

- **Recommend** ranks method families for the chosen asset, horizon, objective,
  risk and series. Every fit score prints its reasons and warnings; a
  recommendation is a prior, not an edge.
- **Scan this series** runs the descriptive diagnostics (trend/reversion/
  volatility clustering/seasonality) and names candidate families.
- **Setups now** evaluates the entry rule on the latest closed bar. A setup is a
  condition, not an order or a recommendation.
- **Mine candidates** runs a bounded IS/OOS search, shows the real trial count
  and the Deflated Sharpe, and labels every result `candidate | weak | rejected`.
- **Use spec** synthesizes a valid spec into the editor. Methods that are not
  single-asset rule strategies show their `requires` instead of being forced
  into the DSL.

`ResearchJournalPanel` is the session record: create a program, pre-register a
hypothesis and its acceptance rule, record the current experiment as a trial,
and see the open/rejected ideas. `PortfolioStressLab` is the expert surface for
VaR/ES and scenario P&L from a covariance matrix or scenario map; it refuses
missing inputs instead of assuming them. `ManifestPanel` (shared with the
Backtest bench) shows the run digest and can reproduce the experiment.

## Authoring without JSON

The spec card has two views over the same text: **Builder** and **JSON**
(`src/components/screens/strategy-studio/spec-card.tsx`). The builder
(`spec-builder.tsx`) is a view over `src/lib/strategy-studio/spec-edit.ts`, whose
functions deep-clone the spec and return a new one. Invariants:

- **JSON is authoritative.** The builder writes a new JSON string back; the
  editor remains the escape hatch.
- **Unknown fields survive.** A template, a hand-written spec or a field the
  builder does not render is preserved by a round-trip.
- **The builder refuses what it cannot represent.** An expression operand is
  marked `advanced` and shown read-only with a pointer to the JSON tab. Nested
  groups ARE editable (`rule-tree.tsx`, recursive), but nesting deeper than three
  levels is JSON-only. A group is never silently flattened into a condition.
- **Condition refs are constrained** to price fields plus declared indicator ids,
  so the builder cannot invent a reference the engine will reject.

## Versions, export and publishing

Strategy versions are immutable and content-hashed by the runtime. The
`VersionPanel` lists them, shows the **structural diff** between two
(`/quant/strategies/{id}/diff`) and exports the portable bundle as JSON
(`format=json`). It does not invent versioning logic.

A **graded** strategy can be published into the local gallery
(`PublishButton` → `POST /api/harness/gallery`). The grade, the summary and the
report travel with the frozen spec. The gallery is a local catalogue — not a
marketplace of anonymous signals.

## Paper semantics

Paper has two explicit modes (`src/lib/strategy-studio/paper-window.ts`):

- **forward** — starts the day after the research window ends and runs to today;
- **replay** — the research window itself, labelled as a replay and *not*
  forward-looking.

A forward window that would start after today is **refused**, never silently
downgraded to a replay. The panel shows the exact dates and day count before the
button is enabled.

Each deployment still goes through the governed approval/deployment path and
records a real backtest; it places no orders. The **track record** lists every
paper run with its window and its drift against the latest *backtest* (never
against another paper run). Δ is shown **per metric** (paper minus research) and
is descriptive, not a significance test; return, Sharpe and drawdown are not
averaged into one score because they are different units.

A **health badge** (`src/lib/strategy-studio/paper-health.ts`) says whether the
record still means anything: `stale` after 30 days, `drifting` when the latest
run differs from the research window by ≥10 return points or ≥0.5 Sharpe. Both
thresholds are printed in the badge's detail — it is not a hidden score, and it
does not page anyone.

The approval trail records the request as `strategy-studio` and the decision as
`operator`, so a single-operator workspace still shows two actors instead of an
approval that approves itself. Live routing is refused by the engine
(`LIVE_TRADING_DISABLED`) and is not offered here.

## Where it connects

- **Projects** — `ProjectLink` attaches the current strategy to a project
  (`kind: "strategy"`, `ref: strategy.id`) through the runtime's project store.
  A project is the named scope for one piece of work; the studio does not
  duplicate it.
- **Dashboard** — the `strategy-studio` widget lists saved strategies newest
  first, shows the grade a published version earned (joined from the local
  gallery), and links each to `?tab=strategy-studio&strategy=<id>`.
- **Share** — the header copies the exact workspace link, including the active
  experiment. The `ShareCard` renders the same summary as Markdown (identity,
  window, metrics, grade, paper state, disclaimer) so it can be pasted anywhere.
  It is a local deep link, not a hosted read-only page.
- **Portfolio** — `PortfolioPanel` runs two or more SAVED strategies together
  through `/quant/portfolio-backtest`. They must share one primary timeframe;
  the result is the same artifact the single-strategy panels render, saved as a
  `portfolio_backtest` experiment. It is a portfolio of strategies, not a basket
  of symbols for one strategy.
- **Mobile** — under `md`, a read-only `CompactSummary` (name, three metrics,
  grade, paper state) sits under the stage rail; the full workspace remains
  available below it.

## Files

| Concern | File |
|---|---|
| Screen | `src/components/screens/strategy-studio/strategy-studio-screen.tsx` |
| Header (share / refresh) | `.../studio-header.tsx` |
| Sidebar (library, thesis, data, project) | `.../studio-sidebar.tsx` |
| Error / notice banners | `.../studio-alerts.tsx` |
| Stage rail | `.../stage-rail.tsx` |
| Saved-strategy rail | `.../strategy-library.tsx` |

The rail reads the shared **strategy catalog** (`src/lib/strategies/catalog.ts`,
`GET /quant/strategies?includeEvidence=true`): every strategy with its newest
backtest, approval and paper run. It refreshes on focus, when the tab becomes
visible, after an agent turn completes, and on the explicit Refresh button; it
can show archived strategies. A strategy created in chat therefore appears here
without a reload, and the same catalog feeds the New-bot strategy picker.
| Thesis + run inputs | `.../thesis-panel.tsx` |
| Spec card (builder / JSON) | `.../spec-card.tsx` |
| No-code builder | `.../spec-builder.tsx` |
| Recursive rule editor | `.../rule-tree.tsx` |
| Experiment list + compare | `.../experiment-history.tsx` |
| Data preflight card | `.../data-preflight.tsx` |
| Results (metrics, curves, trades) | `.../result-panels.tsx` |
| Robustness suite + parameter table | `.../research-studio.tsx` |
| Paper deployment + track record | `.../paper-panel.tsx` |
| Versions, diff, export | `.../version-panel.tsx` |
| Publish to gallery | `.../publish-button.tsx` |
| Method discovery | `.../method-discovery-panel.tsx` |
| Research journal / trial ledger | `.../research-journal-panel.tsx` |
| Portfolio stress lab | `.../portfolio-stress-lab.tsx` |
| Run manifest / reproduce | `src/components/screens/backtest/shared/manifest-panel.tsx` |
| Project binding | `.../project-link.tsx` |
| Share card | `.../share-card.tsx` |
| Portfolio backtest | `.../portfolio-panel.tsx` |
| Compact (small-screen) summary | `.../compact-summary.tsx` |
| Dashboard widget | `src/lib/dashboard/strategy-studio-widget.tsx` |
| Workspace schema + deep link | `src/lib/strategy-studio/workspace.ts` |
| Coverage matching | `src/lib/strategy-studio/preflight.ts` |
| Parameter axis derivation | `src/lib/strategy-studio/param-space.ts` |
| Suite verdict | `src/lib/strategy-studio/research-verdict.ts` |
| Spec editing (builder model) | `src/lib/strategy-studio/spec-edit.ts` |
| Paper window math | `src/lib/strategy-studio/paper-window.ts` |
| Paper health (stale / drift) | `src/lib/strategy-studio/paper-health.ts` |
| Gallery publish client | `src/lib/strategy-studio/gallery-client.ts` |
| Share-card Markdown | `src/lib/strategy-studio/share-card.ts` |
| Starter templates | `src/lib/strategy-studio/templates.ts` |
| Shared quant UI | `src/components/screens/backtest/shared/{charts,metric-grid,trade-table,edge-report-view}.tsx` |

## Not claimed

- Paper runs are recorded backtests over a chosen window. They do not place
  orders, do not stream live prices, and are not a broker connection.
- The builder edits rules as a recursive tree. Expression operands and nesting
  deeper than three levels are read-only there and must be edited in JSON.
- The portfolio backtest composes SAVED strategies. A basket of symbols for one
  strategy is not a portfolio in this surface.
- Paper re-runs are manual; there is no scheduler creating them.
- Drift/staleness is a badge in the studio, not a push notification or alert
  rule.
- The share link opens this local workspace; there is no hosted read-only page.
