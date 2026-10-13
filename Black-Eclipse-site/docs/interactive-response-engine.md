---
title: Interactive Response Engine
status: Current
last-verified: 2026-10-12
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
2. **Every block is validated individually.** One bad block degrades to an
   `unknown` diagnostic card; it never discards the rest of the answer.
3. **Unknown block types are preserved, not executed.** They render a diagnostic
   with the raw JSON in a collapsed `<details>`.
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
diagnostic-backed empty response, never a throw.

### Block catalogue

| Family | `type` | Notes |
|---|---|---|
| Content | `markdown` | Full existing Markdown subset |
| | `heading` | level 1–4 |
| | `callout` | info/note/success/warning/danger |
| | `key_value` | label/value pairs |
| | `details` | collapsible; native `<details>` |
| Data | `metric_grid` | KPI cards; `unavailable: true` renders an explicit chip |
| | `data_table` | sort + filter + paginate + TSV copy (all local) |
| Visualization | `chart` | line, area, bar, stacked_bar, grouped_bar, pie, scatter, histogram, heatmap |
| | `diagram` | flowchart, dependency, state — native SVG, read-only |
| | `node_graph` | selectable node/edge graph — same layout engine; a node's `detail` shows on selection |
| Learning | `learning_map` | prerequisite-aware learning roadmap: skills as ordered stages (edges derived from `requires`), each with objectives/exercises/assessment, clickable resource links (type/duration/thumbnail), and a completion toggle that **persists** to `/api/learning/progress` when a `pathId` is present. An "alternatives" action re-enters the agent loop; a compact text outline is the fallback. Built by the Learning Research Engine — never a generated image. |
| | `timeline` | ordered events with tone dots (alias `execution_timeline`) |
| | `citations` | numbered sources with host/timestamps (alias `source_list`) |
| Media | `gallery` | inline internet-image gallery: validated results with a **direct image URL**, responsive 2–4 column grid, lazy loading, larger-image lightbox, source-page attribution, and a broken-image fallback (no invented URLs). `images[].url` must be http(s) — enforced by the contract's `httpUrl` refinement. |
| Process | `stepper` | numbered steps with per-step status (pending/active/done/error) |
| | `infographic` | icon cards; `icon` is a semantic key resolved via `lib/response/icons.ts` |
| | `workflow` | icon-driven **connected** process: ordered stages joined by directional connectors, each expandable to `detail` / `inputs` / `outputs`; a stage's follow-up re-enters the agent loop. Distinct from `stepper` (no icons/connectors) and `diagram`/`node_graph` (free-form graphs). `layout` is `vertical`/`horizontal`/`auto` (auto = horizontal when ≤4 stages, stacking to a column on narrow screens). |
| | `report` | multi-section container; section `blocks` validated recursively |
| Action | `action_group` | PROPOSED next steps; a click sends a follow-up prompt into the agent loop |
| | `artifact` | a reference to the existing Artifact Center, linked to its download route |
| Presentation | `stat_hero` | oversized headline number(s) (1–4) with unit + delta; the "at a glance" figure. Distinct from `metric_grid` (compact KPI cards). |
| | `gauge` | progress meter: a `value` against a `max` (default 100) as a filled bar. The fill is clamped to `[0, max]` but the true value is always shown, so a clipped bar never lies. |
| | `comparison_grid` | option × attribute matrix (pricing-table shape); a boolean cell renders a check/cross, otherwise its text. An optional `highlight` marks a column. |
| | `ranked_list` | leaderboard of ranked bars scaled to the largest absolute value in the list (never a fabricated ceiling); order is the producer's rank order. |
| | `badge_row` | a cluster of tag/pill badges (sectors, themes); `tone` maps to the shared palette, `icon` to the semantic allowlist. |
| | `carousel` | a slide deck: each slide is a labelled panel of nested blocks (validated recursively, like `tabs`/`report`), one visible at a time with prev/next + dot navigation. A single slide renders without chrome. |
| Layout | `tabs` | local tab switch; nested blocks validated recursively |

**Aliases.** For producer convenience the documented synonyms `text`→`markdown`,
`table`→`data_table`, `source_list`→`citations`, `interactive_form`→`controls`
and `execution_timeline`→`timeline` are normalized to their canonical block in
`normalizeBlockAlias` before validation, so the renderer only ever sees canonical
types. The website-style family has matching synonyms: `stat`/`stats`→`stat_hero`,
`progress`/`meter`→`gauge`, `comparison`→`comparison_grid`,
`leaderboard`/`ranking`→`ranked_list`, `badges`→`badge_row` and
`slides`→`carousel`.

**Field-name synonyms** are normalized the same way, *after* the type alias, so a
producer is not punished for naming a field naturally. `normalizeBlockFields`
rewrites: `content`→`markdown` (markdown/callout/details), a scalar `text`→
`markdown` on those same prose types (observed producer output — scoped away from
`heading`, which legitimately owns a `text` field), `content`/`code`/`source`→
`diagram` (mermaid), `variant`→`tone` (callout, when the value is a valid tone),
`items`→`sources` and `name`→`title` (citations), string `columns` + positional
array `rows`→typed table columns/records (`data_table`), `note`→`hint`
(metric cards), and common `timeframe` intervals (`1Y`, `YTD`, `MAX`, `1D`,
`90d`, `3mo`, …) onto a supported `financial_chart` timeframe, and `steps`→
`stages` for a `workflow`. It also coerces observed producer shapes that the
strict schema would otherwise reject whole (each degrades only its own block):
`key`/`name`→item `label` (`key_value`), `points`/`values`→chart `data` with
`{x,y}` / `{value}` point objects coerced to tuples/scalars and `labels`→
`categories` (`chart`), `ticker`/`instrument`→`symbol` and `interval`/`range`→
`timeframe` plus chart-type synonyms (`financial_chart`), and node
`name`/`title`→`label` / edge `source`/`target`→`from`/`to` (`diagram`,
`node_graph`). A value that is not itself valid is
left untouched, so an unknown tone still falls back to the schema default rather
than hard-failing.

**Mermaid repair.** Mermaid is producer-authored text, and Mermaid v12 rejects
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



`splitResponseSegments` splits prose vs. `eclipse-response` fences.
`decodeResponseFence(source, settled)` distinguishes:
- `ok` — valid JSON → validated response.
- `empty` — whitespace body → render nothing.
- `incomplete` — a JSON **syntax** error while the turn is still streaming → a
  "composing" placeholder (never rendered as a validated object).
- `malformed` — a syntax error on a **settled** turn → an explicit diagnostic.

## 4. The renderer (`src/components/response/response-view.tsx`)

An explicit **registry** (`REGISTRY`: block type → component), not a conditional
chain. Adding a block = add its schema + one registry entry; the chat renderer is
untouched.

Every block is wrapped in `BlockBoundary` (a React error boundary), so a chart
failure cannot destroy the surrounding answer. The chart component
(`response-chart.tsx`) is the **only** place ECharts is imported, and it is loaded
via `next/dynamic({ ssr: false })` so the ~1 MB library is fetched only when a
chart actually renders. `MermaidBlock` is imported **statically**: it lazy-loads
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

### Theming (light and dark)

Blocks are theme-aware. The app switches scheme by toggling the `dark` class on
`<html>`, and the block renderers follow the **same signal** the charts already
use (`lib/chart/providers/eclipse-provider.ts`), via the shared
`hooks/use-dark-scheme.ts` hook. `mermaid-block.tsx` observes that class and
re-initialises Mermaid with `theme: 'dark'` or `'default'` so a diagram is never
rendered on a mismatched background; `response-chart.tsx` rebuilds its ECharts
option when the scheme flips so axis/legend ink stays legible;
`diagram-block.tsx` and `node-graph-block.tsx` draw node labels with
`currentColor` so they inherit the active foreground instead of a hardcoded
light-mode fill.

### Chart & diagram presentation

Every visual surface uses the frosted-glass system: the ECharts canvas, the
Mermaid/diagram/node-graph SVGs and the loading skeletons all sit in
`.glass-card-subtle` containers rather than flat `border + bg-accent` fills.
Charts are **smooth and consistent**: `chart-option.ts` sets `animation` with a
`cubicOut` easing, smooth lines, `borderRadius` rounded bars, a translucent
gradient under area series, soft dashed gridlines and theme-aware axis/legend
ink (zrender cannot parse `oklch`, so ink is concrete `rgba`).

The frosted **tooltip** recipe (translucent tint, `appendTo: 'body'`, 18px blur,
rounded shadow) lives once in `baseChartOption()`; `mergeChartOption()` combines
it with the block's own `trigger`/`valueFormatter`. A plain spread would let the
bare block tooltip clobber the glass chrome — that regression is why the merge is
a named, tested helper.

### Integration point

`components/chat/markdown.tsx` `Block`'s `case 'code'` checks the fence language:
`eclipse-response` → `<ResponseFence>` → `<ResponseView>`; anything else is a
normal code block. `Markdown` gained a `streaming` prop, threaded from
`chat-history.tsx`'s `AssistantContent`, so an in-progress fence shows the
composing placeholder.

## 5. Security posture

- **No execution.** Blocks are structured JSON only. There is no path from a
  model response to `eval`, `Function`, raw HTML, or a dynamic component import.
- **Registry allowlist.** Only registered types render; unknown types degrade.
- **URL safety.** Citations and artifact links use the same external-link policy
  as Markdown (`noopener noreferrer`) and are **scheme-restricted to `http(s)`**
  in the contract — bare `z.string().url()` accepts `javascript:`/`data:`, which
  would be an XSS vector once rendered as an `href`.
- **Icon allowlist.** Infographic/action `icon` values are semantic keys resolved
  against `lib/response/icons.ts`; an unknown key degrades to a neutral default.
  The model never names a component or an import path.
- **Actions are proposals.** `action_group` only composes a follow-up prompt and
  re-enters the existing agent loop; it cannot call a backend function, and the
  card is labeled "Proposed" until the user runs one.
- **Resource limits** bound render cost (see §3).
- **No fabricated data.** The contract has an explicit `unavailable` state; the
  renderer shows it as a chip rather than a value. The engine never fills gaps.

## 6. Verification

- `src/lib/response/contract.test.ts` — envelope, per-block degradation, unknown
  types, version warnings, nesting, totals.
- `src/lib/response/contract-blocks.test.ts` — the new block types, the spec-name
  aliases, link scheme restrictions, the icon allowlist.
- `src/lib/response/parse.test.ts` — segmentation, streaming vs. settled decode.
- `src/lib/response/chart-option.test.ts` — option building per chart type.
- `src/lib/response/diagram-layout.test.ts` — layering, unknown-edge handling,
  cycles.
- `src/components/response/render.test.tsx` — server-renders the **real**
  components (`react-dom/server`) to verify registry dispatch, mixed-block
  ordering, unknown-block isolation, `report` nesting, the streaming/malformed
  fences, action-group proposal semantics, safe citation links, and the
  `mermaid` fence rendering as a diagram (not a `<pre>` code block). Client-only
  canvas/interaction paths (ECharts, Mermaid's async render, click handlers) are
  exercised by the option/layout tests and the production build, not here.
- Full suite: `npx vitest run`, `npx tsc --noEmit`, `npm run build`, and the
  Prompt/ceiling Python tests (`test_memory_tools.py`,
  `test_phase_s_stabilization.py`).

## 7. Requirement traceability

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
| CHART-001 | General charts via ECharts | `chart-option.ts`, `response-chart.tsx` | chart-option.test.ts | Verified |
| CHART-002 | Lazy chart loading | `response-view.tsx` dynamic | tsc/build | Verified |
| DIAG-001 | Interactive diagrams (SVG) | `diagram-layout.ts`, `diagram-block.tsx` | diagram-layout.test.ts | Verified |
| DATA-001 | Interactive data table | `data-table-block.tsx` | tsc | Verified |
| DATA-002 | Metric grid + unavailable state | `blocks.tsx` | contract.test.ts | Verified |
| STREAM-001 | Streaming-aware partial decode | `parse.ts` | parse.test.ts | Verified |
| AGENT-001 | Producer contract (prompt guidance) | `python/harness/prompts.py` | prompt-ceiling pins in `test_memory_tools.py` + `test_phase_s_stabilization.py` | Verified |
| SEC-001 | No code execution from model output | whole engine | code review | Verified |
| INT-001 | Both chat surfaces render blocks | `markdown.tsx` + `chat-history.tsx` | tsc | Verified |
| INT-002 | Persistence/reopen via existing message store | `Message.content` | by construction | Verified |
| PLAN-001 | Deterministic visualization planner (Markdown → blocks) | `lib/response/planner.ts` + `chat-history.tsx` | planner.test.ts | Verified |
| INT-003 | Backend-driven interaction controls | `controls-block.tsx` + `onFollowup` in both surfaces | contract-extended.test.ts + tsc | Verified |
| ART-001 | Artifact persistence (existing Artifact Center) | `response-actions.tsx` → `registerArtifact` | build/tsc | Verified |
| EXP-001 | JSON / CSV / PNG / PDF export | `lib/response/export.ts`, `response-actions.tsx`, `data-table-block.tsx` | export.test.ts | Verified |
| DIAG-002 | Mermaid (sequence/ER/class/gantt/…) | `mermaid-block.tsx` (lazy, strict) — via `mermaid` block and chat ```mermaid fence | build | Verified |
| CHART-003 | Financial (candlestick/OHLCV) chart block | `financial-chart.tsx` (reuses `ChartWidget`) | build/tsc | Verified |
| REND-005 | Per-response export + save actions | `response-actions.tsx` | build/tsc | Verified |
| BLOCK-001 | `stepper`, `infographic`, `report`, `action_group`, `artifact` blocks | `contract.ts` + `rich-blocks.tsx` | contract-blocks.test.ts | Verified |
| BLOCK-002 | `node_graph` selectable graph (reuses layout engine) | `node-graph-block.tsx` | build/tsc | Verified |
| BLOCK-003 | Spec-name aliases normalized to canonical blocks | `contract.ts` `normalizeBlockAlias` | contract-blocks.test.ts | Verified |
| BLOCK-004 | Icon-driven connected `workflow` block (expandable stages, follow-up) | `contract.ts` + `rich-blocks.tsx` (`WorkflowBlock`) | contract-blocks.test.ts + render.test.tsx | Verified |
| BLOCK-005 | Website-style visual blocks: `stat_hero`, `gauge`, `comparison_grid`, `ranked_list`, `badge_row`, `carousel` | `contract.ts` + `visual-blocks.tsx` + `response-view.tsx` REGISTRY | contract-blocks.test.ts + render.test.tsx | Verified |
| BLOCK-006 | `carousel` nests blocks (recursively validated like `tabs`/`report`) | `contract.ts` `parseResponsePayload`/`parseNestedBlocks` | contract-blocks.test.ts + render.test.tsx | Verified |
| SEC-002 | Citation/artifact links restricted to http(s) | `contract.ts` `httpUrl` | contract-blocks.test.ts | Verified |
| SEC-003 | Semantic icon allowlist (no component/import from model) | `lib/response/icons.ts` | contract-blocks.test.ts | Verified |

## 8. Known limitations (honest)

These remain true of the shipped system:

1. **Graph editing — not offered.** `diagram`, `mermaid` and `node_graph` are
   read-only visualizations (a `node_graph` is *selectable* — a node reveals its
   `detail` and the view zooms/pans — but the contract declares no edit
   operations, so there is no graph editor). React Flow is deliberately not a
   dependency; the deterministic `diagram-layout` engine drives both `diagram`
   and `node_graph`. Editing is out of scope until explicitly authorized.
2. **PDF chart embedding** — the PDF embeds charts that are currently mounted
   (captured via the ECharts instance registry). A chart that is scrolled away /
   unmounted, or a `financial_chart`, is listed in an "Export notes" appendix
   rather than embedded.
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

