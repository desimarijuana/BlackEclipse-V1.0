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
  candles: { up: "#7aff78", down: "#ff3e3e", neutral: "#94a3b8" },
  // Finance default: green (up) / red (down). This is the shipped chart palette
  // and is INDEPENDENT of the app theme — a theme edit never recolours charts.
  // A user changes these only deliberately (Settings › Charts, or a preset that
  // carries its own chart palette).
  lines: { primary: "#7aff78", series: ["#ff3e3e", "#22c55e", "#f87171", "#4ade80", "#94a3b8", "#fb7185"] },
  heatmap: { up: "#22c55e", mid: "#27272a", down: "#b91c1c" },
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
