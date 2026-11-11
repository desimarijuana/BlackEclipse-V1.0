// The ONE list of what the chat chart renderer can actually draw.
//
// A chat chart is authored as a Plotly figure by the Python engine, with the
// matplotlib PNG as the instant fallback. A block may pass the wire contract
// and still ask for something the renderer cannot draw, so validation and the
// UI share THIS list instead of guessing.

import type { ChartMark, ChartSpec } from '@/lib/harness/charts';
import { CHART_MARK_TYPES, type ChartBlock } from './contract';
import { chartBlockToSpec } from './chart-spec';

export const CHART_KINDS = new Set<ChartSpec['kind']>([
  'line', 'area', 'bar', 'stackedBar', 'pie', 'donut', 'scatter', 'histogram',
  'heatmap', 'candlestick', 'waterfall', 'radar', 'gauge', 'treemap', 'scene',
]);

// Derived from the contract's own vocabulary so the two can never drift.
export const CHART_MARKS = new Set<string>(CHART_MARK_TYPES);

/** The marks that need a third dimension, and therefore three vectors/a grid. */
const MARK_TYPES_3D = new Set(['scatter3d', 'surface']);

/**
 * Why a spec cannot be drawn, or `null` when it can.
 *
 * This is deliberately about DRAWABILITY, not schema validity: an empty series
 * is valid JSON and a valid block, but it is not a chart.
 */
export function chartSpecWarning(spec: ChartSpec): string | null {
  if (!CHART_KINDS.has(spec.kind)) return `the renderer cannot draw a ${spec.kind} chart`;
  if (spec.panels && spec.panels.length > 0) {
    for (const [panelIndex, panel] of spec.panels.entries()) {
      if (!panel.marks || panel.marks.length === 0) {
        return `panel ${panelIndex + 1} has no marks`;
      }
      for (const mark of panel.marks) {
        if (!CHART_MARKS.has(mark.type)) {
          return `the renderer cannot draw a "${mark.type}" mark (panel ${panelIndex + 1}); a mark's primitive is its \`type\``;
        }
        if (MARK_TYPES_3D.has(mark.type)) {
          const missing = missing3dData(mark);
          if (missing) return `${missing} (panel ${panelIndex + 1})`;
        }
      }
    }
    return null;
  }
  if (spec.kind === 'pie' || spec.kind === 'donut') {
    return (spec.values?.length ?? 0) > 0 ? null : 'a pie chart needs at least one value';
  }
  if (spec.kind === 'radar' || spec.kind === 'gauge') {
    return (spec.values?.length ?? 0) > 0 || spec.value !== undefined ? null : 'the chart has no values';
  }
  if (spec.kind === 'treemap') {
    return (spec.tiles?.length ?? 0) > 0 ? null : 'a treemap needs at least one tile';
  }
  if (spec.kind === 'candlestick') {
    return (spec.candles?.length ?? 0) > 0 ? null : 'a candlestick needs OHLC points';
  }
  if (spec.kind === 'scatter') {
    return (spec.points?.length ?? 0) > 0 ? null : 'a scatter needs at least one point';
  }
  if (spec.kind === 'heatmap') {
    return (spec.matrix?.length ?? 0) > 0 ? null : 'a heatmap needs a matrix';
  }
  if ((spec.series?.length ?? 0) === 0) return `a ${spec.kind} chart needs at least one series`;
  return null;
}

/** The missing part of a 3D mark's data, or `null` when it can be drawn. */
function missing3dData(mark: ChartMark): string | null {
  // A named source is fetched before the figure is drawn; it cannot be
  // judged here.
  if (mark.dataSource) return null;
  if (mark.type === 'scatter3d') {
    if (!mark.x?.length) return 'a scatter3d mark needs `x`';
    if (!mark.y?.length) return 'a scatter3d mark needs `y`';
    if (!mark.z?.length) return 'a scatter3d mark needs `z`';
    return null;
  }
  if (mark.type === 'surface') {
    const matrix = mark.matrix?.filter((row) => Array.isArray(row) && row.length > 0) ?? [];
    if (matrix.length >= 2 && Math.max(...matrix.map((row) => row.length)) >= 2) return null;
    if ((mark.z?.length ?? 0) >= 4) return null;
    return 'a surface mark needs a grid: `matrix`, or `x`/`y` plus a flat `z`';
  }
  return null;
}

/**
 * The drawability check for a raw block, before any data is fetched.
 *
 * A block that NAMES its series is accepted here: the browser resolves it. A
 * scene mark with a named source is accepted for the same reason. Everything
 * else is checked against the same spec the renderer will draw.
 */
export function chartBlockWarning(block: ChartBlock): string | null {
  // A named market source or a computed quant figure is resolved before the
  // mapped spec exists, so the raw block is accepted here; the resolved spec is
  // checked by `chartSpecWarning` once the data arrives.
  if (block.dataSource || block.quant) return null;
  if (block.panels && block.panels.length > 0) {
    if (block.panels.every((panel) => panel.marks.length === 0)) return 'the chart has no marks to draw';
    for (const [panelIndex, panel] of block.panels.entries()) {
      for (const mark of panel.marks) {
        // The contract PRESERVES an unsupported primitive (or `(missing)`).
        // Name it instead of letting a fallback hide the mistake.
        const markType = mark.type as string;
        if (markType === '(missing)') {
          return `a mark in panel ${panelIndex + 1} has no \`type\`; set it to one of: ${[...CHART_MARKS].join(', ')}`;
        }
        if (!CHART_MARKS.has(markType)) {
          return `the renderer cannot draw a "${markType}" mark (panel ${panelIndex + 1}); a mark's primitive is its \`type\`, one of: ${[...CHART_MARKS].join(', ')}`;
        }
      }
    }
    const plan = chartBlockToSpec(block);
    return plan ? chartSpecWarning(plan.spec) : 'the chart has no drawable data (series, panels or a dataSource is required)';
  }
  const plan = chartBlockToSpec(block);
  if (!plan) return 'the chart has no drawable data (series, panels or a dataSource is required)';
  return chartSpecWarning(plan.spec);
}
