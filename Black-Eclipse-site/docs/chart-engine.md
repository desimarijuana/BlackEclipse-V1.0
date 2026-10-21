# The chart engine — Eclipse draws its charts with Python

**Status:** Active. **Last verified:** 2026-10-20.

Eclipse renders every chart with the Python runtime's chart engine: a validated
**chart spec** goes in, `matplotlib` draws a transparent PNG, and the picture is
recorded in the Artifact Center. There is no browser charting library in the
render path.

This document is the canonical description of that engine **and** of the plan
that retires ECharts.

---

## 1. What the engine is for

The **chat's** charts are drawn by this engine, and **only** by this engine.
A `chart` block in an answer is turned into a picture by the runtime
(matplotlib) and shown as an artifact. The chat has no ECharts path: a chart
in a chat answer is never a live canvas.

**The rest of the application is NOT part of this.** The journal, the
portfolio, the dashboard, the backtest screen, the economics and fundamentals
panels, the workspace widgets, the price chart, the Investor Eye map and the
relationship graphs all stay on ECharts. They draw from live data at
interactive rates (a price chart that redraws on every tick, a map the user
hovers), which a server-drawn picture cannot serve.

## 2. The contract

### 2.1 Two forms, one vocabulary

A chat chart arrives in one of two forms, and the engine draws both:

| Form | The block carries | The engine draws |
|---|---|---|
| **simple** | `chartType` + `series` | that kind of chart (line, bar, pie, heatmap, candlestick, …) |
| **scene** | `panels` → `marks` | exactly the marks you wrote |

The scene is what makes **any chart** possible. A fixed list of kinds can only
draw the charts someone thought of; a scene is compositional, so a violin, a
box plot, a Gantt, a funnel, a ridgeline, an error-bar chart or a dual-axis
chart is a **composition of the primitives** — not a new kind that has to be
invented for it.

**The mark vocabulary** (each mark carries its own data and styling):

`line` · `area` · `bar` · `scatter` · `band` · `rule` · `label` · `box` ·
`violin` · `histogram` · `errorbar` · `heatmap` · `pie` · `donut` ·
`candlestick` · `waterfall` · `ridge` · `stem`

A mark may set: `name` (the legend), `y` / `x` / `values` / `lower` /
`upper` / `sizes` / `matrix` / `labels` / `rowLabels` / `colLabels`, `color`,
`alpha`, `width`, `style` (`solid` / `dashed` / `dotted`), `fill`, `label`,
`yAxis` (`left` / `right` — a dual-axis chart), `stack` and `bins`.

A panel may set: `title`, `xLabel`, `yLabel`, `valueFormat`, `logScale` and
`height` (its share of the figure). A scene is up to 6 panels.

### 2.2 The spec

`python/harness/charts/spec.py` — `ChartSpec` (pydantic, `extra="forbid"`).

| Field | Meaning |
|---|---|
| `kind` | `line`, `area`, `bar`, `stackedBar`, `pie`, `donut`, `scatter`, `histogram`, `heatmap`, `candlestick`, `waterfall`, `radar`, `gauge`, `treemap`, `scene` |
| `panels` | The scene: panels of marks (see above) |
| `title` / `subtitle` / `footnote` / `source` | The text around the picture |
| `xLabel` / `yLabel` | The axis labels |
| `categories` | The x-axis labels (dates, tickers, periods) |
| `series[]` | `{ name, data[], color?, style?, band?, colors? }` — `data` holds `null` for a **missing reading** (never `0`) |
| `labels` / `values` / `colors` | A pie/donut's slices and their colours |
| `points[]` | A scatter's `{ x, y, label?, size?, color? }` |
| `matrix` / `rowLabels` / `colLabels` | A heatmap's cells and its two label axes |
| `candles[]` | A candlestick's `{ open, high, low, close }` |
| `referenceLines[]` / `highlights[]` | Named horizontal lines; shaded category spans |
| `volumeData[]` | An optional volume pane under the chart |
| `valueFormat` | How the value axis is written (`percent`, `currency`, `compact`, `r`, `number`) |
| `theme` | `eclipse-dark` (default) or `eclipse-light` |

A per-kind validator states what each kind needs: a pie needs one label per
value, a heatmap needs rectangular rows, a line needs a series, a scene needs
at least one mark. A spec that does not satisfy its kind is refused with the
missing part named.

The wire shape is **camelCase** (like every other harness model); the
snake_case field names stay valid too.

### 2.3 The theme

`python/harness/charts/theme.py`. The background is **transparent** so the
figure sits on the frosted glass card without hiding the frost; the ink is
light because the surface behind it is dark. The palette is the app's:
`#0ea5e9` sky, `#a78bfa` violet, `#22c55e` green, `#f59e0b` amber,
`#e11d48` rose, `#94a3b8` muted ink. The light theme is a real theme,
not an inversion, because the app has a light mode.

### 2.4 The honesty rules

* A figure is always `computed`, never evidence. `RenderedChart.to_dict()`
  emits `isEvidence: false` and there is no field that can change it
  (ADR-H123).
* The renderer draws what the spec says and **nothing else** — it never
  invents a point, a mean, an axis or a scale.
* A missing `matplotlib` is a named refusal (`CHART_RENDER_UNAVAILABLE`), not
  an empty image.
* The picture's identity is the digest of its **spec** (`spec_digest`), so the
  same spec always draws the same picture.

## 3. The surfaces

| Surface | Entry point |
|---|---|
| The agent | the `python_chart` tool (`python/harness/charts/tools.py`) — registered on the one tool registry and on the chat agent's allowlist |
| The front door | `POST /api/harness/charts` → `python/harness/routers/charts.py` → `POST /charts/render` (operator-gated) |
| The browser | `src/lib/harness/charts.ts` (`renderChart`) + `src/components/charts/python-chart.tsx` |
| The **chat's chart blocks** | `src/lib/response/chart-spec.ts` (block -> spec) + `src/components/response/response-chart.tsx` (the picture) |
| The drawn-chart registry | `src/lib/response/chart-registry.ts` (block id -> artifact id, for PNG/PDF export) |

The picture is returned as an **artifact**, not as bytes: the browser fetches
it back through `/api/artifacts/<id>/download`, so a chart is discoverable,
downloadable and versioned.

```
chart block ──▶ chart-spec.ts ──▶ spec ──▶ python_chart tool / /charts/render
                                                        │
                                                        ▼
                                            matplotlib ──▶ PNG ──▶ Artifact Center
                                                        │
                                                        ▼
                                      browser ◀── /api/artifacts/<id>/download
```

### 3.1 The picture is hoverable

A PNG cannot be hovered. The engine therefore returns, with the picture, an
**interaction map**: the picture's own pixel geometry (the axes' box) and, per
category, its x position and each series' value there
(`python/harness/charts/interaction.py`).

The browser draws the pointer experience over the picture from that map: a
crosshair at the nearest category and a tooltip with the values
(`src/components/charts/chart-hover.tsx`). Because the map is in the picture's
pixels and the browser converts it to percentages, the interaction survives any
display size — the picture is never stretched, and the crosshair still lands on
the right column.

The map is a convenience, never a claim: the values it carries are the same
values the picture was drawn from, and a gap stays a gap (no value at all).

### 3.2 The picture's size and its legibility

The chat draws at **1000×560** and shows it at its natural aspect, left
aligned, capped at 860 px wide (`object-contain`, no fixed height), inside a
card that **shrinks to the picture** (`w-fit`) rather than spanning the
column. The old `w-full` + a fixed `maxHeight` stretched the picture; now it
is never distorted, and the focus view simply shows the same picture larger.

Two rules keep the picture readable:

* **The text is a fraction of the picture, not of the screen.** The engine
  draws in fewer inches at a higher resolution (`DRAW_DPI = 150`), so the
  labels and strokes scale with the picture — a chart shown at 860 px has
  legible labels whether it was drawn at 720 px or at 1400 px.
* **Crowded axes are thinned, never faked.** When a category axis carries
  more than ~12 labels, the engine keeps every Nth label (and turns long
  ones, because a row of `2026-07-01` strings cannot share a line). The DATA is
  never thinned — only the labels are.

## 4. What the user gets

| | The chat's chart |
|---|---|
| Engine | the Python chart engine (matplotlib) in the runtime |
| Interaction | hover + crosshair over the picture, from the engine's interaction map |
| Any chart | yes: the SCENE form draws any composition of the marks |
| Export | the artifact's bytes (PNG and PDF both embed the picture the user saw) |
| Provenance | always `computed`, never evidence |

What the rest of the app does is unchanged: ECharts, with its live hover,
crosshair and zoom.

## 5. Where the code lives

| Piece | Path |
|---|---|
| The spec | `python/harness/charts/spec.py` |
| The theme | `python/harness/charts/theme.py` |
| The renderer | `python/harness/charts/render.py` |
| The service (artifact) | `python/harness/charts/service.py` |
| The agent tool | `python/harness/charts/tools.py` |
| The route | `python/harness/routers/charts.py` |
| The browser client | `src/lib/harness/charts.ts` |
| The component | `src/components/charts/python-chart.tsx` |
| The front-door route | `src/app/api/harness/charts/route.ts` |
| The response-engine translation | `src/lib/response/chart-spec.ts` (a chart block → the engine's spec) |
| The response chart surface | `src/components/response/response-chart.tsx` |
| The chart registry | `src/lib/response/chart-registry.ts` |
| The scene (panels of marks) | `python/harness/charts/scene.py` + `scene_render.py` |
| The interaction map | `python/harness/charts/interaction.py` + `src/components/charts/chart-hover.tsx` |
| Tests | `python/tests/test_charts.py`, `python/tests/test_chart_scene.py`, `python/tests/test_chart_interaction.py`, `src/lib/harness/charts.test.ts`, `src/app/api/harness/charts/route.test.ts`, `src/lib/response/chart-spec.test.ts` |

The decision itself is **ADR-050** (`skills/ARCHITECT.md`, mirrored in
`docs/DECISIONS.md`).
