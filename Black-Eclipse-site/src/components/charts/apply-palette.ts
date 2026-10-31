// ── Chart colouring ─────────────────────────────────────────────────────────
// The engine authors a figure with ITS default palette; the user's palette is
// applied here, in the browser, so a colour change repaints an existing chart
// without asking the runtime to redraw (and re-encode) the picture.
//
// The rules are deliberately boring and predictable:
//   • candlestick / waterfall keep a semantic pair (up / down);
//   • a heatmap / surface / 3-D colour axis gets a neutral scale;
//   • every other trace takes the next categorical colour, in order.
//
// The figure is never mutated: the caller keeps the engine's original so
// "reset view" can restore exactly what was authored.

import type { ChartPalette } from '@/lib/chart-palette';
import type { PlotlyFigure } from './plotly-chart';

type Trace = Record<string, unknown> & {
  type?: string;
  name?: string;
  line?: { color?: unknown; width?: unknown; dash?: unknown };
  marker?: Record<string, unknown> & { color?: unknown; colors?: unknown; line?: unknown };
  textfont?: { color?: unknown; size?: unknown };
  fill?: unknown;
  fillcolor?: unknown;
  increasing?: { line?: { color?: string }; marker?: { color?: string } };
  decreasing?: { line?: { color?: string }; marker?: { color?: string } };
  colorscale?: unknown;
  colorbar?: unknown;
  showscale?: unknown;
};

/** `#rrggbb` + alpha → `rgba(...)`, the form Plotly wants for fills. */
export function withAlpha(hex: string, alpha: number): string {
  const clean = hex.trim().replace(/^#/, '');
  const expanded = clean.length === 3 ? clean.split('').map((c) => c + c).join('') : clean;
  if (!/^[0-9a-f]{6}$/i.test(expanded)) return hex;
  const r = parseInt(expanded.slice(0, 2), 16);
  const g = parseInt(expanded.slice(2, 4), 16);
  const b = parseInt(expanded.slice(4, 6), 16);
  const a = Math.max(0, Math.min(1, alpha));
  return `rgba(${r},${g},${b},${a})`;
}

/** A neutral (dark → light) ramp for heatmaps, so no hue invents meaning. */
function heatScale(palette: ChartPalette): Array<[number, string]> {
  return [
    [0, palette.heatmap.down],
    [0.5, palette.heatmap.mid],
    [1, palette.heatmap.up],
  ];
}

function isColorString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

/**
 * The figure with the user's colours applied. `dataIndex` counts only painted
 * traces, so a hidden lower-band trace does not consume a palette slot.
 */
export function applyChartPalette(
  figure: PlotlyFigure | null | undefined,
  palette: ChartPalette,
): PlotlyFigure | null | undefined {
  if (!figure) return figure;
  const series = palette.lines.series.length > 0 ? palette.lines.series : [palette.lines.primary];
  let slot = 0;
  const next = () => series[slot++ % series.length];

  const data = (figure.data ?? []).map((raw) => {
    const trace = raw as Trace;
    const type = String(trace.type ?? 'scatter');

    if (type === 'candlestick') {
      return {
        ...trace,
        increasing: { line: { color: palette.candles.up } },
        decreasing: { line: { color: palette.candles.down } },
      };
    }

    if (type === 'waterfall') {
      return {
        ...trace,
        increasing: { marker: { color: palette.candles.up } },
        decreasing: { marker: { color: palette.candles.down } },
        connector: { line: { color: palette.candles.neutral } },
      };
    }

    if (type === 'heatmap' || type === 'surface' || type === 'contour' || type === 'scatter3d') {
      return { ...trace, colorscale: heatScale(palette) };
    }

    if (type === 'histogram' || type === 'histogram2d') {
      const color = next();
      return { ...trace, marker: { ...(trace.marker ?? {}), color } };
    }

    // An invisible helper trace (a band's lower edge) must not take a colour.
    if (trace.showlegend === false && !isColorString(trace.marker?.color) && !isColorString(trace.line?.color)) {
      return trace;
    }

    const color = next();

    if (type === 'bar' || type === 'box' || type === 'violin' || type === 'funnel') {
      return { ...trace, marker: { ...(trace.marker ?? {}), color }, line: { ...(trace.line ?? {}), color } };
    }

    if (type === 'pie' || type === 'donut' || type === 'treemap' || type === 'sunburst') {
      // Slice colours cycle the palette, so a pie is not one flat block again.
      const count = Array.isArray(trace.values)
        ? trace.values.length
        : Array.isArray(trace.labels)
          ? trace.labels.length
          : 0;
      const colors = Array.from({ length: count }, (_, i) => series[i % series.length]);
      return { ...trace, marker: { ...(trace.marker ?? {}), colors } };
    }

    if (type === 'scatter' && trace.mode === 'text') {
      return { ...trace, textfont: { ...(trace.textfont ?? {}), color } };
    }

    const filled = trace.fill === 'tozeroy' || trace.fill === 'tonexty' || trace.fill === 'toself';
    return {
      ...trace,
      line: { ...(trace.line ?? {}), color },
      ...(trace.marker ? { marker: { ...trace.marker, color } } : {}),
      ...(filled ? { fillcolor: withAlpha(color, 0.22) } : {}),
    };
  });

  return { ...figure, data };
}
