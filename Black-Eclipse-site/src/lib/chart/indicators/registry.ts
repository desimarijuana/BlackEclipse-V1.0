'use client';

// ── Indicator Registry (Phase 2) ──────────────────────────────────────────────
// Registry-driven indicator engine. Each indicator is a plugin with an id, name,
// configurable inputs, and a pure calculate() function. The EclipseChartProvider
// renders whatever the registry returns — adding a new indicator is just
// registering a definition here.

import type { IndicatorDefinition, PriceBar } from '@/lib/chart/types';
import { getChartPalette } from '@/lib/chart-palette-store';
import { analyzeMarketStructure } from '@/lib/chart/structure/engine';
import { structureToMarks } from '@/lib/chart/structure/registry';

// ── Pure math helpers (deterministic, no external deps) ──────────────────────

export function sma(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    out.push(i >= period - 1 ? sum / period : null);
  }
  return out;
}

export function ema(values: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const out: (number | null)[] = [];
  let prev: number | null = null;
  for (let i = 0; i < values.length; i++) {
    if (i < period - 1) { out.push(null); continue; }
    if (prev === null) {
      const sum = values.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
      prev = sum / period;
    } else {
      prev = values[i] * k + prev * (1 - k);
    }
    out.push(prev);
  }
  return out;
}

export function wma(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = [];
  const weightSum = (period * (period + 1)) / 2;
  for (let i = 0; i < values.length; i++) {
    if (i < period - 1) { out.push(null); continue; }
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += values[i - j] * (period - j);
    }
    out.push(sum / weightSum);
  }
  return out;
}

export function rsi(values: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = [];
  let avgGain = 0, avgLoss = 0;
  for (let i = 0; i < values.length; i++) {
    if (i === 0) { out.push(null); continue; }
    const change = values[i] - values[i - 1];
    const gain = Math.max(0, change);
    const loss = Math.max(0, -change);
    if (i <= period) {
      avgGain += gain; avgLoss += loss;
      if (i === period) { avgGain /= period; avgLoss /= period; }
      out.push(null);
      continue;
    }
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    if (avgLoss === 0) { out.push(100); continue; }
    const rs = avgGain / avgLoss;
    out.push(100 - 100 / (1 + rs));
  }
  return out;
}

export function macd(values: number[], fast = 12, slow = 26, signal = 9): {
  macd: (number | null)[]; signal: (number | null)[]; hist: (number | null)[];
} {
  const emaFast = ema(values, fast);
  const emaSlow = ema(values, slow);
  const macdLine: (number | null)[] = values.map((_, i) =>
    emaFast[i] != null && emaSlow[i] != null ? (emaFast[i] as number) - (emaSlow[i] as number) : null
  );
  // Signal = EMA of the MACD line (only over valid region).
  const valid = macdLine.map((v) => (v == null ? null : v));
  const signalLine = ema(valid.filter((v): v is number => v != null), signal);
  // Re-align signal to full length.
  const signalFull: (number | null)[] = new Array(values.length).fill(null);
  const startIdx = values.length - signalLine.length;
  for (let i = 0; i < signalLine.length; i++) signalFull[startIdx + i] = signalLine[i];
  const hist: (number | null)[] = macdLine.map((v, i) =>
    v != null && signalFull[i] != null ? v - (signalFull[i] as number) : null
  );
  return { macd: macdLine, signal: signalFull, hist };
}

export function atr(candles: PriceBar[], period = 14): (number | null)[] {
  const out: (number | null)[] = [];
  const trs: number[] = [];
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    if (i === 0) { trs.push(c.high != null && c.low != null ? c.high - c.low : 0); out.push(null); continue; }
    const prev = candles[i - 1];
    const prevClose = prev.close;
    const high = c.high ?? prevClose;
    const low = c.low ?? prevClose;
    const tr = Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose));
    trs.push(tr);
    if (i < period) { out.push(null); continue; }
    if (i === period) {
      const avg = trs.slice(1, period + 1).reduce((a, b) => a + b, 0) / period;
      out.push(avg);
    } else {
      const prevAtr = out[i - 1] as number;
      out.push((prevAtr * (period - 1) + tr) / period);
    }
  }
  return out;
}

export function bollinger(values: number[], period = 20, mult = 2): {
  mid: (number | null)[]; upper: (number | null)[]; lower: (number | null)[];
} {
  const mid = sma(values, period);
  const upper: (number | null)[] = [];
  const lower: (number | null)[] = [];
  for (let i = 0; i < values.length; i++) {
    if (mid[i] == null) { upper.push(null); lower.push(null); continue; }
    const slice = values.slice(i - period + 1, i + 1);
    const mean = mid[i] as number;
    const variance = slice.reduce((a, b) => a + (b - mean) ** 2, 0) / period;
    const sd = Math.sqrt(variance);
    upper.push(mean + mult * sd);
    lower.push(mean - mult * sd);
  }
  return { mid, upper, lower };
}

export function vwap(candles: PriceBar[]): (number | null)[] {
  const out: (number | null)[] = [];
  let cumPV = 0, cumVol = 0;
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    const vol = c.volume ?? 0;
    const typical = (c.high ?? c.close) + (c.low ?? c.close) + c.close;
    cumPV += (typical / 3) * vol;
    cumVol += vol;
    out.push(cumVol > 0 ? cumPV / cumVol : null);
  }
  return out;
}

export function obv(candles: PriceBar[]): (number | null)[] {
  const out: (number | null)[] = [];
  let prev = 0;
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    const vol = c.volume ?? 0;
    if (i === 0) { out.push(vol); prev = vol; continue; }
    const prevClose = candles[i - 1].close;
    if (c.close > prevClose) prev += vol;
    else if (c.close < prevClose) prev -= vol;
    out.push(prev);
  }
  return out;
}

// ── Registry ──────────────────────────────────────────────────────────────────

const registry = new Map<string, IndicatorDefinition>();

function register(def: IndicatorDefinition) {
  registry.set(def.id, def);
}

register({
  id: 'ema',
  name: 'EMA',
  description: 'Exponential Moving Average — weights recent prices more heavily.',
  category: 'trend',
  inputs: [
    { key: 'period', label: 'Period', type: 'number', default: 20, min: 1, max: 500, step: 1 },
    { key: 'source', label: 'Source', type: 'select', default: 'close', options: [{ value: 'close', label: 'Close' }, { value: 'high', label: 'High' }, { value: 'low', label: 'Low' }, { value: 'open', label: 'Open' }] },
  ],
  calculate(candles, settings) {
    const period = Number(settings.period ?? 20);
    const source = String(settings.source ?? 'close') as 'close' | 'high' | 'low' | 'open';
    const values = candles.map((c) => c[source] ?? c.close);
    return { pane: 'overlay', series: [{ id: 'ema', label: `EMA ${period}`, kind: 'line', data: ema(values, period), color: getChartPalette().lines.series[1] }] };
  },
});

register({
  id: 'sma',
  name: 'SMA',
  description: 'Simple Moving Average — average of the last N closes.',
  category: 'trend',
  inputs: [
    { key: 'period', label: 'Period', type: 'number', default: 20, min: 1, max: 500, step: 1 },
    { key: 'source', label: 'Source', type: 'select', default: 'close', options: [{ value: 'close', label: 'Close' }, { value: 'high', label: 'High' }, { value: 'low', label: 'Low' }, { value: 'open', label: 'Open' }] },
  ],
  calculate(candles, settings) {
    const period = Number(settings.period ?? 20);
    const source = String(settings.source ?? 'close') as 'close' | 'high' | 'low' | 'open';
    const values = candles.map((c) => c[source] ?? c.close);
    return { pane: 'overlay', series: [{ id: 'sma', label: `SMA ${period}`, kind: 'line', data: sma(values, period), color: getChartPalette().lines.series[0] }] };
  },
});

register({
  id: 'wma',
  name: 'WMA',
  description: 'Weighted Moving Average — linear weighting, most recent highest.',
  category: 'trend',
  inputs: [
    { key: 'period', label: 'Period', type: 'number', default: 20, min: 1, max: 500, step: 1 },
  ],
  calculate(candles, settings) {
    const period = Number(settings.period ?? 20);
    const values = candles.map((c) => c.close);
    return { pane: 'overlay', series: [{ id: 'wma', label: `WMA ${period}`, kind: 'line', data: wma(values, period), color: getChartPalette().lines.series[2] }] };
  },
});

register({
  id: 'rsi',
  name: 'RSI',
  description: 'Relative Strength Index — momentum oscillator (0–100).',
  category: 'momentum',
  inputs: [
    { key: 'period', label: 'Period', type: 'number', default: 14, min: 1, max: 100, step: 1 },
  ],
  calculate(candles, settings) {
    const period = Number(settings.period ?? 14);
    const values = candles.map((c) => c.close);
    return {
      pane: 'separate', paneHeight: 0.22, yMin: 0, yMax: 100,
      series: [{ id: 'rsi', label: `RSI ${period}`, kind: 'line', data: rsi(values, period), color: getChartPalette().lines.series[2] }],
      marks: {
        markLine: [
          { yAxis: 70, lineStyle: { color: getChartPalette().candles.down + '59', type: 'dashed', width: 1 }, label: { show: false } },
          { yAxis: 30, lineStyle: { color: getChartPalette().candles.up + '59', type: 'dashed', width: 1 }, label: { show: false } },
        ],
      },
    };
  },
});

register({
  id: 'macd',
  name: 'MACD',
  description: 'Moving Average Convergence Divergence — trend momentum.',
  category: 'momentum',
  inputs: [
    { key: 'fast', label: 'Fast', type: 'number', default: 12, min: 1, max: 100, step: 1 },
    { key: 'slow', label: 'Slow', type: 'number', default: 26, min: 1, max: 200, step: 1 },
    { key: 'signal', label: 'Signal', type: 'number', default: 9, min: 1, max: 100, step: 1 },
  ],
  calculate(candles, settings) {
    const fast = Number(settings.fast ?? 12);
    const slow = Number(settings.slow ?? 26);
    const signal = Number(settings.signal ?? 9);
    const values = candles.map((c) => c.close);
    const { macd: m, signal: s, hist } = macd(values, fast, slow, signal);
    return {
      pane: 'separate', paneHeight: 0.2,
      series: [
        { id: 'macd', label: 'MACD', kind: 'line', data: m, color: getChartPalette().lines.series[0] },
        { id: 'signal', label: 'Signal', kind: 'line', data: s, color: getChartPalette().lines.series[1] },
        { id: 'hist', label: 'Histogram', kind: 'bar', data: hist },
      ],
    };
  },
});

register({
  id: 'atr',
  name: 'ATR',
  description: 'Average True Range — volatility measure.',
  category: 'volatility',
  inputs: [
    { key: 'period', label: 'Period', type: 'number', default: 14, min: 1, max: 200, step: 1 },
  ],
  calculate(candles, settings) {
    const period = Number(settings.period ?? 14);
    return {
      pane: 'separate', paneHeight: 0.2,
      series: [{ id: 'atr', label: `ATR ${period}`, kind: 'line', data: atr(candles, period), color: getChartPalette().lines.series[1] }],
    };
  },
});

register({
  id: 'bollinger',
  name: 'Bollinger Bands',
  description: 'Volatility bands around a moving average.',
  category: 'volatility',
  inputs: [
    { key: 'period', label: 'Period', type: 'number', default: 20, min: 1, max: 200, step: 1 },
    { key: 'mult', label: 'Std Dev', type: 'number', default: 2, min: 0.1, max: 5, step: 0.1 },
  ],
  calculate(candles, settings) {
    const period = Number(settings.period ?? 20);
    const mult = Number(settings.mult ?? 2);
    const values = candles.map((c) => c.close);
    const { mid, upper, lower } = bollinger(values, period, mult);
    return {
      pane: 'overlay',
      series: [
        { id: 'mid', label: `BB Mid ${period}`, kind: 'line', data: mid, color: getChartPalette().lines.series[1] },
        { id: 'upper', label: 'Upper', kind: 'line', data: upper, color: getChartPalette().lines.series[0], bandId: 'lower' },
        { id: 'lower', label: 'Lower', kind: 'line', data: lower, color: getChartPalette().lines.series[0] },
      ],
    };
  },
});

register({
  id: 'vwap',
  name: 'VWAP',
  description: 'Volume-Weighted Average Price — session benchmark.',
  category: 'volume',
  inputs: [],
  calculate(candles) {
    return { pane: 'overlay', series: [{ id: 'vwap', label: 'VWAP', kind: 'line', data: vwap(candles), color: getChartPalette().lines.series[3] }] };
  },
});

register({
  id: 'obv',
  name: 'OBV',
  description: 'On-Balance Volume — cumulative volume flow.',
  category: 'volume',
  inputs: [],
  calculate(candles) {
    return { pane: 'separate', paneHeight: 0.2, series: [{ id: 'obv', label: 'OBV', kind: 'line', data: obv(candles), color: getChartPalette().lines.series[0] }] };
  },
});

// ── Black Eclipse market-structure indicators (Phase 5) ─────────────────────
// Each structure layer is an opt-in indicator that renders mark overlays on the
// main pane. They are first-class analysis objects, not generic line series.

function structureIndicator(
  id: string,
  name: string,
  description: string,
  layer: keyof ReturnType<typeof structureToMarks> | 'swings' | 'bos' | 'choch' | 'orderBlocks' | 'fvgs' | 'liquidity' | 'sessions' | 'openingRanges',
): IndicatorDefinition {
  return {
    id,
    name,
    description,
    category: 'black-eclipse',
    inputs: [],
    calculate(candles) {
      const result = analyzeMarketStructure(candles, '1D');
      const layers = {
        swings: layer === 'swings',
        bos: layer === 'bos',
        choch: layer === 'choch',
        orderBlocks: layer === 'orderBlocks',
        fvgs: layer === 'fvgs',
        liquidity: layer === 'liquidity',
        sessions: layer === 'sessions',
        openingRanges: layer === 'openingRanges',
      };
      const marks = structureToMarks(result, layers);
      return {
        pane: 'overlay',
        series: [],
        marks: {
          markLine: marks.markLine,
          markArea: marks.markArea,
          markPoint: marks.markPoint,
        },
      };
    },
  };
}

register(structureIndicator('be-swings', 'Swing High/Low', 'Black Eclipse — fractal swing highs and lows.', 'swings'));
register(structureIndicator('be-bos', 'Break of Structure (BOS)', 'Black Eclipse — price breaks a prior swing.', 'bos'));
register(structureIndicator('be-choch', 'Change of Character (CHOCH)', 'Black Eclipse — trend reversal signal.', 'choch'));
register(structureIndicator('be-order-blocks', 'Order Blocks', 'Black Eclipse — last opposing candle before a strong move.', 'orderBlocks'));
register(structureIndicator('be-fvg', 'Fair Value Gaps', 'Black Eclipse — price imbalances.', 'fvgs'));
register(structureIndicator('be-liquidity', 'Liquidity Levels', 'Black Eclipse — equal highs/lows.', 'liquidity'));
register(structureIndicator('be-sessions', 'Session High/Low', 'Black Eclipse — daily session levels.', 'sessions'));
register(structureIndicator('be-opening-range', 'Opening Range', 'Black Eclipse — first 3 candles of a session.', 'openingRanges'));

/** Get a registered indicator by id. */
export function getIndicator(id: string): IndicatorDefinition | undefined {
  return registry.get(id);
}

/** All registered indicators, grouped by category. */
export function getAllIndicators(): IndicatorDefinition[] {
  return Array.from(registry.values());
}

/** Compute an indicator over candles with settings. */
export function calculateIndicator(
  id: string,
  candles: PriceBar[],
  settings: Record<string, number | string | boolean>
) {
  const def = getIndicator(id);
  if (!def) return null;
  return def.calculate(candles, settings);
}
