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
   string length 20 000.
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
| | `timeline` | ordered events with tone dots (alias `execution_timeline`) |
| | `citations` | numbered sources with host/timestamps (alias `source_list`) |
| Process | `stepper` | numbered steps with per-step status (pending/active/done/error) |
| | `infographic` | icon cards; `icon` is a semantic key resolved via `lib/response/icons.ts` |
| | `report` | multi-section container; section `blocks` validated recursively |
| Action | `action_group` | PROPOSED next steps; a click sends a follow-up prompt into the agent loop |
| | `artifact` | a reference to the existing Artifact Center, linked to its download route |
| Layout | `tabs` | local tab switch; nested blocks validated recursively |

**Aliases.** For producer convenience the documented synonyms `text`→`markdown`,
`table`→`data_table`, `source_list`→`citations`, `interactive_form`→`controls`
and `execution_timeline`→`timeline` are normalized to their canonical block in
`normalizeBlockAlias` before validation, so the renderer only ever sees canonical
types.

**Field-name synonyms** are normalized the same way, *after* the type alias, so a
producer is not punished for naming a field naturally. `normalizeBlockFields`
rewrites: `content`→`markdown` (markdown/callout/details), `content`/`code`→
`diagram` (mermaid), `variant`→`tone` (callout, when the value is a valid tone),
`items`→`sources` and `name`→`title` (citations), string `columns` + positional
array `rows`→typed table columns/records (`data_table`), `note`→`hint`
(metric cards), and common `timeframe` intervals (`1Y`, `YTD`, `MAX`, `1D`, …)
onto a supported `financial_chart` timeframe. A value that is not itself valid is
left untouched, so an unknown tone still falls back to the schema default rather
than hard-failing.

### Parsing (`src/lib/response/parse.ts`)

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
chart actually renders.

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
| AGENT-001 | Producer contract (prompt guidance) | `python/harness/prompts.py` | test_prompt_segments.py | Verified |
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

