---
title: Interactive Response Engine
status: Current
last-verified: 2026-10-10
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
| | `diagram` | flowchart, dependency, state — native SVG |
| | `timeline` | ordered events with tone dots |
| | `citations` | numbered sources with host/timestamps |
| Layout | `tabs` | local tab switch; nested blocks validated recursively |

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
- **URL safety.** Citations use the same external-link policy as Markdown
  (`noopener noreferrer`, no `javascript:` schemes — the contract rejects
  non-URL `url` values).
- **Resource limits** bound render cost (see §3).
- **No fabricated data.** The contract has an explicit `unavailable` state; the
  renderer shows it as a chip rather than a value. The engine never fills gaps.

## 6. Verification

- `src/lib/response/contract.test.ts` — envelope, per-block degradation, unknown
  types, version warnings, nesting, totals.
- `src/lib/response/parse.test.ts` — segmentation, streaming vs. settled decode.
- `src/lib/response/chart-option.test.ts` — option building per chart type.
- `src/lib/response/diagram-layout.test.ts` — layering, unknown-edge handling,
  cycles.
- Full suite: `npx vitest run` (2563 passing at time of writing), `npx tsc
  --noEmit` clean, `python -m pytest tests/test_prompt_segments.py` passing.

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
| DIAG-002 | Mermaid (sequence/ER/class/gantt/…) | `mermaid-block.tsx` (lazy, strict) | build | Verified |
| CHART-003 | Financial (candlestick/OHLCV) chart block | `financial-chart.tsx` (reuses `ChartWidget`) | build/tsc | Verified |
| REND-005 | Per-response export + save actions | `response-actions.tsx` | build/tsc | Verified |

## 8. Known limitations (honest)

These remain true of the shipped system:

1. **React Flow / editable graphs** — diagrams are read-only by design (`diagram`,
   `mermaid`). Node-graph *editing* is not offered; the contract does not declare
   it and the spec says editing must be explicitly authorized.
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

