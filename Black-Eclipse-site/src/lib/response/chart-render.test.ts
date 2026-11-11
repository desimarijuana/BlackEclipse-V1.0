import { beforeEach, describe, expect, it, vi } from 'vitest';
import { parseResponsePayload } from './contract';
import { chartBlockToSpec } from './chart-spec';
import { chartBlockWarning, chartSpecWarning } from './chart-capabilities';
import { fetchQuantFigure, hydrateChartBlock } from './chart-data';

function chartBlock(value: unknown) {
  const parsed = parseResponsePayload({ blocks: [value] });
  const block = parsed.blocks[0];
  if (!block || block.type !== 'chart') {
    throw new Error(`block did not validate: ${JSON.stringify(parsed.diagnostics)}`);
  }
  return block;
}

function bars() {
  return [
    { date: '2026-01-02', open: 100, high: 105, low: 99, close: 104, volume: 10 },
    { date: '2026-01-05', open: 104, high: 108, low: 102, close: 107, volume: 12 },
  ];
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ symbol: 'AAPL', series: bars(), source: 'yfinance' }),
  })));
});

describe('candle row shapes never lose the chart', () => {
  it('keeps a dated [date, o, h, l, c] tuple', () => {
    const block = chartBlock({
      type: 'chart',
      chartType: 'candlestick',
      series: [{ name: 'GLD', data: [
        ['2026-01-02', 100, 105, 99, 104],
        ['2026-01-05', 104, 108, 102, 107],
      ] }],
    });
    expect(block.categories).toEqual(['2026-01-02', '2026-01-05']);
    const plan = chartBlockToSpec(block);
    expect(plan?.spec.candles).toHaveLength(2);
    expect(plan?.spec.candles?.[0]).toEqual({ open: 100, high: 105, low: 99, close: 104 });
  });

  it('keeps object OHLC rows (instead of flattening to [open, high])', () => {
    const block = chartBlock({
      type: 'chart',
      chartType: 'candlestick',
      series: [{ name: 'GLD', data: [
        { date: '2026-01-02', open: 100, high: 105, low: 99, close: 104 },
        { date: '2026-01-05', open: 104, high: 108, low: 102, close: 107 },
      ] }],
    });
    expect(block.categories).toEqual(['2026-01-02', '2026-01-05']);
    expect(chartBlockToSpec(block)?.spec.candles).toHaveLength(2);
  });
});

describe('a chart that names its series is resolved in the browser', () => {
  it('fills a block-level dataSource', async () => {
    const block = chartBlock({
      type: 'chart',
      chartType: 'line',
      dataSource: { symbol: 'AAPL', interval: '1d' },
    });
    const hydrated = await hydrateChartBlock(block);
    expect(hydrated.dataSource).toBeUndefined();
    expect(hydrated.categories).toEqual(['2026-01-02', '2026-01-05']);
    expect(hydrated.series?.[0].data).toEqual([104, 107]);
    expect(chartBlockWarning(hydrated)).toBeNull();
  });

  it('fills a mark-level dataSource with OHLC rows for a candle', async () => {
    const block = chartBlock({
      type: 'chart',
      chartType: 'scatter',
      panels: [{ marks: [{ type: 'candlestick', dataSource: { symbol: 'AAPL' } }] }],
    });
    const hydrated = await hydrateChartBlock(block);
    const mark = hydrated.panels?.[0].marks[0];
    expect(mark?.dataSource).toBeUndefined();
    expect(mark?.matrix).toHaveLength(2);
  });
});

describe('the chart spec reads the fields each kind uses', () => {
  it('maps a scatter to its points', () => {
    const block = chartBlock({
      type: 'chart',
      chartType: 'scatter',
      series: [{ name: 's', data: [[1, 2], [3, 4]] }],
    });
    expect(chartBlockToSpec(block)!.spec.points).toHaveLength(2);
  });

  it('maps a radar to its values', () => {
    const block = chartBlock({
      type: 'chart',
      chartType: 'radar',
      categories: ['a', 'b', 'c'],
      series: [{ name: 's', data: [1, 2, 3] }],
    });
    expect(chartBlockToSpec(block)!.spec.values).toEqual([1, 2, 3]);
  });

  it('maps a gauge and a treemap to their native kinds', () => {
    const gauge = chartBlockToSpec(chartBlock({
      type: 'chart', chartType: 'gauge', series: [{ name: 's', data: [42] }],
    }))!;
    const treemap = chartBlockToSpec(chartBlock({
      type: 'chart', chartType: 'treemap', categories: ['a'], series: [{ name: 's', data: [3] }],
    }))!;
    expect(gauge.spec.kind).toBe('gauge');
    expect(treemap.spec.kind).toBe('treemap');
  });

  it('maps a scene mark to its panel', () => {
    const block = chartBlock({
      type: 'chart',
      chartType: 'line',
      panels: [{ marks: [{ type: 'line', name: 'NAV', y: [1, 2, 3] }] }],
    });
    const plan = chartBlockToSpec(block)!;
    expect(plan.spec.panels?.[0].marks[0].type).toBe('line');
    expect(plan.spec.panels?.[0].marks[0].y).toHaveLength(3);
  });
});

describe('a quant figure names the artifact it was computed from', () => {
  it('accepts a chart block with only a quant source', () => {
    const block = chartBlock({
      type: 'chart',
      chartType: 'auto',
      title: 'Equity curve',
      quant: { experimentId: 'exp_abcd1234', figure: 'equity' },
    });
    expect(block.quant).toEqual({ experimentId: 'exp_abcd1234', figure: 'equity' });
    expect(block.series).toEqual([]);
    // The validator must not call a named quant figure "undrawable": the spec
    // is resolved from the experiment before the chart is rendered.
    expect(chartBlockWarning(block)).toBeNull();
  });

  it('resolves the figure through the backtest front door', async () => {
    const spec = { kind: 'line', series: [{ name: 'Equity', data: [1, 2] }] };
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        figure: { name: 'equity', title: 'Equity', available: true, spec },
      }),
    })));
    const resolved = await fetchQuantFigure({ experimentId: 'exp_abcd1234', figure: 'equity' });
    expect(resolved).toEqual(spec);
    const url = String((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(url).toContain('/api/backtest/experiments/exp_abcd1234/figures/equity');
  });

  it('reports an unavailable figure instead of drawing an empty one', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        figure: { name: 'equity', title: 'Equity', available: false, reason: 'no equity curve' },
      }),
    })));
    await expect(
      fetchQuantFigure({ experimentId: 'exp_missing', figure: 'equity' }),
    ).rejects.toThrow(/no equity curve/);
  });
});

describe('drawability is checked with the renderer, not just the schema', () => {
  it('rejects a series chart with no drawable values', () => {
    const block = chartBlock({
      type: 'chart', chartType: 'line', series: [{ name: 's', data: [] }],
    });
    expect(chartBlockWarning(block)).toMatch(/no drawable data/i);
  });

  it('accepts a named source without fetching it', () => {
    const block = chartBlock({
      type: 'chart', chartType: 'line', dataSource: { symbol: 'AAPL' },
    });
    expect(chartBlockWarning(block)).toBeNull();
  });
});

describe('3D is a mark, and a flat z grid is a real surface', () => {
  it('recovers a surface whose primitive is spelled `kind`', () => {
    const block = chartBlock({
      type: 'chart',
      chartType: 'line',
      panels: [{
        marks: [{
          kind: 'surface',
          name: 'Sharpe',
          x: [5, 10, 15],
          y: [20, 40, 60],
          z: [0.4, 0.5, 0.6, 0.5, 0.7, 0.8, 0.3, 0.6, 0.9],
        }],
      }],
    });
    expect(block.panels?.[0].marks[0].type).toBe('surface');
    const plan = chartBlockToSpec(block)!;
    expect(plan.spec.panels?.[0].marks[0].type).toBe('surface');
    expect(plan.spec.panels?.[0].marks[0].z).toHaveLength(9);
    expect(chartBlockWarning(block)).toBeNull();
    expect(chartSpecWarning(plan.spec)).toBeNull();
  });

  it('accepts a 2D `z` as the surface matrix', () => {
    const block = chartBlock({
      type: 'chart',
      chartType: 'line',
      panels: [{ marks: [{ type: 'surface', z: [[1, 2], [3, 4]] }] }],
    });
    expect(block.panels?.[0].marks[0].matrix).toEqual([[1, 2], [3, 4]]);
    expect(chartSpecWarning(chartBlockToSpec(block)!.spec)).toBeNull();
  });

  it('names a surface that carries no grid instead of drawing an empty one', () => {
    const block = chartBlock({
      type: 'chart',
      chartType: 'line',
      panels: [{ marks: [{ type: 'surface', z: [1] }] }],
    });
    expect(chartSpecWarning(chartBlockToSpec(block)!.spec)).toMatch(/needs a grid/);
    expect(chartBlockWarning(block)).toMatch(/needs a grid/);
  });
});

describe('an unsupported mark fails loudly, never silently', () => {
  it('names the primitive the producer asked for', () => {
    const block = chartBlock({
      type: 'chart',
      chartType: 'line',
      panels: [{ marks: [{ type: 'waterfall3d', y: [1, 2] }] }],
    });
    expect(block.panels?.[0].marks[0].type).toBe('waterfall3d');
    expect(chartBlockWarning(block)).toMatch(/cannot draw a "waterfall3d" mark/);
    expect(chartSpecWarning(chartBlockToSpec(block)!.spec)).toMatch(/waterfall3d/);
  });

  it('names a mark with no primitive at all', () => {
    const block = chartBlock({
      type: 'chart',
      chartType: 'line',
      panels: [{ marks: [{ name: 'orphan', y: [1, 2] }] }],
    });
    expect(chartBlockWarning(block)).toMatch(/has no `type`/);
  });
});
