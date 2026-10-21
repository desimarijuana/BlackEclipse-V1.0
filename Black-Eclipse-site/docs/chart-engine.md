# The chart engine — Eclipse draws its charts with Python

**Status:** Active. **Last verified:** 2026-10-20.

Eclipse renders every chart with the Python runtime's chart engine: a validated
**chart spec** goes in, `matplotlib` draws a transparent PNG, and the picture is
recorded in the Artifact Center. There is no browser charting library in the
render path.

This document is the canonical description of that engine **and** of the plan
that retires ECharts.

---

## 1. Why the engine exists

The old path drew charts in the browser with ECharts. That put the entire
chart vocabulary in TypeScript: a deeply nested *option object* per chart, a
600 KB dependency in the bundle, and a rendering engine whose behaviour could
only be verified by a browser.

Moving the drawing to Python buys three things:

1. **One chart vocabulary, shared by the agent and the UI.** The model, a
   dashboard widget and a chat block all describe a chart the same way. There
   is no second "chart option" format to keep in sync.
2. **A spec is data, so it can be checked.** A chart spec carries numbers,
   names and colours — never a callback, a URL or a path. A malformed chart is
   a *refusal* with the missing part named, not a broken picture.
3. **The chart joins the rest of the produced artifacts.** A chart is
   downloadable, versioned and re-shareable like any document the agent
   produced, instead of pixels that exist only in a React tree.

The engine does **not** reimplement the analysis sandbox. Computation still
happens in the sandbox (`python/harness/code/`, ADR-H123); the chart engine
only draws.

---

## 2. The contract

### 2.1 The spec

`python/harness/charts/spec.py` — `ChartSpec` (pydantic, `extra="forbid"`).

| Field | Meaning |
|---|---|
| `kind` | `line`, `area`, `bar`, `stackedBar`, `pie`, `donut`, `scatter`, `histogram`, `heatmap`, `candlestick`, `waterfall`, `radar` |
| `title` / `subtitle` / `footnote` / `source` | The text around the picture |
| `xLabel` / `yLabel` | The axis labels |
| `categories` | The x-axis labels (dates, tickers, periods) |
| `series[]` | `{ name, data[], color?, style? }` — `data` holds `null` for a **missing reading** (never `0`) |
| `labels` / `values` | A pie/donut's slices, a radar's axes, a waterfall's values |
| `points[]` | A scatter's `{ x, y, label?, size?, color? }` |
| `matrix` / `rowLabels` / `colLabels` | A heatmap's cells and its two label axes |
| `candles[]` | A candlestick's `{ open, high, low, close }` |
| `stacked` / `normalized` / `smooth` / `showPoints` | How the series are drawn |
| `theme` | `eclipse-dark` (default) or `eclipse-light` |
| `width` / `height` | The picture size in pixels (320–2400) |

A per-kind validator states what each kind needs: a pie needs one label per
value, a heatmap needs rectangular rows, a line needs a series. A spec that
does not satisfy its kind is refused with the missing part named.

### 2.2 The theme

`python/harness/charts/theme.py`. The background is **transparent** so the
figure sits on the frosted glass card without hiding the frost; the ink is
light because the surface behind it is dark. The palette is the app's:
`#0ea5e9` sky, `#a78bfa` violet, `#22c55e` green, `#f59e0b` amber,
`#e11d48` rose, with `#94a3b8` muted ink. The light theme is a real theme,
not an inversion, because the app has a light mode.

### 2.3 The honesty rules

* A figure is always `computed`, never evidence. `RenderedChart.to_dict()`
  emits `isEvidence: false` and there is no field that can change it
  (ADR-H123).
* The renderer draws what the spec says and **nothing else** — it never
  invents a point, a mean, an axis or a scale.
* A missing `matplotlib` is a named refusal (`CHART_RENDER_UNAVAILABLE`), not
  an empty image.
* The picture's identity is the digest of its **spec** (`spec_digest`), so the
  same spec always draws the same picture.

---

## 3. The surfaces

| Surface | Entry point |
|---|---|
| The agent | the `python_chart` tool (`python/harness/charts/tools.py`) — registered on the one tool registry |
| The front door | `POST /api/harness/charts` → `python/harness/routers/charts.py` → `POST /charts/render` (operator-gated) |
| The browser | `src/lib/harness/charts.ts` (`renderChart`) + `src/components/charts/python-chart.tsx` |

The picture is returned as an **artifact**, not as bytes: the browser fetches
it back through `/api/artifacts/<id>/download`, so a chart is discoverable,
downloadable and versioned.

```
spec ──▶ python_chart tool ─┐
                            ├─▶ render_spec ─▶ matplotlib ─▶ PNG ─▶ Artifact Center
spec ──▶ /charts/render ────┘                                              │
                                                                           ▼
                                              browser ◀── /api/artifacts/<id>/download
```

---

## 4. Retiring ECharts — the plan

ECharts (`echarts@^6.1.0`) and `echarts-gl@^2.1.0` are **leaving the app**.
`recharts@^3.8.1` is already dead weight (zero imports) and goes with them.

The migration is deliberately **not** a dual engine: every surface moves to
the Python engine, and ECharts is removed from `package.json` once the last
surface has moved. The order below is the order of work.

### 4.1 The inventory

| # | Surface | File | Replacement | Difficulty |
|---|---|---|---|---|
| 1 | Chat response charts | `src/lib/response/chart-option.ts`, `src/components/response/response-chart.tsx` | The response block asks the engine for the picture; the block renders the artifact | Medium — the block contract keeps its shape, the renderer changes |
| 2 | Journal charts (8) | `src/components/journal/charts/` | One `<PythonChart>` per chart, fed by the journal's existing data hooks | Medium |
| 3 | Portfolio analytics | `src/components/screens/portfolio/widgets.tsx` | NAV-vs-benchmark line, allocation donut, risk gauge → `gauge` is not a chart kind yet: it becomes a `bar` with a threshold line | Medium |
| 4 | Backtest | `src/components/screens/backtest/backtest-screen.tsx` | Equity curve + drawdown area | Easy |
| 5 | Dashboard widgets | `src/lib/dashboard/chart-widgets.tsx`, `widgets.tsx` | Price/EMA lines, RSI, macro series | Easy |
| 6 | Market heatmap | `src/lib/dashboard/heatmap-widget.tsx` | A treemap is **not** a chart kind: it becomes a `bubble` (a scatter with a size) or a ranked bar | Hard — the treemap's area encoding is lost |
| 7 | Economics panel | `src/components/screens/economics/panel.tsx` | Multi-series macro lines + CSV/PNG export | Easy |
| 8 | TradingView-style price chart | `src/components/screens/tradingview-chart.tsx` | A `candlestick` chart; the **crosshair/zoom/tooltip** are gone | Hard — the interactive parts of ECharts have no Python equivalent |
| 9 | Price chart widget + drawings | `src/components/chart/chart-widget.tsx`, `src/lib/chart/` | The `ChartProvider` contract gets a `python` provider; the drawing overlay (a browser canvas over a live chart) is **retired** | Hard |
| 10 | Investor Eye map | `src/lib/investor-eye/map-echarts.ts`, `src/components/investor-eye/world-map.tsx` | A static 2D map is drawn in Python (geopandas is **not** installed — the country geometry has to come from the app's own geo data) | Very hard — the 3D globe has no Python counterpart in this stack |
| 11 | Force graphs | `src/components/investor-eye/graph-panel.tsx`, `src/components/screens/skills/learning-graph.tsx` | A networkx/igraph layout drawn in Python | Hard — the layout is a layout |
| 12 | Heatmap widget, correlation matrix | `src/components/screens/portfolio/widgets.tsx` | The `heatmap` kind | Easy |

### 4.2 What is genuinely lost

This is the honest cost, and it is why the plan is staged rather than a single
commit:

* **No hover tooltips, no crosshair, no zoom/brush, no legend toggling.** A
  Python figure is a picture. Anything that needed a live pointer needs a
  different design (a table beside the picture, or a second, simpler picture).
* **The 3D globe and the force graph have no counterpart** in the current
  Python stack. They are the last two surfaces and they need their own
  decisions (a static 2D map + a network layout, or keeping one WebGL
  library for those two views only).
* **Every chart costs a round trip.** A widget that re-draws on every scroll
  or every tick must be debounced and cached by spec digest.

### 4.3 What is gained

* One chart vocabulary for the model, the chat and the widgets.
* A chart is an artifact: downloadable, versioned, shareable, recorded in the
  run ledger.
* The chart engine is the same code path for the agent's figures and the
  user's widgets, so a picture can never mean two different things.
* The browser bundle loses the charting library.

---

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
| Tests | `python/tests/test_charts.py`, `src/lib/harness/charts.test.ts`, `src/app/api/harness/charts/route.test.ts` |

The decision itself is **ADR-050** (`skills/ARCHITECT.md`, mirrored in
`docs/DECISIONS.md`).
