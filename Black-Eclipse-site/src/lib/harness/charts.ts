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
  | "histogram" | "heatmap" | "candlestick" | "waterfall" | "radar";

export type ChartTheme = "eclipse-dark" | "eclipse-light";

export interface ChartSeries {
  name: string;
  data: Array<number | null>;
  color?: string;
  style?: "line" | "area" | "bar" | "step" | "scatter";
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

export interface ChartSpec {
  kind: ChartKind;
  title?: string;
  subtitle?: string;
  footnote?: string;
  source?: string;
  xLabel?: string;
  yLabel?: string;
  categories?: string[];
  series?: ChartSeries[];
  labels?: string[];
  values?: number[];
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
  width?: number;
  height?: number;
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
