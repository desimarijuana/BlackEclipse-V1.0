export interface CandleColors {
  up: string;
  down: string;
  neutral: string;
}

export interface LineColors {
  primary: string;
  series: string[];
}

export interface HeatmapColors {
  up: string;
  mid: string;
  down: string;
}

export interface ChartPalette {
  candles: CandleColors;
  lines: LineColors;
  heatmap: HeatmapColors;
}

export const DEFAULT_CHART_PALETTE: ChartPalette = {
  candles: { up: "#22c55e", down: "#ef4444", neutral: "#94a3b8" },
  // Colour is the DEFAULT: a multi-series chart drawn in a greyscale ramp makes
  // the reader work to tell one series from the next, and a chart the agent drew
  // for you should not look like a wireframe. These six hues are distinct, read
  // on both the dark and the light surface, and start with the app's own ocean
  // blue. Market direction keeps its conventional green / red pair.
  // "Black & white" is still one click away in Settings › General › Charts, and
  // a saved palette always wins over this default.
  lines: { primary: "#38bdf8", series: ["#38bdf8", "#fbbf24", "#a78bfa", "#fb7185", "#2dd4bf", "#e879f9"] },
  heatmap: { up: "#22c55e", mid: "#27272a", down: "#ef4444" },
};

export function normalizeChartColor(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const value = raw.trim().toLowerCase();
  if (/^#[0-9a-f]{6}$/.test(value)) return value;
  if (/^#[0-9a-f]{3}$/.test(value)) {
    return `#${value.slice(1).split("").map((digit) => digit + digit).join("")}`;
  }
  return null;
}

function normalizeCandles(raw: unknown): CandleColors {
  const value = raw && typeof raw === "object" && !Array.isArray(raw) ? raw as Record<string, unknown> : {};
  return {
    up: normalizeChartColor(value.up) ?? DEFAULT_CHART_PALETTE.candles.up,
    down: normalizeChartColor(value.down) ?? DEFAULT_CHART_PALETTE.candles.down,
    neutral: normalizeChartColor(value.neutral) ?? DEFAULT_CHART_PALETTE.candles.neutral,
  };
}

function normalizeLines(raw: unknown): LineColors {
  const value = raw && typeof raw === "object" && !Array.isArray(raw) ? raw as Record<string, unknown> : {};
  const series = Array.isArray(value.series) ? value.series : [];
  return {
    primary: normalizeChartColor(value.primary) ?? DEFAULT_CHART_PALETTE.lines.primary,
    series: DEFAULT_CHART_PALETTE.lines.series.map((fallback, index) => normalizeChartColor(series[index]) ?? fallback),
  };
}

function normalizeHeatmap(raw: unknown): HeatmapColors {
  const value = raw && typeof raw === "object" && !Array.isArray(raw) ? raw as Record<string, unknown> : {};
  return {
    up: normalizeChartColor(value.up) ?? DEFAULT_CHART_PALETTE.heatmap.up,
    mid: normalizeChartColor(value.mid) ?? DEFAULT_CHART_PALETTE.heatmap.mid,
    down: normalizeChartColor(value.down) ?? DEFAULT_CHART_PALETTE.heatmap.down,
  };
}

export type PaletteSection = "candles" | "lines" | "heatmap";

export function normalizeChartPalette(raw: unknown): ChartPalette {
  const value = raw && typeof raw === "object" && !Array.isArray(raw)
    ? raw as Record<string, unknown>
    : {};
  return {
    candles: normalizeCandles(value.candles),
    lines: normalizeLines(value.lines),
    heatmap: normalizeHeatmap(value.heatmap),
  };
}

export function normalizeSection(section: PaletteSection, raw: unknown) {
  if (section === "candles") return normalizeCandles(raw);
  if (section === "lines") return normalizeLines(raw);
  return normalizeHeatmap(raw);
}
