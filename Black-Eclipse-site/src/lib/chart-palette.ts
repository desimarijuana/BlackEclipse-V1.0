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
  candles: { up: "#e5e7eb", down: "#6b7280", neutral: "#94a3b8" },
  // Neutral (black & white) by default: a chart is data, not decoration, and a
  // greyscale ramp reads on both the dark and the light surface without a hue
  // clash. Candles keep a light/dark pair so up and down still separate.
  // Users change these deliberately in Settings › General › Charts, or pick a
  // preset (Black & white, Silver, Ocean & amber, …).
  lines: { primary: "#fafafa", series: ["#fafafa", "#a1a1aa", "#d4d4d8", "#71717a", "#e4e4e7", "#52525b"] },
  heatmap: { up: "#e5e7eb", mid: "#27272a", down: "#52525b" },
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
