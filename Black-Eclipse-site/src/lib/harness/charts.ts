// The chart engine's browser client.
//
// Eclipse draws its charts with Python (matplotlib) in the runtime. This
// module is the browser's half of that contract: it describes a chart (data
// only — never code, never a callback) and asks the front door to draw it.
//
// The picture comes back as an ARTIFACT, not as bytes: the chart is recorded
// in the Artifact Center, so it can be downloaded, versioned and re-shared
// like any other produced file. The browser then fetches it back through the
// artifact route.
//
// A chart is always `computed` — it is never evidence. That label is part of
// the contract, not a caption the UI adds.

export type ChartKind =
  | "line" | "area" | "bar" | "stackedBar" | "pie" | "donut" | "scatter"
  | "histogram" | "heatmap" | "candlestick" | "waterfall" | "radar"
  | "gauge" | "treemap"
  // The compositional form: panels of marks (any chart).
  | "scene";

export type ChartTheme = "eclipse-dark" | "eclipse-light";

export interface ChartBand {
  /** The lower edge of the range. `null` is a missing reading. */
  lower: Array<number | null>;
  /** The upper edge of the range. */
  upper: Array<number | null>;
}

export interface ChartSeries {
  name: string;
  data: Array<number | null>;
  color?: string;
  style?: "line" | "area" | "bar" | "step" | "scatter";
  /** An optional range drawn around the series (a forecast band). */
  band?: ChartBand;
  /** Per-point colours, in the same order as `data` (a sign, a slice). */
  colors?: Array<string | null>;
  /** Draw the series as a dashed line (a benchmark, a reference series). */
  dashed?: boolean;
}

/** One tile of a treemap: a name, a size (the area) and a colour. */
export interface ChartTile {
  name: string;
  value: number;
  color?: string;
  label?: string;
}

export interface ChartPoint {
  x: number;
  y: number;
  label?: string;
  size?: number;
  color?: string;
}

export interface ChartCandle {
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface ChartReferenceLine {
  label: string;
  value: number;
  color?: string;
  dashed?: boolean;
}

/** One drawn primitive of a scene. */
export interface ChartMark {
  type:
    | "line" | "area" | "bar" | "scatter" | "band" | "rule" | "label"
    | "box" | "violin" | "histogram" | "errorbar" | "heatmap" | "pie"
    | "donut" | "candlestick" | "waterfall" | "ridge" | "stem";
  name?: string;
  y?: Array<number | null>;
  x?: Array<number | null>;
  values?: Array<number | null>;
  lower?: Array<number | null>;
  upper?: Array<number | null>;
  sizes?: Array<number | null>;
  matrix?: number[][];
  labels?: string[];
  rowLabels?: string[];
  colLabels?: string[];
  color?: string;
  alpha?: number;
  width?: number;
  style?: "solid" | "dashed" | "dotted";
  fill?: boolean;
  label?: string;
  yAxis?: "left" | "right";
  stack?: string;
  bins?: number;
}

/** One panel of a scene: its own axes, its own marks. */
export interface ChartPanel {
  title?: string;
  xLabel?: string;
  yLabel?: string;
  marks: ChartMark[];
  valueFormat?: "percent" | "currency" | "compact" | "r" | "number";
  logScale?: boolean;
  height?: number;
}

export interface ChartSpec {
  kind: ChartKind;
  title?: string;
  subtitle?: string;
  /** A gauge's reading. */
  value?: number;
  /** A gauge's scale (100 by default). */
  gaugeMax?: number;
  /** A treemap's tiles. */
  tiles?: ChartTile[];
  footnote?: string;
  source?: string;
  xLabel?: string;
  yLabel?: string;
  categories?: string[];
  series?: ChartSeries[];
  labels?: string[];
  values?: number[];
  /** Per-slice colours for a pie/donut, in the same order as `values`. */
  colors?: Array<string | null>;
  points?: ChartPoint[];
  matrix?: number[][];
  rowLabels?: string[];
  colLabels?: string[];
  candles?: ChartCandle[];
  stacked?: boolean;
  normalized?: boolean;
  smooth?: boolean;
  showPoints?: boolean;
  theme?: ChartTheme;
  /** How the value axis is written (the engine draws numbers). */
  valueFormat?: "percent" | "currency" | "compact" | "r" | "number";
  /** The currency symbol used by the `currency` value format. */
  currencySymbol?: string;
  /** Named horizontal lines drawn across the chart (an entry, a stop). */
  referenceLines?: ChartReferenceLine[];
  /** Shaded spans of the category axis (a recession, a regime). */
  highlights?: Array<{ start: number; end: number; color?: string; label?: string }>;
  /** A compositional chart: panels of marks (any chart). */
  panels?: ChartPanel[];
  /** An optional volume pane under the chart (a price chart's volume bars). */
  volumeData?: Array<number | null>;
  /** The volume bars' colours (one per bar). */
  volumeColors?: Array<string | null>;
  /** Draw the value axis on a log scale. */
  logScale?: boolean;
  width?: number;
  height?: number;
}

/** Where each category sits on the picture, so the browser can hover it. */
export interface ChartInteraction {
  width: number;
  height: number;
  plot: { left: number; right: number; top: number; bottom: number };
  columns: Array<{
    label: string;
    x: number;
    values: Array<{ name: string; value: number; color: string }>;
  }>;
}

export interface ChartFigure {
  kind: ChartKind;
  label: string;
  /** Always false: a picture is a computed artifact, never evidence. */
  isEvidence: false;
  artifact: string;
  artifactId?: string | null;
  sha256: string;
  bytes: number;
  width: number;
  height: number;
  theme: ChartTheme;
  title: string | null;
  series: Array<{ name: string; points: number }>;
  summary: string;
  /** Present when the picture can be hovered (a category axis). */
  interaction?: ChartInteraction;
}

export interface RenderedChart {
  figure: ChartFigure;
  artifact: {
    id: string | null;
    name: string;
    bytes: number;
    sha256: string;
    downloadUrl: string | null;
  };
}

/**
 * Draw a chart. The request is a SPEC — the runtime validates it and refuses
 * a malformed one with the missing part named.
 */
export async function renderChart(spec: ChartSpec): Promise<RenderedChart> {
  const res = await fetch("/api/harness/charts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
  });
  const body = (await res.json().catch(() => ({}))) as Partial<RenderedChart> & {
    status?: string;
    error?: string;
    detail?: { code?: string; message?: string } | string;
  };
  if (!res.ok) {
    const detail = body.detail;
    const message =
      typeof detail === "object" && detail && "message" in detail
        ? String(detail.message)
        : typeof detail === "string"
          ? detail
          : body.error ?? `the chart could not be drawn (${res.status})`;
    throw new Error(message);
  }
  if (!body.figure) throw new Error("the chart engine returned no figure");
  return {
    figure: body.figure,
    artifact: body.artifact ?? {
      id: null,
      name: body.figure.artifact,
      bytes: body.figure.bytes,
      sha256: body.figure.sha256,
      downloadUrl: null,
    },
  };
}
