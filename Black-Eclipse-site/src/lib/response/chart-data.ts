// A chart that NAMES its series, resolved in the BROWSER.
//
// A chart block may say `dataSource: {symbol, interval, field}` instead of
// typing 250 prices into the message. The old path sent that to the Python
// engine and back as a picture. The interactive renderer resolves it here:
// one request through the app's own JDdS price-history route (the same route
// every chart uses), then the block is filled so the shared mapper can draw it.

import type { ChartBlock, ChartDataSource } from './contract';
import type { ChartSpec } from '@/lib/harness/charts';

export interface ChartBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

interface BarsPayload {
  symbol: string;
  currency?: string;
  series: ChartBar[];
  source?: string;
}

const FETCH_CACHE = new Map<string, Promise<{ categories: string[]; bars: ChartBar[]; name: string }>>();

function rangeFor(source: ChartDataSource): string {
  const interval = (source.interval ?? '1d').toLowerCase();
  if (source.start || source.end) {
    const start = source.start ? Date.parse(source.start) : NaN;
    const end = source.end ? Date.parse(source.end) : Date.now();
    if (Number.isFinite(start) && Number.isFinite(end) && end > start) {
      const days = (end - start) / 86_400_000;
      if (days <= 10) return '5d';
      if (days <= 31) return '1mo';
      if (days <= 92) return '3mo';
      if (days <= 183) return '6mo';
      if (days <= 366) return '1y';
      if (days <= 731) return '2y';
      return '5y';
    }
  }
  if (/(m|h)$/.test(interval) && !/mo$/.test(interval)) return '5d';
  if (interval === '1wk') return '2y';
  if (interval === '1mo') return '5y';
  return '1y';
}

function cacheKey(source: ChartDataSource): string {
  return [
    source.symbol.toUpperCase(),
    (source.market ?? '').toUpperCase(),
    source.interval ?? '1d',
    source.start ?? '',
    source.end ?? '',
  ].join('|');
}

/** Fetch the bars a named source refers to. Throws an honest, readable error. */
export async function fetchChartBars(
  source: ChartDataSource,
): Promise<{ categories: string[]; bars: ChartBar[]; name: string }> {
  const key = cacheKey(source);
  const existing = FETCH_CACHE.get(key);
  if (existing) return existing;
  const run = (async () => {
    const params = new URLSearchParams({
      symbol: source.symbol,
      market: source.market || 'US',
      range: rangeFor(source),
      interval: source.interval || '1d',
    });
    const res = await fetch(`/api/price-history?${params.toString()}`, {
      signal: AbortSignal.timeout(30_000),
    });
    if (!res.ok) throw new Error(`the chart's source could not be loaded (HTTP ${res.status})`);
    const payload = (await res.json().catch(() => ({}))) as Partial<BarsPayload>;
    const bars = Array.isArray(payload.series) ? payload.series : [];
    if (bars.length === 0) {
      throw new Error(`no price history is available for ${source.symbol}`);
    }
    return {
      categories: bars.map((bar) => String(bar.date ?? '')),
      bars,
      name: source.name || source.symbol,
    };
  })();
  FETCH_CACHE.set(key, run);
  // A failed fetch must be retryable; keep successful responses cached.
  run.catch(() => FETCH_CACHE.delete(key));
  return run;
}

function valueOf(bar: ChartBar, field: ChartDataSource['field']): number {
  const key = field && field in bar ? field : 'close';
  const value = bar[key as keyof ChartBar];
  return typeof value === 'number' && Number.isFinite(value) ? value : bar.close;
}

function isCandleKind(kind: string): boolean {
  return kind === 'candlestick' || kind === 'ohlc';
}

/**
 * Fill every named source on the block with the series it names.
 *
 * Returns a NEW block; a source that cannot be resolved rejects with the reason
 * (the UI shows it rather than an empty chart).
 */
export interface QuantFigureSource {
  experimentId: string;
  figure: string;
}

export interface QuantFigurePayload {
  status?: string;
  experimentId?: string;
  figure?: {
    name: string;
    title: string;
    available: boolean;
    reason?: string;
    spec?: ChartSpec;
  };
}

const QUANT_FETCH_CACHE = new Map<string, Promise<ChartSpec>>();

/**
 * Resolve a COMPUTED quant figure to the chart engine's spec.
 *
 * The figure is built by the Python Quant Figure Kit from the stored
 * experiment; the browser never receives a series to fill in. A source that
 * cannot be resolved rejects with the runtime's own reason, so the chart shows
 * an honest empty state instead of a guessed picture.
 */
export async function fetchQuantFigure(source: QuantFigureSource): Promise<ChartSpec> {
  const key = `${source.experimentId}|${source.figure}`;
  const existing = QUANT_FETCH_CACHE.get(key);
  if (existing) return existing;
  const run = (async () => {
    const params = new URLSearchParams({ theme: 'eclipse-dark' });
    const res = await fetch(
      `/api/backtest/experiments/${encodeURIComponent(source.experimentId)}/figures/` +
        `${encodeURIComponent(source.figure)}?${params.toString()}`,
      { signal: AbortSignal.timeout(30_000) },
    );
    const payload = (await res.json().catch(() => ({}))) as QuantFigurePayload & {
      error?: string;
    };
    if (!res.ok) {
      throw new Error(payload.error || `the figure could not be built (HTTP ${res.status})`);
    }
    const figure = payload.figure;
    if (!figure?.available || !figure.spec) {
      throw new Error(figure?.reason || `the quant figure ${source.figure} is unavailable`);
    }
    return figure.spec;
  })();
  QUANT_FETCH_CACHE.set(key, run);
  run.catch(() => QUANT_FETCH_CACHE.delete(key));
  return run;
}

export async function hydrateChartBlock(block: ChartBlock): Promise<ChartBlock> {
  const next = { ...block } as ChartBlock & { dataSource?: ChartDataSource };

  if (block.dataSource) {
    const source = block.dataSource;
    const { categories, bars, name } = await fetchChartBars(source);
    if (isCandleKind(block.chartType)) {
      next.categories = categories;
      next.series = [{
        name,
        data: bars.map((bar) => [bar.open, bar.high, bar.low, bar.close]),
      }];
    } else {
      next.categories = categories;
      next.series = [{ name, data: bars.map((bar) => valueOf(bar, source.field)) }];
    }
    delete next.dataSource;
  }

  if (block.panels && block.panels.length > 0) {
    const panels = await Promise.all(block.panels.map(async (panel) => {
      const marks = await Promise.all(panel.marks.map(async (mark) => {
        if (!mark.dataSource) return mark;
        const source = mark.dataSource;
        const { categories, bars, name } = await fetchChartBars(source);
        const filled = { ...mark } as typeof mark & { dataSource?: ChartDataSource };
        delete filled.dataSource;
        filled.name = filled.name || name;
        if (isCandleKind(mark.type)) {
          filled.matrix = bars.map((bar) => [bar.open, bar.high, bar.low, bar.close]);
          filled.x = categories;
        } else {
          filled.x = categories;
          filled.y = bars.map((bar) => valueOf(bar, source.field));
        }
        return filled;
      }));
      return { ...panel, marks };
    }));
    next.panels = panels;
  }

  return next;
}
