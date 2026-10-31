---
title: Interactive Response Engine
status: Current
last-verified: 2026-10-22
---

# Interactive Response Engine

**Who this is for:** anyone changing how an assistant answer is presented as
tables, metrics, charts, diagrams, timelines or citations — and anyone wondering
why structured responses arrive the way they do.

This is the *human* explanation. The code is authoritative for exact shapes:
`src/lib/response/` (contract + parsers) and `src/components/response/`
(renderers).

---

## 1. The problem it solves

Until now every assistant turn was **plain Markdown**. The one structured detail
the stream carried was a retrieval object count. So metric cards, charts, tables
and diagrams could not be rendered — `docs/chat-ui-audit.md` (Phase 4, §16,
Risk R7) deliberately refused to fabricate them because there was no wire
contract to back them.

The Interactive Response Engine closes that gap **without a second chat stack**.

## 2. How an answer becomes structured

The agent/model may append ONE fenced code block whose info string is
`eclipse-response`:

````text
The 90-day comparison is driven by realized volatility, not price level.

```eclipse-response
{
  "schemaVersion": "1.0",
  "title": "BTC vs ETH — 90 days",
  "blocks": [
    { "type": "markdown", "markdown": "BTC led on absolute return; ETH on risk-adjusted." },
    { "type": "metric_grid", "metrics": [
      { "label": "BTC return", "value": 12.4, "unit": "%", "delta": 12.4 },
      { "label": "ETH return", "value": 8.1, "unit": "%" }
    ] },
    { "type": "chart", "chartType": "line", "categories": ["d1","d2","d3"],
      "series": [ { "name": "BTC", "data": [1, 2, 3] }, { "name": "ETH", "data": [1, 1.5, 2.2] } ],
      "source": "JDDs daily close", "asOf": "2026-10-09" },
    { "type": "citations", "sources": [ { "title": "…", "url": "https://…", "source": "…" } ] }
  ]
}
```
````

Everything outside the fence stays ordinary Markdown. The fence is stored
verbatim in `Message.content`, so **persistence, reopening and export are the
existing message pipeline** — no new artifact store is needed for inline answers.

### Why a fenced block and not a new stream event

- No Python protocol change, so the agent loop, tool registry and model adapter
  are untouched (AGENTS.md: never rebuild the agent loop in TypeScript).
- Works unchanged in **both** chat surfaces (full page + floating dock) because
  both render through the same `Markdown` component.
- The fence is just text: it persists, copies, and reopens with the message.
- It can only ever produce **validated, registered components** — never code.

Structured output is **optional and conditional**: the prompt instructs the agent
to use it only when it materially improves comprehension, and to keep every
number identical to its prose and grounded in real tool results.

## 3. The contract (`src/lib/response/contract.ts`)

A versioned zod schema. Current version: **1.0** (`RESPONSE_SCHEMA_VERSION`).

Envelope: `schemaVersion?`, `responseId?`, `responseType?`, `title?`, `summary?`,
`blocks[]`, `metadata?`.

### Validation rules (non-negotiable)

1. **The envelope is validated loosely** (unknown fields stripped) so a newer
   producer never bricks an older renderer.
2. **Every block is validated individually.** One bad block never discards the
   rest of the answer.
3. **A rejected block degrades to readable content, never a user-visible error.**
   The render chokepoint (`finalize.ts`) replaces any block the contract rejected
   with a `markdown` block carrying the block's REAL content — its prose/title, or
   a JSON code fence of its structure — so a wrong block costs its *visual*, never
   the answer. The original failure is retained on `response.diagnostics` and
   surfaced through the `degraded` telemetry records; it is never rendered as an
   error card. Unknown block types are thus preserved, not executed.
4. **Hard limits** are enforced at parse (`RESPONSE_LIMITS`): blocks 80, nested
   depth 4, series 24, points/series 5000, table rows 2000, columns 40, metrics
   60, sources 100, diagram nodes 120, edges 300, timeline events 200, tabs 12,
   string length 20 000, and free-form `metadata` 40 keys / 20 000 chars. An
   over-limit `metadata` object is **dropped, not fatal** (`.catch(undefined)`) —
   losing producer bookkeeping must never cost the user the answer.
5. **Version handling.** Missing → 1.0. A newer *major* renders best-effort with
   a `SCHEMA_VERSION_FUTURE` warning. An unparsable version warns and falls back
   to 1.0.

`parseResponsePayload(value)` is total — malformed input yields a
diagnostic-backed empty response, never a throw. It is the *low-level* total
parser: its per-block diagnostics feed the pre-send validation tool and telemetry.
The **render path** runs everything through `finalize.ts` first —
`finalizeResponse(raw)` / `finalizeParsed(response)` / `finalizeFenceSource(source)`
— so the invariant holds: **the renderer is a total function from any input to a
proper render, with no user-visible error state.** For a rejected block the
chokepoint runs, in order:

1. **Repair** (`repair.ts`, driven by `schema-meta.ts`). One deterministic,
   schema-directed attempt to make the block valid so it renders as its intended
   visual. It is generic, not a list of special cases: a missing required field is
   rescued from a same-kind sibling (`title`→`name`, `datasets`→`series`,
   `headline`→`title`); an off enum value is aliased or nearest-matched
   (`bars`→`bar`, `vertical`→`TB`); a single value where an array is required is
   wrapped; an object/array mismatch is unwrapped; a coercible scalar
   (`"true"`, `"12.4"`) is coerced. `schema-meta.ts` is introspected LIVE from
   `ResponseBlockSchema`, so repair tracks the contract with no copy.
2. **Degrade** (the honest backstop). If repair still fails, the block becomes a
   `markdown` block carrying its REAL content (prose/title, else a JSON code
   fence) — a wrong block costs its visual, never the answer; nothing is invented.

Either way, error diagnostics are downgraded and recorded (as `BLOCK_REPAIRED` /
`BLOCK_DEGRADED`) on the `degraded` telemetry records, never rendered. Malformed
JSON (a settled fence that is not valid JSON) degrades to a code fence of the
source instead of the former red "could not be parsed" card.

**The telemetry loop (Phase 4).** Once per run, at the answer seam, the runtime
measures the final structured answer through the SAME chokepoint the client uses
(bridge `response_contract` op `"finalize"` → `finalizeFenceSource`) and emits the
`onResponseBlocks` observability hook + the `eclipse_response_blocks_total`
metric, labelled by outcome (`repaired`/`degraded`) and block type. A recurring
label is the signal to add a normalization/repair rule — that is how the rate is
driven to zero. The client seam (`setResponseDegradeReporter` in `finalize.ts`)
remains the render-time hook and can forward to a transport when one exists; the
server-side signal is the durable, deduped (one per run) measurement today.

**Guards (CI).** `contract-matrix.test.tsx` holds the line against drift: it
asserts the contract's block types, the renderer registry (`REGISTERED_BLOCK_TYPES`)
and a canonical sample per type are the SAME set, and it renders every type from
its canonical payload asserting no repair, no degrade and no error affordance —
so a new block type cannot ship unrendered, and a renamed field cannot silently
break a figure. There is no hand-copied block vocabulary left in the prompt or the
evaluator: the prompt points at the generated schema digest, and the offline
response smoke check asserts only structure, deferring every field name and enum
to the TS contract.

**Every producer route passes the chokepoint.** The fence path finalizes via
`finalizeFenceSource`; the deterministic planner (`planMarkdown`) re-validates
its hand-built blocks through `finalizeResponse`; export (`responseToJson` /
`responseToPdf`) finalizes defensively so an exported file or saved artifact can
never contain a rejected block. Bots, group chat and the workspace document
viewer render through the same `Markdown` component as chat, so their
`eclipse-response` fences get the identical guarantee — there is no second
renderer to keep in sync.

### Block catalogue

| Family | `type` | Notes |
|---|---|---|
| Content | `markdown` | Full existing Markdown subset, **including typeset formulas** (`$...$` / `$$...$$` in LaTeX - see "Formulas in the chat" in `docs/chat-ui-audit.md`) |
| | `heading` | level 1–4 |
| | `callout` | info/note/success/warning/danger |
| | `key_value` | label/value pairs |
| | `details` | collapsible; native `<details>` |
| Data | `metric_grid` | KPI cards; `unavailable: true` renders an explicit chip |
| | `data_table` | sort + filter + paginate + TSV copy (all local) |
| Visualization | `chart` | line, area, bar, stacked_bar, grouped_bar, pie, scatter, bubble, histogram, heatmap, treemap, sunburst, funnel, gauge, radar, waterfall, **candlestick**, **ohlc**, **regression** (the points, the least-squares line and its R-squared - the engine fits it, so the model never fits it itself) |
| | `diagram` | flowchart, dependency, state — native SVG, read-only |
| | `node_graph` | selectable node/edge graph — same layout engine; a node's `detail` shows on selection |
| | `anatomy` | interactive isometric **mechanism figure**: a declarative scene (slab/cylinder `parts`, `wires`, `legend`, deterministic `stages`) compiled by the Anatomy-derived kit (`lib/anatomy/`, see its `NOTICE`). A stage's `readout` is the ONLY source of live text, so the animation can never invent a value. See ADR-047 and "Isometric mechanism figures" in §3. |
| | `model3d` | interactive **3D model**: a declarative scene graph (`parts[]` with `position`/`rotation`/`scale`, optional `parent` assemblies, `material`/`tone`/`lit`, and geometry as a primitive (`box`/`cylinder`/`cone`/`sphere`/`torus`/`lathe`/`extrude`/`tube`/`gear`) **or a mechanism recipe** (`motor`/`gearbox`/`pump`/`valve`/`gauge`/`tank`/`bearing`/`gear`/`pulley`/`belt-drive`/`frame`/`bracket`/`fan`/`heat-exchanger`/`pcb`/`lever`/`spring`)) compiled to world-space meshes and drawn in an orbitable `ogl` WebGL viewport, with a numbered key, stages and `.glb` download. See ADR-048 and "3D mechanism models" in §3. |
| Learning | `learning_map` | prerequisite-aware learning roadmap: skills as ordered stages (edges derived from `requires`), each with objectives/exercises/assessment, clickable resource links (type/duration/thumbnail), and a completion toggle that **persists** to `/api/learning/progress` when a `pathId` is present. An "alternatives" action re-enters the agent loop; a compact text outline is the fallback. Built by the Learning Research Engine — never a generated image. |
| | `timeline` | ordered events with tone dots (alias `execution_timeline`) |
| | `citations` | numbered sources with host/timestamps (alias `source_list`) |
| Media | `gallery` | inline internet-image gallery: validated results with a **direct image URL**, responsive 2–4 column grid, lazy loading, larger-image lightbox, source-page attribution, and a broken-image fallback (no invented URLs). `images[].url` must be http(s) — enforced by the contract's `httpUrl` refinement. |
| Process | `stepper` | numbered steps with per-step status (pending/active/done/error) |
| | `infographic` | icon cards; `icon` is a semantic key resolved via `lib/response/icons.ts` |
| | `workflow` | icon-driven **connected** process: ordered stages joined by directional connectors, each expandable to `detail` / `inputs` / `outputs`; a stage's follow-up re-enters the agent loop. Distinct from `stepper` (no icons/connectors) and `diagram`/`node_graph` (free-form graphs). `layout` is `vertical`/`horizontal`/`auto` (auto = horizontal when ≤4 stages, stacking to a column on narrow screens). |
| | `flow` | dependency-free **HTML/CSS process flow**: ordered `steps` rendered as frosted cards joined by CSS connectors, each step optionally branching into parallel `paths` rendered as smaller cards. Unlike `workflow` it supports branching/parallel paths; unlike `diagram`/`node_graph` it is responsive cards (flex/grid), not an absolute-positioned SVG graph. `direction` is `LR` (default) / `TB`. The native answer for a flowchart — prefer it over a Mermaid flowchart. The block is **centered and width-capped** (`max-w-3xl`, never full-bleed); its step/path **icons render white** (tone/status no longer tints the glyph — status stays as the dot/check beside the label), and a visible **"Full page"** control opens the WHOLE FLOW in a full-screen overlay — larger, centered, over the blurred page; the overlay is portaled to `document.body` (like the app's other overlays) so a transformed chat ancestor cannot trap `position: fixed` and make it overlap; Escape / backdrop / Close to dismiss. |
| | `report` | multi-section container; section `blocks` validated recursively |
| Action | `action_group` | PROPOSED next steps; a click sends a follow-up prompt into the agent loop |
| | `artifact` | a reference to the existing Artifact Center, linked to its download route |
| Presentation | `stat_hero` | oversized headline number(s) (1–4) with unit + delta; the "at a glance" figure. Distinct from `metric_grid` (compact KPI cards). |
| | `gauge` | progress meter: a `value` against a `max` (default 100) as a filled bar. The fill is clamped to `[0, max]` but the true value is always shown, so a clipped bar never lies. |
| | `comparison_grid` | option × attribute matrix (pricing-table shape); a boolean cell renders a check/cross, otherwise its text. An optional `highlight` marks a column. |
| | `ranked_list` | leaderboard of ranked bars scaled to the largest absolute value in the list (never a fabricated ceiling); order is the producer's rank order. |
| | `badge_row` | a cluster of tag/pill badges (sectors, themes); `tone` maps to the shared palette, `icon` to the semantic allowlist. |
| | `carousel` | a slide deck: each slide is a labelled panel of nested blocks (validated recursively, like `tabs`/`report`), one visible at a time with prev/next + dot navigation. A single slide renders without chrome. |
| Interactive | `inputs` | renders the envelope-level shared `state` as controls; a change updates the answer's state and re-renders any figure bound to a `computed` value — locally, with 0 model calls. See "Envelope state" in §3. |
| | `simulation` | a **declarative in-chat calculator**: `inputs` are local state and `outputs` are safe expressions over it (see "Declarative calculators" in §3). Unlike `controls` (which composes a follow-up prompt and re-enters the agent loop), it computes LOCALLY — no model call, no backend, no arbitrary code. A named `preset` (`risk_reward`) supplies a canonical input/output set; explicit `inputs`/`outputs` override it. Always labelled "Illustrative" with an always-visible disclaimer; it never reads market data and never implies a real backtest. |
| Layout | `tabs` | local tab switch; nested blocks validated recursively |

**Aliases.** For producer convenience the documented synonyms `text`→`markdown`,
`table`→`data_table`, `source_list`→`citations`, `interactive_form`→`controls`
and `execution_timeline`→`timeline` are normalized to their canonical block in
`normalizeBlockAlias` before validation, so the renderer only ever sees canonical
types. The website-style family has matching synonyms: `stat`/`stats`→`stat_hero`,
`progress`/`meter`→`gauge`, `comparison`→`comparison_grid`,
`leaderboard`/`ranking`→`ranked_list`, `badges`→`badge_row` and
`slides`→`carousel`. Flow vocabulary resolves onto the native flow blocks:
`process`→`workflow`, `process_flow`/`pipeline`→`flow` and `flow_graph`→`diagram`.

**Field-name synonyms** are normalized the same way, *after* the type alias, so a
producer is not punished for naming a field naturally. `normalizeBlockFields`
rewrites: `content`→`markdown` (markdown/callout/details), a scalar `text`→
`markdown` on those same prose types (observed producer output — scoped away from
`heading`, which legitimately owns a `text` field), and a scalar `body`→
`markdown` on those same prose types (also accepted as the `mermaid` body) —
three real producer spellings of the one field, all observed in live runs;
`content`/`code`/`source`→
`diagram` (mermaid), `variant`→`tone` (callout, when the value is a valid tone),
`items`→`sources` and `name`/`label`→`title` (citations), string `columns` + positional
array `rows`→typed table columns/records (`data_table`), `note`→`hint`
(metric cards), and common `timeframe` intervals (`1Y`, `YTD`, `MAX`, `1D`,
`90d`, `3mo`, …) onto a supported `financial_chart` timeframe, and `steps`→
`stages` for a `workflow`, and `stages`→`steps` / `branches`/`options`→`paths`
(plus a bare-string step → `{ label }`) for a `flow`. It also coerces observed producer shapes that the
strict schema would otherwise reject whole (each degrades only its own block):
`key`/`name`→item `label` (`key_value`; its `value` is a display line and may
run to 500 chars because producers attach a short source/citation),
`points`/`values`→chart `data` with
`{x,y}` / `{value}` point objects coerced to tuples/scalars, `labels`→
`categories` and Chart.js-style `datasets`→`series` (`chart`, whose
`chart_type` spelling is also accepted),
`ticker`/`instrument`→`symbol` and `interval`/`range`→
`timeframe` plus chart-type synonyms (`financial_chart`), and node
`name`/`title`→`label` / edge `source`/`target`→`from`/`to` (`diagram`,
`node_graph`).

**Candles and formulas (ADR-H242).** `chart` carries `candlestick`/`ohlc` as
first-class types, and an OHLC point is `[open, high, low, close]` (the order
people read a candle in; the engine's spec takes the same four values). A series of quadruples is a price chart even when the type is left
to the `auto` director, and a point that is not a quadruple is a gap — never a
fabricated candle. The synonyms (`candle`, `candles`, `ohlc_bar`, `price_bar`)
are RECOVERED in the repair pass for `chart` as well as `financial_chart`: a
dropped enum left the block invalid and degraded it to prose, which is how a
"candlestick chart" arrived as a text chart. A derived figure may carry
`provenance.formula`, which is rendered under the metric and hero figures — a
number without its formula is an assertion.

**Tone.** Every `tone` (top-level and nested — `flow` steps/paths, `diagram`
nodes/edges, …) is mapped onto the block's enum *or dropped* before validation.
`tone` carries a schema default, so a PRESENT-but-invalid value (`trend-up`,
`positive`, `bearish` — the semantic words that are correct for `icon` but not
for `tone`) defeats that default and hard-fails the whole block; normalization
instead maps the known semantic synonyms to the status enum
(`positive`/`up`/`trend-up`→`success`, `negative`/`down`/`trend-down`→`danger`,
…; `note` stays valid only on `callout`), and drops an unrecognized value so the
default applies. A wrong tone costs the accent colour, never the block.

**Icon values.** The optional `icon` on the icon-bearing item arrays (`infographic`
cards, `workflow` stages, `action_group` actions, `stat_hero` stats, `ranked_list`
items, `badge_row` badges, and a `flow`'s steps and their nested `paths`) is canonicalized before validation against the allowlist
below: case/separator spellings (`TrendUp`, `trend_up`, `TREND UP`), common synonyms
(`graph`, `money`, `alert`) and the emoji producers actually emit (`📈`, `⚠️`) all
resolve to the canonical key. A string that is still unknown is kept as-is — the
renderer degrades it to the neutral dot — and a non-string value (number, object)
has the field dropped, so a bad icon costs at most the glyph, never the block.

**Block-level `unavailable` figures.** The producer prompt's rule for missing
data (`"unavailable": true` — never a made-up value) is honored at the BLOCK
level for the figure family (`stat_hero`, `gauge`, `comparison_grid`,
`ranked_list`, `badge_row`): the data array may be absent/empty and the block
validates; the renderer then shows an explicit UNAVAILABLE state with the
producer's `description`/`caption` explanation instead of an empty or fabricated
figure.

### Producer read-back: schema lookup + pre-send validation

The producer does not have to infer field names. Two read-only tools, backed by
the LIVE zod contract through the bridge (`response_contract` capability in
`src/lib/harness/response-bridge.ts`), are bound to Eclipse:

- `response_block_schema` — the exact field names for any block type (optional
  fields marked, array item fields included), plus the **live icon vocabulary**
  (`iconKeys`, from `lib/response/icon-vocabulary.ts` — the server-safe key
  list; the component map stays in `lib/response/icons.ts`) for the semantic
  `icon` fields. Derived from `ResponseBlockSchema` at runtime, so it cannot
  drift from the renderer.
- `response_validate` — runs the renderer's OWN parser over a drafted answer
  (a full message containing the `eclipse-response` fence, or the bare JSON) and
  returns per-block errors (wrong field name, invalid value, malformed JSON) so a
  drifted block is fixed in-turn, before the answer is sent.

Both are read-only and low-risk; a missing bridge reports UNAVAILABLE honestly.
This is the answer to "the model can write into a format it cannot verify": the
format is now queryable and checkable before emission. It does not replace the
consumer-side leniency above — normalization still catches drift the model never
checked.

**The schema is also injected up front.** Relying on the model to *remember* to
call `response_block_schema` proved fragile: a live run skipped it and guessed
(`datasets` for `series`, a semantic `tone`), so the block rendered as a
diagnostic. Every run whose resolved surface may emit structured blocks now has a
compact digest of the exact field names and enum values appended to its
byte-stable system prompt (`response_schema_prompt_block` in
`python/harness/response_tools.py`, composed into the head in
`graph.execute_run`). It is generated LIVE from the same bridge `op: "schema"`
reply, so it cannot drift from the renderer; a bridge miss degrades silently to
the on-demand tool and never blocks the run.

### Just-in-time design modules

The schema digest carries exact FIELDS, not taste — when a family of blocks is
the right answer, how they differ, and what a good document in that family looks
like. Loading all of that into every prompt is expensive and goes stale.

`python/harness/response_style.py` defines seven design modules — `data`,
`chart`, `diagram`, `workflow`, `interactive`, `explanation`, `mechanical` — each
with the family's block types, the choices a producer gets wrong, and one or two
worked examples. The system prompt receives only a small module INDEX
(`response_style_index_prompt_block`, composed in `graph.execute_run`); before the
first block of a family the model calls the read-only `response_style_guide`
tool for that module. The guide is generated with the live field map from the
same bridge `op: "schema"` reply, so examples and fields cannot drift, and it
still returns its guidance and examples when the bridge is unavailable. Only the
families in use are loaded, so the byte-stable head stays small and the design
rules are versionable in one file.

> The `mechanical` examples are validated against the live contract in review;
> the producer is told the numbers are placeholders, never real figures.

### Follow-up state → prompt (one shared bridge)

Interactive blocks keep their state locally. When an interaction needs the model,
the state is serialized to plain text and re-enters the existing agent loop via
`onFollowup` — as capable as the user typing it. `src/lib/response/followup.ts`
is the ONE implementation of that serialization (`composeFollowupPrompt`,
`renderFollowupTemplate`, `labelsById`); `controls-block.tsx` and
`simulation-block.tsx` both use it instead of hand-rolling interpolation. A new
interactive block gets the same safe `{{placeholder}}` substitution for free.

### Declarative calculators (`simulation`) — state + computed, no JS

The `simulation` block is the engine's first **declarative** interactive surface:
a set of `inputs` (the local state the user drives) and a set of `outputs`, each
an **expression** evaluated locally over that state. A slider move recomputes in
place with **0 model calls** — the value never leaves the browser.

- **The evaluator is a tiny, safe expression language**
  (`src/lib/response/evaluate.ts`) — recursive-descent, a fixed operator set and a
  **closed function whitelist** (`abs`, `sqrt`, `floor`, `ceil`, `sign`, `round`,
  `clamp`, `pow`, `min`, `max`, `sum`, `avg`, `if`). No `eval`, no `Function`, no
  property access, no imports, no I/O. It is **server-safe** (no React/DOM), the
  same shape as `lib/response/icon-vocabulary.ts`.
- **UNAVAILABLE, never a wrong number.** A division by zero, a non-finite result,
  an unknown name or a parse error evaluates to `null`, rendered as `—`.
- **Known rounding.** Outputs round half-away-from-zero to an explicit
  `precision` at the format boundary, so a displayed figure is stable.
- **Two implementations, one truth.** The renderer uses the TS evaluator; the
  harness validates with `python/harness/response_eval.py` (which reuses the
  tested tokenizer/parser of `stats/formula.py`). Both run the SAME fixture corpus
  (`src/lib/response/__fixtures__/evaluate-cases.json`), so they cannot drift —
  see `evaluate.test.ts` and `python/tests/test_response_eval.py`.
- **Producers use a preset or write expressions.** `preset: "risk_reward"` gives
  the blueprint's example (entry + stop/target distance → stop/target price,
  risk/reward, break-even win rate); or the producer supplies explicit
  `inputs`/`outputs`. A later output may reference an earlier output's id.
- **Deliberately illustrative.** The block never reads market data; the
  "Illustrative" chip and disclaimer are always shown. This is the "simple,
  trusted formulas client-side" allowance — not the model's transcription of a
  price.

### Source-referenced figures (`$ref`) — the number comes from the source

A figure value (a `metric_grid` metric, a `stat_hero` stat) may be a **reference**
`{ "$ref": "<namespace>:<id>#/<field>" }` instead of a literal. It is resolved
**before render** (`src/lib/response/refs.ts`) from a real surface, so the model
never retypes a financial figure. Namespaces are an **allowlist**: `analysis`
(this run's computed-result outputs), `tool`, `jdds`, `artifact`. Provenance
(`source`/`asOf`/`freshness`) is attached to the resolved item and shown as a chip,
reusing the existing computed-provenance / observation-freshness vocabulary.

- **Never a literal.** An unresolvable reference becomes an explicit **UNAVAILABLE**
  item; the raw reference string never renders and never falls back to a number.
  So "the model said 237" cannot masquerade as "the source returned 237".
- **Resolution is injected, not global.** The chat wraps each assistant message in
  a `FigureResolverProvider` (`src/components/response/figure-context.tsx`) built
  from the turn's own data (`buildFigureResolver`). A surface with no resolver
  (export, PDF, bots) renders any reference as UNAVAILABLE — the honest default.
- **Allowlist at parse.** An unknown namespace is rejected in `parseFigureRef`.
  Only `analysis` has a client-side source today; `tool`/`jdds`/`artifact`
  references are UNAVAILABLE until server-side resolution lands.
- **Containers are walked.** References inside `tabs`/`report`/`carousel` are
  resolved recursively.

### Envelope state, computed values & the `inputs` block (v1.1)

An answer may carry **envelope-level** `state` (typed scalars: number/select/
toggle) and `computed` (safe expressions over state). The **`inputs` block**
renders `state` as controls; a change updates the shared state, and every figure
bound to a computed value (`{ "$computed": "<id>" }`) re-renders **locally — 0
model calls, no arbitrary code** (the same evaluator as `simulation`,
`lib/response/evaluate.ts`). Computed entries evaluate in order (one may reference
an earlier one); an unresolvable entry renders UNAVAILABLE — never a literal.

- **Resolution.** The Phase-2 pass is extended:
  `resolveResponseFigures(response, resolver, computed)` handles both `$ref`
  (from the turn) and `$computed` (from the live state); `state.ts`
  (`initialEnvelopeValues`, `computeEnvelopeValues`) derives the values.
- **Persistence (v1.1).** The chat wraps each message in a
  `ResponseRuntimeProvider` (`figure-context.tsx`) whose `stateKey` is the message
  id; `ResponseView` owns the state, restores edits from
  `localStorage["eclipse-response-state:<messageId>"]` and writes them back
  latest-wins, so reopening an answer restores the last slider positions.
- **Boundary unchanged.** Inputs are local; only `controls`/`action_group`
  re-enter the agent loop.

### Layout primitives, design tokens & motion

Two structural blocks let a producer compose a response instead of stacking
siblings:

- `layout` — a container (`box` / `row` / `column` / `grid`, `columns` 1–4) whose
  nested `blocks` are validated recursively like `tabs`/`report`. Its styling is
  driven **only** by closed token vocabularies (spacing / radius / tone / align),
  resolved in `src/lib/response/tokens.ts` to existing utility classes. There is
  no path from model output to raw CSS or an arbitrary class — the same posture as
  the icon allowlist.
- `divider` — a labelled or bare rule.

**Motion.** Each surfaced block gets a one-shot entrance (`response-block-enter`,
`fadeInUp`) as it appears — including a block that streams in mid-answer. It uses
`backwards` fill only (never `forwards`/`both`), so it cannot create a persistent
backdrop root above a glass surface, and `prefers-reduced-motion: reduce` disables
it. The block's gap wrapper is unchanged, so the layout-cohesion invariant holds.

### Deterministic Markdown projection (fallback)

`toMarkdownProjection(response)` (`src/lib/response/projection.ts`) is a total,
pure function from a response to **readable Markdown**: prose kept, tables as GFM,
charts as their data table, controls as their labels, a `simulation` as its
expanded default inputs/outputs, a figure `$ref` as UNAVAILABLE (never the raw
reference), and container blocks (`tabs`/`report`/`carousel`/`layout`) flattened so
nothing vanishes. It runs the finalize chokepoint first, so a rejected block is
already degraded before projection. It is derived from block data, never authored
by the model, so it cannot drift from the rendered answer — and the contract-matrix
test asserts **every registered block type projects without throwing and is
non-empty**.

It is the single source for surfaces that cannot render blocks:
`projectContentMarkdown(content)` replaces each `eclipse-response` fence with its
projection (the copy button writes this, so a copied answer is readable text, not
raw JSON); `responseToMarkdown` / `downloadResponseMarkdown` add a Markdown export
alongside JSON/PDF; and bots/group chat share the same renderer path.

**Mermaid repair.** Mermaid is reserved for the diagram families the native
blocks do not cover — sequence, ER, class and gantt. A flow/flowchart is routed
to the native `diagram`/`flow`/`workflow` blocks (the prompt says so explicitly),
which keeps the heavy `mermaid` package unloaded for ordinary process answers.
Mermaid is producer-authored text, and Mermaid v12 rejects
small slips that a model makes routinely. Before rendering, `mermaid-repair.ts`
(a pure, total, tested function) conservatively patches the observed cases — it
decodes HTML entities once (`&gt;`→`>`), quotes an unquoted flowchart/state node
label only when it holds a reserved character (`( ) [ ] { } < > | / \ →`), and
joins a sequence statement that wrapped onto the next line (a lowercase fragment
with no `:` or arrow, following a line that has one). It never invents content
and leaves anything it does not recognise untouched; a diagram that still fails
parses to the existing honest inline card rather than the error boundary.

### Internet image search and the gallery block

A user asking to "show/find images of X" must produce **actual images**, not links.
Two deterministic paths feed the `gallery` block, and the model never invents an
image URL:

1. **Runtime-collected gallery (primary).** The `image_search` tool searches the
   real internet (providers in `src/lib/image-search.ts`: Brave Images when
   `BRAVE_API_KEY` is set, else the keyless Openverse and Wikimedia Commons
   chains, all reached through the SSRF-hardened `safeGet` transport) and returns
   normalized `ImageSearchResult`s. Validated results are handed to the run's
   `ImageCollector` (`python/harness/research/image_contracts.py`) and surfaced on
   the run as an `images` blob. The chat renders it with `ImageGalleryPanel`
   (`components/chat/image-gallery.tsx`) directly beneath the answer and persists
   it on the message, so a reload keeps the gallery. This needs **no** model
   round-trip and cannot be hallucinated.
2. **Producer `gallery` block.** For mixed answers the model may emit a `gallery`
   block inside an `eclipse-response` fence; it renders through the same shared
   `ImageGallery` component.

Every image URL — from either path — is scheme-restricted to http(s) (the
contract's `httpUrl` refinement server-side; `_safe_image_url` and
`image-gallery-view.ts` client-side), so `javascript:`/`data:` URLs can never
reach an `<img src>`. Images load directly (plain `<img>`, `loading="lazy"`,
`referrerPolicy="no-referrer"`); a fetch failure degrades to a labeled
"Image unavailable" card rather than a broken box or a crash.

### Isometric mechanism figures (`anatomy`) — a scene, not generated code

The `anatomy` block explains a *physical mechanism* (how a cache, a data path, an
engine or an agent pipeline works) as an interactive isometric illustration. It is
the one place a figure is not a chart/flow, and it keeps the engine's posture
intact: **the model authors a declarative scene; it never authors SVG or code.**
It can be requested explicitly with the `/anatomy <concept>` slash command (an
agent-turn command — `docs/harness/slash-commands.md`), or the agent may choose it
when a mechanism explanation fits.

- **The scene** (`src/lib/response/blocks/anatomy.ts`): `parts[]`
  (`id`, `kind: slab|prism|cylinder|disc|knob|lathe|cone|sphere`, a placement
  `x/y/z` with `w/d/corner` (box) or `radius` (round), `height`, `tone`, `lit`,
  `halo`, `label`, and craft decorations — `groove`, `screws`, `ticks` (a ruler
  strip), `knurl`/`knurlCount`), `wires[]` (`from`/`to` part ids, optional
  world-space `via` waypoints, a `tone`, optional `label`), an optional
  `legend[]`, and optional deterministic `stages[]` (`{ label, note, readout, lit }`,
  where `lit` is a boolean or an id list). `lathe` takes a turning `profile`
  (`[axial, radius]` pairs — bells, flanges, bottles; `smooth: true` shades a
  curved profile as one body), `cone` a `radius`/`radiusTop`, `sphere` a
  `radius`; these come from the vendored kit's lathe (`lib/anatomy/lathe.mjs`) and
  return the same `SolidPaths` shape, so a machine is built from **turned solids,
  not just boxes and tubes**. `tone` is the SAME status vocabulary as every other
  block (`neutral|info|success|warning|danger`). `legend[].mark` is free text.
  Bounds: 64 parts, 128 wires, 12 legend keys, 12 stages. **Painter's order is
  the producer's order** — the model lists the base/ground first, then nearer
  parts (a naive depth sort would hide a small part behind a large ground slab).
  Viewport (`width`/`height`) and camera (`azimuth`/`elevation`) are declared; the
  projection is auto-fitted and a tight `viewBox` is computed.
- **Labels are numbered callouts, not in-plane text.** Each labelled part gets a
  numbered badge (`1`, `2`, …) in the figure and a **key below it** lists the full
  labels — SVG text cannot wrap, so the model's descriptive sentences overflowed
  when drawn along the isometric plane.
- **The compiler** (`src/lib/anatomy/scene.ts`) is pure and server-safe: it turns
  the scene into one `SolidPaths` per part (via the vendored kit's
  `slabOf`/`cylinder`), projected wire endpoints (`iso`) and label transforms
  (`topMatrix`). It is **total** — a part it cannot place (non-finite, no
  footprint) or a wire with an unknown endpoint is skipped with a diagnostic,
  never thrown. The same scene compiles identically for a test, a server render
  or an export.
- **The kit** (`src/lib/anatomy/`) is the MIT-licensed Anatomy-derived isometric
  toolbox (`iso-kit.ts`, `draw.tsx`, `live.tsx`); `lib/anatomy/NOTICE` records
  its origin and the update procedure. The bespoke lathe/tube/WebGL parts of the
  upstream project are **not** in the runtime (kept under
  `docs/figures/eclipse-refinery/` as a reference benchmark).
- **Live text comes only from the model of record.** The renderer shows a
  stage's `readout`; when no stage is selected it shows the block's static
  `readout`. Nothing on screen is computed by the animation, so a figure can
  never show a number the block did not carry — the same "model is the source of
  truth" rule as `simulation`, without an evaluator.
- **Interaction & motion.** Stage controls (play/pause, previous/next, reset)
  advance a discrete index — there is **no `requestAnimationFrame` loop**, the
  autoplay `setInterval` is cleared on pause and unmount, and autoplay is off
  under `prefers-reduced-motion` (a manual step still works — it is a discrete
  change, not an animation). The figure carries `role="img"` with the block's
  `description` as its label plus an `sr-only` sentence.
- **Security.** No path from the model to SVG/HTML/`eval`/`Function` or a dynamic
  component import: the scene is structured JSON validated by the contract, and
  only registered primitives render (`SEC-001`). The drawing is **self-contained**:
  every path is painted with explicit `fill`/`stroke` SVG presentation attributes
  and an inline palette, so it depends on **no stylesheet** and cannot fall into
  the "undefined CSS variable → black-on-black" failure the kit's class-driven
  paint produced when its stylesheet did not load.
- **Presentation.** A graphite-on-dark-paper look: near-black solid fills with
  thin grey ink outlines, muted accent lines for flow, light-grey labels, on a
  near-black "paper" panel inside a width-capped **frosted-glass card** with a
  header (fig/title), a legend/readout line and the stage controls; a **"Full
  page"** control opens the figure in a full-screen overlay (portaled to
  `document.body`, Escape/backdrop to close — the same pattern as the `flow`
  block).
- **Fallback.** The Markdown projection renders the figure's parts and stages as
  a list (`projection.ts`), and the PDF export adds a parts/connections line —
  so a surface that cannot draw the SVG still gets the figure's content.

### 3D mechanism models (`model3d`) — a scene graph compiled to real meshes

The `model3d` block is the true-3D successor to the isometric `anatomy` block:
same posture (**the model authors a declarative scene, never meshes/shader code**)
but the output is a real, orbitable 3D model that can be downloaded as `.glb`.
It is requested with the same `/anatomy <concept>` slash command.

- **The scene** (`src/lib/response/blocks/model3d.ts`): `parts[]`, each with an
  `id`, a transform (`position`, `rotation` in degrees, `scale`), an optional
  `parent` (assemblies), `material`/`tone`/`lit`/`label`, and geometry as either
  a `kind` primitive or a `recipe` (+ numeric `params`). Primitives:
  `box`, `cylinder`, `cone`, `sphere`, `torus`, `lathe` (a `profile` of
  `[z, radius]` pairs), `extrude` (a `points` polygon), `tube` (a `path` of
  `[x,y,z]`), `gear` (`teeth`/`toothDepth`). Recipes are the **mechanism kit**
  (`motor`, `gearbox`, `pump`, `valve`, `gauge`, `tank`, `bearing`, `gear`,
  `pulley`, `belt-drive`, `frame`, `bracket`, `fan`, `heat-exchanger`, `pcb`,
  `lever`, `spring`): each expands into a detailed multi-part assembly under one
  labelled group, which is what makes a composed figure read as a machine rather
  than a pile of cylinders. Optional `wires[]`, `legend[]`, `camera`
  (`azimuth`/`elevation`/`distance`) and deterministic `stages[]`. Bounds: 96
  parts, 128 wires, 12 stages. Coordinates are world units, z up.
- **The compiler** (`src/lib/model3d/compile.ts`) is pure, server-safe and
  **total**: it expands recipes, composes transforms through parents (with a
  cycle guard), bakes every mesh to world space, drops the scene onto `z = 0`,
  fits the camera and reports any part/wire it could not place as a diagnostic —
  it never throws. Geometry builders live in `mesh.ts`; the recipe kit in
  `recipes.ts`; the shared vocabulary in `names.ts`.
- **The renderer** is two pieces: `model3d-block.tsx` (the DOM half — header,
  numbered key, legend, readout, stage controls, `.glb` download) and a
  `next/dynamic(ssr:false)` `model3d-canvas.tsx` WebGL viewport built on `ogl`
  (already a dependency). It offers orbit/zoom/pan, pencil-on-charcoal shading
  (dark paper ground behind an alpha context, posterized graphite fills, paper
  grain, a light edge on silhouettes and a faint grid), projected numbered
  hotspots and stage highlighting. **Solids are always graphite grey (anatomy
  parity); `tone` colours the WIRES and the legend, and `lit` lifts the one
  subject to a lighter graphite.** The canvas element is **created inside the
  effect** and removed on teardown, so every mount gets a fresh context and a
  remount can never reuse a dead one (the earlier white-viewport bug); context
  creation waits for a non-zero size, `webglcontextlost` is handled, rendering
  pauses off-screen, and the scene is memoized by content so streaming does not
  recompile/remount per token. If the context cannot be created the DOM half
  still renders.
- **Export** (`src/lib/model3d/glb.ts`) is a dependency-free glTF 2.0 binary
  writer: the baked parts become mesh nodes with PBR materials, so the download
  opens in any 3D tool.
- **Validation & selection.** Recipe parameters are checked against a declared
  contract (`RECIPE_PARAM_KEYS`); an unknown key is reported as a diagnostic.
  The compiler reports an off-scale scene and caps the outline **edge budget**
  (60k segments) so a large model degrades instead of freezing. Clicking a key
  selects/highlights its part and clicking a part (raycast picking, click-vs-drag)
  selects its key; numbered hotspots highlight with the stage and the selection.
- **Views & export.** On-canvas **Explode** and **Section** (cutaway) sliders, a
  **High-contrast** toggle, pinch-zoom + keyboard orbit/zoom/reset, a PNG
  snapshot, a **leader line** per hotspot, and **GLB / OBJ / STL** export
  (`glb.ts`, `exporters.ts`). The GLB carries the stages as a **stage animation**
  (pivot-correct scale pulse per lit group). A busy scene **LODs** tiny parts'
  outlines. A **Share link** copies a self-contained `/figure#<base64>` URL and
  the public `/figure` route renders the block standalone (`lib/response/share.ts`).
- **Fallback.** When WebGL is unavailable or the context is lost the panel draws a
  static **isometric wireframe** of the compiled feature edges (plus hotspots) via
  the anatomy iso-kit, so it is never a blank box. The Markdown projection and PDF
  export render the model's parts and stages as text. The legacy isometric
  `anatomy` block remains registered and renders unchanged.



`splitResponseSegments` splits prose vs. `eclipse-response` fences.
`decodeResponseFence(source, settled)` distinguishes:
- `ok` — valid JSON → validated response.
- `empty` — whitespace body → render nothing.
- `incomplete` — a JSON **syntax** error while the turn is still streaming → a
  "composing" placeholder (never rendered as a validated object).
- `malformed` — a syntax error on a **settled** turn → an explicit diagnostic
  card with a "Show the raw content" disclosure, so an unparseable body is never
  lost to the user.

**Incremental decode (streaming).** While the fence is still being written the
whole envelope is not valid JSON, but finished `blocks[]` entries already are.
`decodeResponseFenceStreaming(source)` (`src/lib/response/stream-blocks.ts`) scans
the partial source with a brace/string-aware cursor and returns each **fully
closed** block, so `ResponseFence` renders blocks as they arrive instead of
holding the whole answer. The hard rule: only a closed, JSON-parseable object is
ever returned as a block — **a half-written block is never rendered as data**, it
stays the "composing" placeholder. Each closed block is validated + repaired/
degraded through the **block-level chokepoint** (`finalizeBlock`) and memoized by
its raw JSON (`finalizeBlockCached`), so a streaming frame only re-finalizes the
block that changed. Blocks carry a **stable key** (`id ?? index:type`) so a
block's identity — and its local React state, e.g. a slider position — survives as
later blocks arrive. The settled path (`decodeResponseFence`) stays authoritative;
the scan is a fast heuristic for the streaming path only.

### Interactive apps (`interactive`) — model-authored code in an opaque-origin sandbox

The `interactive` block is the escape hatch for things the user should **operate**
rather than read: a price knob, a VWAP explorer, a draggable doji figure. Unlike
`anatomy`/`model3d`, the model supplies actual markup + code, so the block exists
to be *isolated*, not trusted.

- **The block** (`src/lib/response/blocks/interactive.ts`): `html` (required,
  body markup, inline SVG expected), optional `css`/`js`, `height` (240–900),
  optional `dataset` (`{ kind:'series', symbol, market?, range?, interval? }`),
  static `data`, and `provenance` (`illustrative` | `user-provided`). Assembled
  source is capped at 200 KB. It rides the ADR-043 pipeline unchanged
  (validation, repair/degrade, registry, projection, export).
- **The sandbox** (`src/lib/interactive/document.ts` +
  `src/components/response/interactive-frame.tsx`). The composer wraps the source
  in ONE document whose `<head>` carries an immutable meta CSP:
  `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline';
  img-src data: blob:; connect-src 'none'; frame-src 'none'; object-src 'none';
  base-uri 'none'; form-action 'none'`. It also injects a tiny runtime
  (`Eclipse.data()`, `Eclipse.onData(fn)`, `Eclipse.resize(h)`) and unwraps a
  model-supplied full document so the model can never replace the policy. The
  frame is `<iframe sandbox="allow-scripts">` with **no `allow-same-origin`**, so
  it runs in an opaque origin: no app DOM, cookies or storage, and no network.
  Message traffic is accepted only when `event.source === frame.contentWindow`
  and the per-render nonce matches.
- **Data comes from the host, never from the model.** When `dataset` is present,
  `src/lib/interactive/dataset.ts` validates the symbol/range/interval and calls
  the existing read-only `/api/price-history` route from the app origin,
  normalizes the bars (caps at 5000) and posts a snapshot with `source`, `asOf`,
  `freshness` and `stale`. An empty or failed series becomes an explicit
  `status:'unavailable'` envelope — never a fabricated line. This is why the model
  is told to declare `dataset` instead of typing prices: a widget cannot claim to
  be live while showing invented numbers.
- **Authoring is forgiving.** A settled ```` ```html ````, ```` ```htm ````,
  ```` ```svg ```` or ```` ```eclipse-app ```` fence is rendered by the *same*
  component, so a model that answers "here's the code" still produces a live app
  instead of a wall of text. The composer keeps a full document's own
  `<style>`/`<script>`/body, strips a model-supplied CSP `<meta>` and `<title>`,
  and emits its own policy first. **The app owns its palette**: the shell sets
  only structural defaults (box-sizing, margin, font, transparent background) and
  never forces a text colour or `color-scheme`, so the model can design light,
  dark or themed from the user's context. The card is full width and offers
  Reload, Download (the composed HTML) and a viewport-filling Full page view
  (Escape to exit). The scrollbar is thin and derived from the app's own
  `currentColor`, scroll chaining is contained, the card auto-fits the app's
  reported content height (clamped 240–900), and an uncaught app error is
  surfaced as an "App error" banner instead of a silent blank — with an
  **Ask Eclipse to fix** action that re-enters the agent with the error. Until
  the app signals `eclipse:ready` the card shows a skeleton and fades the frame
  in. The host exposes `Eclipse.context = { theme, reducedMotion, locale }`
  (baked at mount, then pushed live when the app theme changes) so a widget can
  match the user's scheme without guessing from the OS. `Eclipse.visible` /
  `Eclipse.onVisibility(fn)` reports off-screen or hidden-tab state, the shell
  pauses CSS animations while hidden and holds `requestAnimationFrame` callbacks
  until the card returns, so an off-screen app stops burning CPU. The toolbar
  also offers a source view with Copy, a drag/keyboard resize handle whose height
  is remembered per app, and a focus-trapped full page that restores scroll and
  focus on exit. A fenced app that
  needs a series declares it
  in a leading `<!--eclipse-dataset {"symbol":"AAPL","range":"6mo"}-->` comment
  (stripped before render); the widget reads it with `Eclipse.data()` or
  `Eclipse.bars()`.
- **Live preview while writing.** A still-streaming ```` ```html ```` / ```` ```svg ````
  / ```` ```eclipse-app ```` fence renders a debounced (450 ms) sandboxed preview
  of what has arrived, labelled "Live preview · building"; the settled block
  replaces it. No dataset is requested mid-stream.
- **Sharing.** The Share action copies `/app-view#<base64>` (the same encoding as
  `/figure`). The standalone page decodes the block and renders it in the same
  sandbox — no server storage, `noindex`. Links are ephemeral and bounded by the
  URL length.
- **Fallback.** The Markdown projection names the app and its data request, and
  the PDF export says the app must be opened in the app — nothing vanishes on a
  surface that cannot run it.

## 4. The renderer (`src/components/response/response-view.tsx`)

An explicit **registry** (`REGISTRY`: block type → component), not a conditional
chain. Adding a block = add its schema + one registry entry; the chat renderer is
untouched.

Every block is wrapped in `BlockBoundary` (a React error boundary), so a chart
failure cannot destroy the surrounding answer. The chart component
(`response-chart.tsx`) maps the block to the shared `ChartSpec`, resolves a named
`dataSource` through `/api/price-history`, asks the Python engine for the picture
and the live figure, and renders it with **Plotly** (`plotly-chart.tsx`;
`docs/chart-engine.md`, ADR-050 as amended 2026-10-22). The drawn PNG paints
first and Plotly is loaded lazily, so a chart is visible immediately. A chart
block may also arrive as a **SCENE** -
`panels` of `marks` - so the model can draw ANY chart the user asks for, not
just the kinds someone pre-loaded. `MermaidBlock` is imported **statically**: it
lazy-loads
the heavy `mermaid` package inside its own effect, so wrapping the tiny wrapper in
its own `next/dynamic` only added a redundant chunk-load failure path that could
surface a scary render error instead of the block's inline card. Mermaid renders
are also **serialised** through one module-level chain, because Mermaid keeps its
parsed theme/config in module-global state and two diagrams in one answer could
otherwise clobber each other. Any failure — dynamic import, `initialize`, or
`render` — degrades to the inline "Diagram could not be rendered" card and never
reaches `BlockBoundary`.

### Layout cohesion (one document, not a stack of cards)

`blocks[]` is a list of **components**, not a document wrapper — so a producer
that puts one idea per entry (a callout, then a paragraph, then a table …) is
structurally valid. The renderer must therefore make any block count read as
**one answer**, never as N detached cards. `ResponseView` assigns the gap between
siblings by **adjacency** (`blockGapClass`): two adjacent *prose* blocks
(`markdown`, `heading`, `callout`, `details`, `key_value`, `citations`,
`timeline`) get a tight `mt-2.5` so they flow, while a *surface* block (`chart`,
`data_table`, `metric_grid`, `diagram`, `mermaid`, `node_graph`, `tabs`,
`stepper`, `infographic`, `report`, `action_group`, `artifact`, `controls`, and
`unknown` diagnostics) keeps a clear `mt-4` so it reads as its own figure. The
first block carries no leading gap, and the same helper drives the nested
`renderBlocks` used by `tabs` and `report`. The invariant — *fragmentation by the
model must never degrade into a detached-card layout* — is locked by the
"response layout cohesion" tests in `render.test.tsx`. The producer prompt also
states the array is one document, so the model is steered toward a single
`markdown`/`report` block for connected prose.

### Computed results are NOT a block (R3-06)

A result Eclipse *worked out* (`analysis_run`) does not travel through the
`eclipse-response` contract at all: the runtime emits `analysis.completed`
carrying the SAME bounded blob it persists (`AnalysisResult.to_blob()` — outputs,
artifacts, provenance), the client maps it to the turn's `analysis` field, and
`computed-result-panel.tsx` renders it under the assistant message with the
always-visible "Worked out by Eclipse" label. A value without a provenance
record renders UNAVAILABLE, never bare, and the panel is never a citation: a
computed number is not retrieved evidence. Both chat surfaces map the full turn
(chat-dock and stock-chat), so the panel, the code-capability panel and the
document panel appear everywhere.

The card's second line is a METHOD a person can read. A provenance detail that
is really a debug dump of the runtime's Python object (`type <class 'dict'> ·
keys [...]`) is dropped rather than shown — it describes the object, not the
calculation — and a "Proof it works" panel with no recorded check, claim,
artifact, review or repair renders nothing at all, because a "0 check(s)" card
claims a check that never happened.

Diagnostics are split by **severity**: only `error` diagnostics raise the amber
panel; a warning-only answer renders quietly (an empty-but-valid envelope says so
in one muted line instead of an alarm).

### Theming (light and dark)

Blocks are theme-aware. The app switches scheme by toggling the `dark` class on
`<html>`, and the block renderers follow the **same signal** the charts already
use (`lib/chart/providers/eclipse-provider.ts`), via the shared
`hooks/use-dark-scheme.ts` hook. `mermaid-block.tsx` observes that class and
re-initialises Mermaid with `theme: 'dark'` or `'default'` so a diagram is never
rendered on a mismatched background; `response-chart.tsx` redraws its picture in the
matching theme when the scheme flips so axis/legend ink stays legible;
`diagram-block.tsx` and `node-graph-block.tsx` draw node labels with
`currentColor` so they inherit the active foreground instead of a hardcoded
light-mode fill.

### Chart & diagram presentation

Every visual surface uses the frosted-glass system: the drawn chart picture
(a transparent PNG, so the frost behind it still shows),
the Mermaid/diagram/node-graph SVGs and the loading skeletons all sit in
`.glass-card-subtle` containers rather than flat `border + bg-accent` fills.

A `chart` block covers **sixteen series styles** — the classic
line/area/bar/stacked_bar/grouped_bar/pie/scatter/histogram/heatmap plus
`bubble` (`[x, y, size]` triples), `treemap`, `sunburst`, `funnel`, `gauge`,
`radar` and `waterfall`. A producer picks the style that fits the data. The
translation to the engine's spec is pure and lives in
`src/lib/response/chart-spec.ts` (`chartBlockToSpec`): it never invents a
point, and a **lossy** mapping is TOLD — the engine draws a fixed set of
kinds, so a `treemap`/`sunburst`/`funnel`/`gauge` is drawn as the closest
honest shape (a bar or a pie) and the note appears under the picture, so the
user is never looking at a chart that quietly became a different chart. Series
colours come from the app's single source of truth
(`DEFAULT_CHART_PALETTE`, `src/lib/chart-palette.ts`), which is **green/red by
default** (finance up/down) and **decoupled from the theme** — applying or
previewing a theme never recolours a chart. A user changes chart colours only
deliberately (Settings › Charts, or a preset that carries its own
`chartPalette`); a producer that genuinely needs colour sets it per series via
`color`.

**The frosted tooltip recipe is gone with the browser canvas.** A chart is now
a picture, so there is no hover tooltip to frost: the values a tooltip used to
show live in the block's own table/text, and the picture is the picture.

The frosted **tooltip** recipe (translucent tint, `appendTo: 'body'`, 18px blur,
rounded shadow) lives once in `baseChartOption()`; `mergeChartOption()` combines
it with the block's own `trigger`/`valueFormatter`. A plain spread would let the
bare block tooltip clobber the glass chrome �?" that regression is why the merge is
a named, tested helper.

**Visual director, weights, bands and focus (2026-10-19).** `chartType: "auto"`
(the new default; explicit types always win) resolves in `chart-spec.ts`: a
temporal category axis or multiple series renders a line; a single series of at
most 12 labels renders bars; `[x, y, size]` triples render `bubble`; a fully
monotonic pair renders a line; any other pair renders `scatter`. A series may
carry `weight` (0..1): it scales stroke width
(`Math.round((1.2 + 2.4*w)*100)/100`) and opacity (`0.45 + 0.55*w`) so the
important series reads first without inventing values. A series may also carry
`band: {lower, upper, weight?}`: the band travels into the engine's spec and is
drawn as a translucent area around the series — presentation weight, never a
probability. `data_table` alignment is derived in
`table-presentation.ts` (an explicit `align` wins; a column whose values are
≥80% numeric right-aligns; raw numbers get locale formatting with at most 4
fraction digits, numeric strings are left untouched). `response-chart.tsx` adds
a **focus overlay** (Maximize control, Escape/backdrop/Close to dismiss,
`role="dialog"`); the picture is the same artifact, shown larger.

### Integration point

`components/chat/markdown.tsx` `Block`'s `case 'code'` checks the fence language:
`eclipse-response` → `<ResponseFence>` → `<ResponseView>`; anything else is a
normal code block. `Markdown` gained a `streaming` prop, threaded from
`chat-history.tsx`'s `AssistantContent`, so an in-progress fence shows the
composing placeholder.

## 5. The Intelligent Response Orchestrator (response-mode plan)

The engine above lets the model emit structured blocks, but until now nothing
*decided* whether a turn should be prose or a figure — the model volunteered a
fence or it did not, and the deterministic planner only upgraded Markdown tables
and source lists. The orchestrator is that missing decision layer: a **pure,
model-free classifier** that picks ONE presentation mode and appends a matching
directive to the prompt head.

`python/harness/response_mode.py` — `classify_response_mode(query, history) ->
ResponsePlan`. Modes: `text`, `explanation`, `visualization`, `simulation`,
`workflow`, `composite`. It is modeled on the deterministic code-request
classifier (`code/request_intent.py`): no model call can force a presentation,
and it is testable independently of the run loop.

- **Deterministic, distinctive signals.** Each mode owns a signal vocabulary
  (workflow: agent/delegate/dependency/workflow; simulation: backtest/what-if/
  scenario/monte-carlo; visualization: chart/compare/correlation/drawdown/
  distribution; explanation: explain/teach/how-does/difference-between). Two
  rich modes co-occurring — at least one data-bearing — resolve to `composite`.
- **Bias to honesty.** An ambiguous, short or conversational turn is `text`, so a
  widget is never forced. A follow-up ("do it") inherits the prior user turn's
  mode (bounded recursion).
- **Wiring.** In `graph.execute_run`, gated on the same resolved surface that may
  emit blocks (`response_block_schema` in `allowed`) and placed right after the
  schema digest: the directive is appended to the byte-stable prompt head, and
  the chosen mode is emitted as the `response.plan` run event for evaluation.
  Best-effort — a classification failure degrades to text and never blocks the
  run.
- **Model-assisted fallback (opt-in).** When the deterministic verdict is
  `unsure`, a single bounded model call may choose a mode instead
  (`response_mode_llm.py`: `orchestrate_response_mode` → `refine_with_model`).
  Off unless `HARNESS_RESPONSE_MODE_MODEL` is truthy, so the default path stays
  deterministic and free; one short completion under a hard deadline
  (`await_bounded`); any failure returns the deterministic plan unchanged. The
  prompt + reply parser (`MODE_CLASSIFIER_SYSTEM`, `parse_mode_reply`) live in
  `response_mode.py` as pure, tested functions.
- **Client surface.** The mode is not only prompt guidance: the front door's
  `response.plan` frame is normalized in `src/lib/agent/events.ts`
  (`coerceResponsePlan`) and carried on the turn as `AssistantTurn.responsePlan`,
  so `chat-history.tsx` shows a small mode chip for non-`text` turns. Display
  only — it never changes the answer.
- **What it is not.** No wire contract change (the mode rides an existing run
  event) and no fabricated data. The schema digest remains the source of EXACT
  field names — the plan only says WHICH structure fits and reminds the model of
  the data-honesty rules.
- **When NOT to render.** Every plan also appends `RENDER_DISCIPLINE` (in
  `response_mode.py`): a checklist that overrides the mode — one sentence answers
  it → write the sentence; a lone fact/lookup/definition → prose; data you do not
  hold → `UNAVAILABLE` in prose, never an empty figure; a requested file → write
  the file; never replace the whole answer with a bare fence. It lives in the
  dynamic per-run directive, so the static prompt ceiling does not grow.

- **Routing benchmark (Phase 6).** `python/harness/response_mode_benchmark.py` holds
  a versioned, labelled set of real-shaped prompts (each with its expected mode,
  including text anti-cases and follow-ups) and scores the SHIPPED deterministic
  classifier: overall accuracy, per-mode precision/recall and the confusion pairs.
  `python -m harness.response_mode_benchmark` prints the report; the test asserts
  an accuracy floor (≥0.95) and per-mode recall floors. It runs the same
  `classify_response_mode` the runtime uses, so it cannot drift; the
  model-assisted path is non-deterministic and is deliberately not benchmarked.

Tests: `python/tests/test_response_mode.py` (the decision table, composite, text
defaults, learning refinement, follow-up inheritance, the model-assisted fallback,
directive rendering); `python/tests/test_response_mode_benchmark.py` (routing
accuracy + per-mode floors); `src/lib/agent/events.test.ts` (`response.plan`
mapping + `coerceResponsePlan`).

## 6. Security posture

- **No execution.** Blocks are structured JSON only. There is no path from a
  model response to `eval`, `Function`, raw HTML, or a dynamic component import.
- **Registry allowlist.** Only registered types render; unknown types degrade.
- **URL safety.** Citations and artifact links use the same external-link policy
  as Markdown (`noopener noreferrer`) and are **scheme-restricted to `http(s)`**
  in the contract — bare `z.string().url()` accepts `javascript:`/`data:`, which
  would be an XSS vector once rendered as an `href`.
- **Icon allowlist.** Infographic/action `icon` values are semantic keys resolved
  against `lib/response/icons.ts`; spellings, common synonyms and emoji are
  canonicalized to the allowlisted key before validation, an unknown key degrades
  to a neutral default, and a non-string value is dropped rather than failing the
  block. The model never names a component or an import path, and the live
  vocabulary is queryable via `response_block_schema`.
- **Actions are proposals.** `action_group` only composes a follow-up prompt and
  re-enters the existing agent loop; it cannot call a backend function, and the
  card is labeled "Proposed" until the user runs one.
- **Resource limits** bound render cost (see §3).
- **No fabricated data.** The contract has an explicit `unavailable` state; the
  renderer shows it as a chip rather than a value. The engine never fills gaps.

## 7. Verification

- `src/lib/response/contract.test.ts` — envelope, per-block degradation, unknown
  types, version warnings, nesting, totals.
- `src/lib/response/contract-blocks.test.ts` — the new block types, the spec-name
  aliases, link scheme restrictions, the icon allowlist and icon-key
  canonicalization (aliases, emoji, non-string drop, nested blocks).
- `src/lib/response/parse.test.ts` — segmentation, streaming vs. settled decode.
- `src/lib/response/chart-spec.test.ts` — the block-to-spec translation per chart type.
- `src/lib/response/diagram-layout.test.ts` — layering, unknown-edge handling,
  cycles.
- `src/components/response/render.test.tsx` — server-renders the **real**
  components (`react-dom/server`) to verify registry dispatch, mixed-block
  ordering, unknown-block isolation, `report` nesting, the streaming/malformed
  fences, action-group proposal semantics, safe citation links, and the
  `mermaid` fence rendering as a diagram (not a `<pre>` code block). Client-only
  canvas/interaction paths (the chart engine's async render, Mermaid's async render,
  exercised by the option/layout tests and the production build, not here.
- `src/lib/anatomy/scene.test.ts` — the `anatomy` scene compiler is pure, total
  and deterministic: parts compile to real geometry with a finite projection, a
  wire routes between known parts, an unknown endpoint / a non-finite part is
  skipped with a diagnostic (never thrown), and an empty figure still yields a
  finite projection.
- `src/components/response/anatomy-render.test.tsx` — server-renders the real
  `AnatomyBlock`: a labelled `role="img"` SVG carrying real geometry, the
  fig/legend/caption chrome, the sr-only description, and a control per
  interaction (play/pause, previous/next, reset) — with no stage controls when
  the block declares no stages. Client-only timer/click paths are not exercised
  here (no DOM harness in this repo), consistent with `render.test.tsx`.
- Full suite: `npx vitest run`, `npx tsc --noEmit`, `npm run build`, and the
  Prompt/ceiling Python tests (`test_memory_tools.py`,
  `test_phase_s_stabilization.py`).

## 8. Requirement traceability

| ID | Requirement | Location | Verification | Status |
|---|---|---|---|---|
| RESP-001 | Versioned response contract | `lib/response/contract.ts` | contract.test.ts | Verified |
| RESP-002 | Per-block validation + total parse | same | contract.test.ts | Verified |
| RESP-003 | Unknown/malformed block → diagnostic, no lost answer | `contract.ts`, `blocks.tsx` | contract.test.ts | Verified |
| RESP-004 | Resource limits | `contract.ts` `RESPONSE_LIMITS` | contract.test.ts | Verified |
| RESP-005 | Schema-version policy | `contract.ts` `normalizeVersion` | contract.test.ts | Verified |
| REND-001 | Registered component registry | `components/response/response-view.tsx` | code review + tsc | Verified |
| REND-002 | Per-block error isolation | `response-view.tsx` `BlockBoundary` | code review | Verified |
| REND-003 | Markdown/content blocks | `components/response/blocks.tsx` | tsc | Verified |
| REND-004 | Rich text reuses existing Markdown | `markdown.tsx` | existing suite | Verified |
| CHART-001 | Chart blocks, drawn interactively by Plotly (simple form, named source, or a SCENE of marks) | `chart-spec.ts`, `chart-data.ts`, `chart-capabilities.ts`, `response-chart.tsx` | chart-spec.test.ts, chart-render.test.ts | Verified |
| CHART-002 | Lazy chart loading | `response-view.tsx` dynamic | tsc/build | Verified |
| DIAG-001 | Interactive diagrams (SVG) | `diagram-layout.ts`, `diagram-block.tsx` | diagram-layout.test.ts | Verified |
| DATA-001 | Interactive data table | `data-table-block.tsx` | tsc | Verified |
| DATA-002 | Metric grid + unavailable state | `blocks.tsx` | contract.test.ts | Verified |
| STREAM-001 | Streaming-aware partial decode | `parse.ts` | parse.test.ts | Verified |
| STREAM-002 | Incremental block decode: closed blocks render as they arrive; a half-written block is never rendered as data | `src/lib/response/stream-blocks.ts` + `response-fence.tsx` | stream-blocks.test.ts + streaming-fence.test.tsx | Verified |
| STREAM-003 | Block-level finalize chokepoint + memo cache + stable block keys | `finalizeBlock`/`finalizeBlockCached` + `response-view.tsx` blockKey | stream-blocks.test.ts | Verified |
| AGENT-001 | Producer contract (prompt guidance) | `python/harness/prompts.py` | prompt-ceiling pins in `test_memory_tools.py` + `test_phase_s_stabilization.py` | Verified |
| SEC-001 | No code execution from model output | whole engine | code review | Verified |
| INT-001 | Both chat surfaces render blocks | `markdown.tsx` + `chat-history.tsx` | tsc | Verified |
| INT-002 | Persistence/reopen via existing message store | `Message.content` | by construction | Verified |
| PLAN-001 | Deterministic visualization planner (Markdown → blocks) | `lib/response/planner.ts` + `chat-history.tsx` | planner.test.ts | Verified |
| ORCH-001 | Deterministic response-mode orchestrator (text/explanation/visualization/simulation/workflow/composite) → prompt directive + `response.plan` event | `python/harness/response_mode.py` + `graph.execute_run` | test_response_mode.py + test_graph.py | Verified |
| ORCH-002 | Model-assisted fallback for `unsure` plans (opt-in, bounded, total) | `python/harness/response_mode_llm.py` | test_response_mode.py | Verified |
| ORCH-003 | The chosen mode reaches the client (`response.plan` → `AssistantTurn.responsePlan` → mode chip) | `src/lib/agent/events.ts` + `response-model.ts` + `chat-history.tsx` | events.test.ts | Verified |
| SIM-001 | Declarative in-chat `simulation` calculator: `inputs` (state) + `outputs` (safe expressions), local recompute, illustrative | `src/lib/response/simulation.ts` + `src/components/response/simulation-block.tsx` + `contract.ts` | simulation.test.ts + contract-matrix.test.tsx | Verified |
| EVAL-001 | Safe scalar expression evaluator (fixed ops + closed function whitelist; no eval/Function); UNAVAILABLE on div-by-zero/non-finite | `src/lib/response/evaluate.ts` | evaluate.test.ts | Verified |
| EVAL-002 | TS↔Python evaluator parity via one shared fixture corpus | `python/harness/response_eval.py` (reuses `stats/formula.py` parser) + `__fixtures__/evaluate-cases.json` | test_response_eval.py + evaluate.test.ts | Verified |
| REF-001 | Source-referenced figure values (`$ref`) resolved before render; unresolvable → UNAVAILABLE, never a literal; namespace allowlist | `src/lib/response/refs.ts` + `contract.ts` | refs.test.ts + figure-ref.test.tsx | Verified |
| REF-002 | Per-turn figure resolver from the computed-result blob, injected via React context | `buildFigureResolver` + `figure-context.tsx` + `response-view.tsx` | figure-ref.test.tsx | Verified |
| LAYOUT-001 | `layout`/`divider` primitives; styling only via closed token vocabularies (no raw CSS) | `contract.ts` + `tokens.ts` + `layout-block.tsx` | tokens.test.ts + layout-block.test.tsx + contract-matrix.test.tsx | Verified |
| MOTION-001 | One-shot block entrance motion, reduced-motion safe, no forwards/both fill above glass | `globals.css` + `response-view.tsx` | render.test.tsx (cohesion) | Verified |
| PROJ-001 | Deterministic Markdown projection covering every block type; used by copy + export | `src/lib/response/projection.ts` + `export.ts` + `chat-history.tsx` | projection.test.ts + contract-matrix.test.tsx | Verified |
| STATE-001 | Envelope `state`/`computed` + `inputs` block + `{$computed}` figure binding (local, 0 model calls) | `contract.ts`, `state.ts`, `inputs-block.tsx`, `refs.ts`, `response-view.tsx` | state.test.ts + refs.test.ts + envelope-state.test.tsx | Verified |
| STATE-002 | Interaction state persists per message (localStorage, latest-wins) | `response-view.tsx` + `figure-context.tsx` + `chat-history.tsx` | envelope-state.test.tsx | Verified |
| TELEM-001 | Server `finalize` read-back returns block-type + figure-binding counts; client telemetry seam | `response-bridge.ts` + `response_tools.py` + `telemetry.ts` | telemetry.test.ts + test_response_tools.py | Verified |
| ORCH-004 | Routing-quality benchmark: versioned labelled prompts, accuracy + per-mode recall floors | `python/harness/response_mode_benchmark.py` | test_response_mode_benchmark.py | Verified |
| INT-003 | Backend-driven interaction controls | `controls-block.tsx` + `onFollowup` in both surfaces | contract-extended.test.ts + tsc | Verified |
| ART-001 | Artifact persistence (existing Artifact Center) | `response-actions.tsx` → `registerArtifact` | build/tsc | Verified |
| EXP-001 | JSON / CSV / PNG / PDF export | `lib/response/export.ts`, `response-actions.tsx`, `data-table-block.tsx` | export.test.ts | Verified |
| DIAG-002 | Mermaid (sequence/ER/class/gantt/…) | `mermaid-block.tsx` (lazy, strict) — via `mermaid` block and chat ```mermaid fence | build | Verified |
| CHART-003 | Financial (candlestick/OHLCV) chart block | `financial-chart.tsx` (reuses `ChartWidget`) | build/tsc | Verified |
| REND-005 | Per-response export + save actions | `response-actions.tsx` | build/tsc | Verified |
| BLOCK-001 | `stepper`, `infographic`, `report`, `action_group`, `artifact` blocks | `contract.ts` + `rich-blocks.tsx` | contract-blocks.test.ts | Verified |
| BLOCK-002 | `node_graph` selectable graph (reuses layout engine) | `node-graph-block.tsx` | build/tsc | Verified |
| ANAT-001 | Interactive isometric `anatomy` figure: a declarative scene compiled purely (parts/wires/legend/stages), never model-authored SVG or code | `src/lib/response/blocks/anatomy.ts` + `src/lib/anatomy/scene.ts` + `src/components/response/anatomy-block.tsx` | scene.test.ts + anatomy-render.test.tsx + contract-matrix.test.tsx | Verified |
| ANAT-002 | A `stage`'s `readout` is the only source of live text (the model is the source of truth); discrete stepping, reduced-motion-safe autoplay, timer cleared on unmount | `src/components/response/anatomy-block.tsx` | anatomy-render.test.tsx + code review | Verified |
| ANAT-003 | Anatomy isometric kit vendored with attribution + a verified provenance/update record | `src/lib/anatomy/NOTICE` + `LICENSE` + `iso-kit.ts`/`draw.tsx`/`live.tsx` | blob-hash comparison vs upstream `e9488296` | Verified |
| ANAT-004 | `anatomy` uses the shared status `tone` vocabulary; `normalize.ts` maps synonyms; `legend[].mark` free-text and `stages[].lit` boolean-or-array are lenient | `src/lib/response/normalize.ts` + `src/lib/response/blocks/anatomy.ts` | scene.test.ts + anatomy-render.test.tsx | Verified |
| MODEL-001 | `model3d` authors a declarative scene graph (transforms, parents, recipes) compiled purely to world meshes — never model-authored meshes/shaders/code; total with diagnostics | `src/lib/response/blocks/model3d.ts` + `src/lib/model3d/compile.ts` + `mesh.ts` + `recipes.ts` | model3d compile.test.ts + mesh.test.ts + contract-matrix.test.tsx | Verified |
| MODEL-002 | The mechanism kit exposes exactly the recipes the runtime implements; unknown recipes are rejected by the schema (no silent degrade) | `src/lib/model3d/recipes.ts` + `names.ts` + block schema | compile.test.ts (schema↔kit parity) | Verified |
| MODEL-003 | The WebGL viewport is client-only/lazy (`next/dynamic ssr:false`, `ogl`), disposed on unmount; the DOM key/legend/stages and `.glb` export survive without WebGL | `src/components/response/model3d-{block,canvas}.tsx` + `src/lib/model3d/glb.ts` | model3d-render.test.tsx + compile.test.ts (GLB header/JSON) | Verified |
| BLOCK-003 | Spec-name aliases normalized to canonical blocks | `normalize.ts` (`normalizeBlockAlias`, re-exported by `contract.ts`) | contract-blocks.test.ts | Verified |
| BLOCK-004 | Icon-driven connected `workflow` block (expandable stages, follow-up) | `contract.ts` + `rich-blocks.tsx` (`WorkflowBlock`) | contract-blocks.test.ts + render.test.tsx | Verified |
| BLOCK-005 | Website-style visual blocks: `stat_hero`, `gauge`, `comparison_grid`, `ranked_list`, `badge_row`, `carousel` | `contract.ts` + `visual-blocks.tsx` + `response-view.tsx` REGISTRY | contract-blocks.test.ts + render.test.tsx | Verified |
| BLOCK-006 | `carousel` nests blocks (recursively validated like `tabs`/`report`) | `contract.ts` `parseResponsePayload`/`parseNestedBlocks` | contract-blocks.test.ts + render.test.tsx | Verified |
| BLOCK-007 | Field leniency (`body`, `chart_type`, 500-char `key_value` values, bare-string badges) + block-level `unavailable` figures | `normalize.ts` + `visual-blocks.tsx` UNAVAILABLE state | contract-blocks.test.ts | Verified |
| BLOCK-008 | Producer read-back: exact block schema + live icon vocabulary + pre-send validation (bridge capability `response_contract`) | `src/lib/harness/response-bridge.ts` + `python/harness/response_tools.py` | response-bridge.test.ts + test_response_tools.py | Verified |
| BLOCK-011 | Just-in-time design modules: compact prompt index + `response_style_guide(module)` with family guidance and worked examples; field map comes from the live contract; usable without the bridge | `python/harness/response_style.py` + `response_tools.py` + `graph.execute_run` | test_response_tools.py | Verified |
| FOLLOWUP-001 | One shared local-state → follow-up-prompt serializer (safe `{{id}}`/`{{id.from}}` substitution, stable label order) used by `controls` and `simulation` | `src/lib/response/followup.ts` + `controls-block.tsx` + `simulation-block.tsx` | followup.test.ts | Verified |
| BLOCK-009 | Icon-key canonicalization (spellings, synonyms, emoji) + non-string icon leniency, in the prompt vocabulary | `icon-vocabulary.ts` `canonicalIconKey` + `normalize.ts` + `prompts.py` | contract-blocks.test.ts | Verified |
| BLOCK-010 | Branching HTML/CSS `flow` block (parallel-path cards) + native-flow routing over Mermaid | `contract.ts` + `flow-block.tsx` + `response-view.tsx` + `normalize.ts` + `prompts.py` | contract-blocks.test.ts + render.test.tsx | Verified |
| SEC-002 | Citation/artifact links restricted to http(s) | `contract.ts` `httpUrl` | contract-blocks.test.ts | Verified |
| SEC-003 | Semantic icon allowlist (no component/import from model); vocabulary server-safe, component map client-only | `lib/response/icon-vocabulary.ts` + `lib/response/icons.ts` | contract-blocks.test.ts + route.test.ts | Verified |

## 9. Known limitations (honest)

These remain true of the shipped system:

1. **Graph editing — not offered.** `diagram`, `mermaid` and `node_graph` are
   read-only visualizations (a `node_graph` is *selectable* — a node reveals its
   `detail` and the view zooms/pans — but the contract declares no edit
   operations, so there is no graph editor). React Flow is deliberately not a
   dependency; the deterministic `diagram-layout` engine drives both `diagram`
   and `node_graph`. Editing is out of scope until explicitly authorized.
2. **PDF chart embedding** — the PDF embeds the chart's ARTIFACT (the very picture
   the user saw), fetched back from the Artifact Center and set on the app's own
   dark panel, because the engine draws a transparent figure with light ink. A
   chart that was never drawn (no artifact), or a `financial_chart`, is listed in
   an "Export notes" appendix rather than embedded.
3. **PDF/tabbed flattening** — `tabs` content is flattened; `controls` are
   omitted from PDF (they are interactive-only). Both are reported in the PDF's
   export notes, never silently dropped.
4. **Planner scope** — the deterministic planner upgrades GFM tables → interactive
   tables and link-only source lists → citations. It does not infer charts from
   prose (that would risk fabricating structure), and it runs only on *settled*
   turns (streaming renders raw Markdown to avoid flicker).
5. **Controls re-run via the existing agent loop** — they compose a prompt and
   re-enter `/api/harness/chat`. They cannot call an arbitrary backend endpoint;
   that is the deliberate security boundary (no model-authored privileged calls).
6. **Very large datasets** — `data_table` is client-side (sort/filter/page); it
   caps at 2000 rows in the contract. Server-side pagination for larger tables is
   not implemented.
7. **PDF generation** pulls `jspdf` + `jspdf-autotable` lazily (dynamic import),
   so it never enters the initial chat bundle.
8. **`simulation` is illustrative and local only.** It is now declarative
   (`inputs`/`outputs` expressions, `risk_reward` preset), computes with no
   fees/slippage/gaps, and is entirely client-side — it is never bound to the real
   quant/backtest engine. Routing a simulation through the quant worker via an
   authorized action endpoint (with job handling, provenance and the "real run"
   boundary) remains out of scope; a `controls` block re-entering the agent loop
   is the current, deliberately-unprivileged path for a real computation. The
   evaluator also uses **float arithmetic with explicit output rounding**, not a
   decimal backend — adequate for an illustrative display calculator, but a
   decimal-backed evaluator is a planned hardening for money maths.
9. **`$ref` resolution is client-side and partial today.** Only the `analysis`
   namespace (this run's computed-result outputs) has a resolver; a reference to
   `tool`/`jdds`/`artifact` renders UNAVAILABLE until server-side resolution lands
   at the fence-compile seam. Refs are accepted on the KPI/hero figure family
   (`metric_grid`, `stat_hero`); `chart` series, `data_table` cells, `gauge` and
   `ranked_list` adopt the same mechanism next.
10. **Envelope state persistence is client-local (localStorage).** Envelope
    `state`/`computed` and the `inputs` block are implemented, and edits restore
    on reopen via `localStorage` keyed by message id — not the server transcript.
    A cleared browser storage resets the controls to the answer's defaults (the
    answer itself is unchanged). The `simulation` block's own local state is
    session-only.
11. **`$ref` resolution remains client-side and partial** (see #9): only the
    `analysis` namespace resolves today; `tool`/`jdds`/`artifact` render
    UNAVAILABLE until server-side resolution lands.
12. **`anatomy` is 2.5D; `model3d` is the 3D path.** The legacy isometric
    `anatomy` block draws only isometric `slab`/`cylinder`/turned parts with a
    fixed auto-fitted camera. True 3D (rotation, assemblies, depth buffer, orbit,
    GLB export) is the `model3d` block (ADR-048); `model3d` bounds are 96 parts /
    128 wires / 12 stages, and its stages are still a declared lit set (no physics
    or per-part parameter editing).
13. **`anatomy` provenance is recorded and verified.** `src/lib/anatomy/NOTICE`
    (+ `LICENSE`) records the upstream repository, the MIT license, and the
    **verified** upstream commit `e9488296a44211c42701ff71705b7901470ec78f` — with
    git blob SHA-1s proving `iso-kit.ts`/`live.tsx` are byte-identical and
    `draw.tsx` differs only by its import path.
14. **`anatomy` stages are discrete, not a simulation.** A stage is a declared
    lit-part set + readout; there is no continuous/physics animation and no
    per-part parameter editing. Adjustable parameters are the `simulation` /
    `inputs` blocks' job.

