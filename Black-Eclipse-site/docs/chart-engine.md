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

The **chat's** charts can be drawn by two engines, and the user picks:

* **`eclipse`** (the default) — the interactive ECharts chart: a live canvas
  with a crosshair, a hover tooltip and a legend.
* **`python`** — the picture the Python chart engine (matplotlib) draws in the
  runtime, fetched back as an artifact.

**The rest of the application is NOT part of this.** The journal, the
portfolio, the dashboard, the backtest screen, the economics and fundamentals
panels, the workspace widgets, the price chart, the Investor Eye map and the
relationship graphs all stay on ECharts. Only the `chart` blocks inside a
chat answer have a second engine.

Why the chat gets one: a chat answer is the one surface where the CHART ITSELF
is the payload — the model authored it, it travels in the response contract,
and it is exported, saved and re-shared. Giving that one surface a second
engine (a picture drawn by the same code that draws the agent's own figures)
is useful without touching anything else.

## 2. The contract

### 2.1 The spec

`python/harness/charts/spec.py` — `ChartSpec` (pydantic, `extra="forbid"`).

| Field | Meaning |
|---|---|
| `kind` | `line`, `area`, `bar`, `stackedBar`, `pie`, `donut`, `scatter`, `histogram`, `heatmap`, `candlestick`, `waterfall`, `radar`, `gauge`, `treemap` |
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
value, a heatmap needs rectangular rows, a line needs a series. A spec that
does not satisfy its kind is refused with the missing part named.

The wire shape is **camelCase** (like every other harness model); the
snake_case field names stay valid too.

### 2.2 The theme

`python/harness/charts/theme.py`. The background is **transparent** so the
figure sits on the frosted glass card without hiding the frost; the ink is
light because the surface behind it is dark. The palette is the app's:
`#0ea5e9` sky, `#a78bfa` violet, `#22c55e` green, `#f59e0b` amber,
`#e11d48` rose, `#94a3b8` muted ink. The light theme is a real theme,
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

## 3. The surfaces

| Surface | Entry point |
|---|---|
| The agent | the `python_chart` tool (`python/harness/charts/tools.py`) — registered on the one tool registry and on the chat agent's allowlist |
| The front door | `POST /api/harness/charts` → `python/harness/routers/charts.py` → `POST /charts/render` (operator-gated) |
| The browser | `src/lib/harness/charts.ts` (`renderChart`) + `src/components/charts/python-chart.tsx` |
| The **chat's chart blocks** | `src/lib/response/chart-spec.ts` (block → spec) + `src/components/response/response-chart.tsx` (the engine toggle) |
| The drawn-chart registry | `src/lib/response/chart-registry.ts` (both the live ECharts instance and the artifact id) |

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

## 4. What the two engines mean for the user

| | ECharts (`eclipse`) | Python (`python`) |
|---|---|---|
| Interaction | hover tooltip, crosshair, legend toggling | a flat picture |
| Fidelity | the app's established look | the agent's own figures |
| Export | canvas capture (`getDataURL`) | the artifact's bytes |
| Cost | the ECharts bundle (already there) | a runtime round trip |

The choice is a **user preference**, remembered across answers
(`src/lib/response/chart-engine.ts`, `be_chat_chart_engine`), and the toggle
sits on the chart itself. The export helpers serve both: the drawn picture is
an artifact, the interactive chart is a live canvas.

A lossy *mapping* is never silent: a block type the engine cannot draw
exactly (`treemap`, `sunburst`, `funnel`, `gauge`) is drawn as the closest
honest shape and the note appears under the picture.

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
| The response chart surface | `src/components/response/response-chart.tsx` (the engine toggle + both paths) |
| The engine preference | `src/lib/response/chart-engine.ts` |
| The chart registry (both engines) | `src/lib/response/chart-registry.ts` |
| Tests | `python/tests/test_charts.py`, `src/lib/harness/charts.test.ts`, `src/app/api/harness/charts/route.test.ts`, `src/lib/response/chart-spec.test.ts` |

The decision itself is **ADR-050** (`skills/ARCHITECT.md`, mirrored in
`docs/DECISIONS.md`).
