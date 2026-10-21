import { describe, it, expect } from 'vitest';

// The chart block → the chart engine's SPEC.
//
// The rules under test:
//   * the mapping never invents data (a missing point stays missing);
//   * a lossy mapping is TOLD, not hidden (a treemap becomes a bar, and the
//     note says so);
//   * a block with no data produces no spec at all.

import { chartBlockToSpec, chartHasData, directChartType, resolveChartType } from './chart-spec';
import type { ChartBlock } from './contract';

type Block = Partial<ChartBlock> & Pick<ChartBlock, 'chartType' | 'series'>;

function block(overrides: Block): ChartBlock {
  return {
    legend: true,
    zoom: false,
    smooth: false,
    stacked: false,
    ...overrides,
  } as ChartBlock;
}

describe('chartHasData', () => {
  it('is false when every point is missing', () => {
    expect(chartHasData(block({ chartType: 'line', series: [{ name: 'a', data: [null, null] }] }))).toBe(false);
  });

  it('is true when one point has a value', () => {
    expect(chartHasData(block({ chartType: 'line', series: [{ name: 'a', data: [null, 3] }] }))).toBe(true);
  });
});

describe('the visual director', () => {
  it('reads OHLC points as a candlestick chart', () => {
    const b = block({
      chartType: 'auto',
      series: [{ name: 'p', data: [[1, 2, 0.5, 1.5]] }],
    });
    expect(directChartType(b)).toBe('candlestick');
  });

  it('reads temporal categories as a line chart', () => {
    const b = block({
      chartType: 'auto',
      categories: ['2026-01', '2026-02'],
      series: [{ name: 'a', data: [1, 2] }],
    });
    expect(directChartType(b)).toBe('line');
  });

  it('never overrides an explicit type', () => {
    const b = block({ chartType: 'bar', series: [{ name: 'a', data: [1, 2] }] });
    expect(resolveChartType(b)).toBe('bar');
  });
});

describe('the SCENE form (any chart)', () => {
  it('passes the panels and marks straight through to the engine', () => {
    const plan = chartBlockToSpec(
      block({
        chartType: 'line',
        series: [],
        panels: [
          {
            title: 'Price',
            marks: [
              { type: 'line', name: 'Close', y: [100, 104] },
              { type: 'band', lower: [98, 102], upper: [102, 106] },
            ],
          },
        ],
      } as never),
    );
    expect(plan?.spec.kind).toBe('scene');
    expect(plan?.spec.panels).toHaveLength(1);
    expect(plan?.spec.panels?.[0].marks).toHaveLength(2);
    expect(plan?.spec.panels?.[0].marks[0].y).toEqual([100, 104]);
    expect(plan?.notes).toEqual([]);
  });

  it('a scene needs no series at all', () => {
    const plan = chartBlockToSpec(
      block({
        chartType: 'line',
        panels: [{ marks: [{ type: 'violin', values: [1, 2, 3] }] }],
      } as never),
    );
    expect(plan?.spec.kind).toBe('scene');
  });
});

describe('chartBlockToSpec', () => {
  it('returns null when the block carries no data', () => {
    expect(chartBlockToSpec(block({ chartType: 'line', series: [{ name: 'a', data: [] }] }))).toBeNull();
  });

  it('maps a line chart to a line spec with its categories', () => {
    const plan = chartBlockToSpec(
      block({
        chartType: 'line',
        title: 'NAV',
        categories: ['Jan', 'Feb'],
        series: [{ name: 'NAV', data: [100, 104] }],
      }),
    );
    expect(plan?.spec.kind).toBe('line');
    expect(plan?.spec.categories).toEqual(['Jan', 'Feb']);
    expect(plan?.spec.series?.[0].data).toEqual([100, 104]);
    expect(plan?.spec.title).toBe('NAV');
  });

  it('keeps a missing point missing — never a zero', () => {
    const plan = chartBlockToSpec(
      block({ chartType: 'line', categories: ['a', 'b', 'c'], series: [{ name: 's', data: [1, null, 3] }] }),
    );
    expect(plan?.spec.series?.[0].data).toEqual([1, null, 3]);
  });

  it('maps a stacked bar chart to a stacked spec', () => {
    const plan = chartBlockToSpec(
      block({
        chartType: 'stacked_bar',
        categories: ['a', 'b'],
        series: [
          { name: 'x', data: [1, 2] },
          { name: 'y', data: [3, 4] },
        ],
      }),
    );
    expect(plan?.spec.kind).toBe('stackedBar');
    expect(plan?.spec.stacked).toBe(true);
  });

  it('maps a pie chart to labels and values', () => {
    const plan = chartBlockToSpec(
      block({ chartType: 'pie', categories: ['A', 'B'], series: [{ name: 's', data: [60, 40] }] }),
    );
    expect(plan?.spec.kind).toBe('pie');
    expect(plan?.spec.labels).toEqual(['A', 'B']);
    expect(plan?.spec.values).toEqual([60, 40]);
  });

  it('maps a scatter chart to points', () => {
    const plan = chartBlockToSpec(
      block({ chartType: 'scatter', series: [{ name: 's', data: [[1, 2], [3, 4]] }] }),
    );
    expect(plan?.spec.kind).toBe('scatter');
    expect(plan?.spec.points).toEqual([
      { x: 1, y: 2 },
      { x: 3, y: 4 },
    ]);
  });

  it('maps a bubble chart to sized scatter points and says so', () => {
    const plan = chartBlockToSpec(
      block({ chartType: 'bubble', series: [{ name: 's', data: [[1, 2, 50]] }] }),
    );
    expect(plan?.spec.kind).toBe('scatter');
    expect(plan?.spec.points?.[0].size).toBe(50);
    expect(plan?.notes.join(' ')).toMatch(/bubble/i);
  });

  it('maps a heatmap to a matrix with both label axes', () => {
    const plan = chartBlockToSpec(
      block({
        chartType: 'heatmap',
        categories: ['x', 'y'],
        series: [
          { name: 'r1', data: [1, 2] },
          { name: 'r2', data: [3, 4] },
        ],
      }),
    );
    expect(plan?.spec.kind).toBe('heatmap');
    expect(plan?.spec.matrix).toEqual([
      [1, 2],
      [3, 4],
    ]);
    expect(plan?.spec.rowLabels).toEqual(['r1', 'r2']);
    expect(plan?.spec.colLabels).toEqual(['x', 'y']);
  });

  it('maps a candlestick chart to candles in the OHLC order', () => {
    const plan = chartBlockToSpec(
      block({ chartType: 'candlestick', categories: ['d1'], series: [{ name: 'p', data: [[1, 2, 0.5, 1.5]] }] }),
    );
    expect(plan?.spec.kind).toBe('candlestick');
    expect(plan?.spec.candles?.[0]).toEqual({ open: 1, high: 2, low: 0.5, close: 1.5 });
  });

  it('maps a waterfall chart to one series of values', () => {
    const plan = chartBlockToSpec(
      block({ chartType: 'waterfall', categories: ['a', 'b'], series: [{ name: 'c', data: [10, -4] }] }),
    );
    expect(plan?.spec.kind).toBe('waterfall');
    expect(plan?.spec.series?.[0].data).toEqual([10, -4]);
  });

  it('maps a radar chart to labels and values', () => {
    const plan = chartBlockToSpec(
      block({ chartType: 'radar', categories: ['v', 'q'], series: [{ name: 's', data: [1, 2] }] }),
    );
    expect(plan?.spec.kind).toBe('radar');
    expect(plan?.spec.labels).toEqual(['v', 'q']);
  });

  it('carries a forecast band through to the spec', () => {
    const plan = chartBlockToSpec(
      block({
        chartType: 'line',
        categories: ['a', 'b'],
        series: [{ name: 's', data: [1, 2], band: { lower: [0, 1], upper: [2, 3] } }],
      }),
    );
    expect(plan?.spec.series?.[0].band).toEqual({ lower: [0, 1], upper: [2, 3] });
  });

  it('draws a treemap as a bar chart AND says the chart engine draws no treemap', () => {
    const plan = chartBlockToSpec(
      block({ chartType: 'treemap', categories: ['a', 'b'], series: [{ name: 's', data: [1, 2] }] }),
    );
    expect(plan?.spec.kind).toBe('bar');
    expect(plan?.notes.join(' ')).toMatch(/treemap/i);
  });

  it('draws a gauge as a bar chart AND says so', () => {
    const plan = chartBlockToSpec(
      block({ chartType: 'gauge', categories: ['a'], series: [{ name: 's', data: [42] }] }),
    );
    expect(plan?.spec.kind).toBe('bar');
    expect(plan?.notes.join(' ')).toMatch(/gauge/i);
  });

  it('never fabricates a category that was not supplied', () => {
    const plan = chartBlockToSpec(
      block({ chartType: 'line', categories: ['a'], series: [{ name: 's', data: [1, 2] }] }),
    );
    expect(plan?.spec.categories).toEqual(['a', '#2']);
  });
});
