import { describe, it, expect } from 'vitest';
import {
  buildChartOption,
  chartHasData,
  directChartType,
  mergeChartOption,
  resolveChartType,
} from './chart-option';
import { validateBlock, type ChartBlock } from './contract';

const palette = { primary: '#7aff78', series: ['#60a5fa', '#fbbf24'] };

function chart(raw: unknown): ChartBlock {
  const { block } = validateBlock(raw);
  if (block.type !== 'chart') throw new Error('expected chart block');
  return block;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
describe('buildChartOption', () => {
  it('builds a line chart with a category axis and one series per series entry', () => {
    const option = buildChartOption(
      chart({ type: 'chart', chartType: 'line', categories: ['a', 'b'], series: [{ name: 'BTC', data: [1, 2] }, { name: 'ETH', data: [3, 4] }] }),
      palette,
    ) as any;
    expect(option.xAxis.data).toEqual(['a', 'b']);
    expect(option.series).toHaveLength(2);
    expect(option.series[0].type).toBe('line');
  });

  it('maps a pie chart from the first series + categories', () => {
    const option = buildChartOption(
      chart({ type: 'chart', chartType: 'pie', categories: ['A', 'B'], series: [{ name: 'mix', data: [60, 40] }] }),
      palette,
    ) as any;
    expect(option.series[0].type).toBe('pie');
    expect(option.series[0].data).toEqual([{ name: 'A', value: 60 }, { name: 'B', value: 40 }]);
  });

  it('uses value axes for scatter', () => {
    const option = buildChartOption(
      chart({ type: 'chart', chartType: 'scatter', series: [{ name: 'p', data: [[1, 2], [3, 4]] }] }),
      palette,
    ) as any;
    expect(option.xAxis.type).toBe('value');
    expect(option.series[0].type).toBe('scatter');
  });

  it('adds a visualMap for heatmaps', () => {
    const option = buildChartOption(
      chart({ type: 'chart', chartType: 'heatmap', categories: ['x1', 'x2'], series: [{ name: 'y1', data: [1, 2] }] }),
      palette,
    ) as any;
    expect(option.series[0].type).toBe('heatmap');
    expect(option.visualMap).toBeTruthy();
  });

  it('stacked_bar sets the stack key', () => {
    const option = buildChartOption(
      chart({ type: 'chart', chartType: 'stacked_bar', categories: ['a'], series: [{ name: 's', data: [1] }] }),
      palette,
    ) as any;
    expect(option.series[0].stack).toBe('total');
  });

  it('chartHasData is false for an all-null series', () => {
    const block = chart({ type: 'chart', chartType: 'line', categories: ['a'], series: [{ name: 's', data: [null] }] });
    expect(chartHasData(block)).toBe(false);
  });

  it('the built option carries no tooltip chrome of its own (base recipe survives a merge)', () => {
    const option = buildChartOption(
      chart({ type: 'chart', chartType: 'line', categories: ['a'], series: [{ name: 's', data: [1] }] }),
      palette,
    ) as any;
    // The bare builder must NOT set the frosted chrome — that lives in the base.
    expect(option.tooltip.backgroundColor).toBeUndefined();
    expect(option.tooltip.appendTo).toBeUndefined();
    // …but it must carry the block-specific trigger + formatter.
    expect(option.tooltip.trigger).toBe('axis');
    expect(typeof option.tooltip.valueFormatter).toBe('function');
  });

  it('mergeChartOption keeps the frosted tooltip chrome and the block trigger', () => {
    const base = {
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(18,18,20,0.5)',
        appendTo: 'body',
        extraCssText: 'backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px;',
      },
    } as any;
    const built = buildChartOption(
      chart({ type: 'chart', chartType: 'scatter', series: [{ name: 'p', data: [[1, 2]] }] }),
      palette,
    );
    const merged = mergeChartOption(base, built) as any;
    expect(merged.tooltip.trigger).toBe('item'); // block wins
    expect(merged.tooltip.backgroundColor).toBe('rgba(18,18,20,0.5)'); // chrome survives
    expect(merged.tooltip.appendTo).toBe('body');
    expect(merged.tooltip.extraCssText).toContain('backdrop-filter');
  });

  it('uses light ink on a light scheme and dark ink on a dark scheme', () => {
    const block = chart({ type: 'chart', chartType: 'line', categories: ['a'], series: [{ name: 's', data: [1] }] });
    const dark = buildChartOption(block, palette, true) as any;
    const light = buildChartOption(block, palette, false) as any;
    expect(dark.yAxis.axisLabel.color).not.toBe(light.yAxis.axisLabel.color);
    expect(dark.yAxis.splitLine.lineStyle.color).not.toBe(light.yAxis.splitLine.lineStyle.color);
  });

  it('draws smooth lines with rounded, width-capped bars and theme-aware animation', () => {
    const line = buildChartOption(
      chart({ type: 'chart', chartType: 'line', categories: ['a', 'b'], series: [{ name: 's', data: [1, 2] }] }),
      palette,
    ) as any;
    expect(line.series[0].smooth).toBe(true);
    expect(line.animation).toBe(true);
    const bar = buildChartOption(
      chart({ type: 'chart', chartType: 'bar', categories: ['a'], series: [{ name: 's', data: [1] }] }),
      palette,
    ) as any;
    expect(bar.series[0].itemStyle.borderRadius).toEqual([5, 5, 0, 0]);
    expect(bar.series[0].barMaxWidth).toBeGreaterThan(0);
  });
});

describe('buildChartOption — extended chart types', () => {
  it('maps treemap and sunburst from categories + the first series', () => {
    const treemap = buildChartOption(
      chart({ type: 'chart', chartType: 'treemap', categories: ['A', 'B'], series: [{ name: 'mix', data: [60, 40] }] }),
      palette,
    ) as any;
    expect(treemap.series[0].type).toBe('treemap');
    expect(treemap.series[0].data).toEqual([{ name: 'A', value: 60 }, { name: 'B', value: 40 }]);

    const sunburst = buildChartOption(
      chart({ type: 'chart', chartType: 'sunburst', categories: ['A', 'B'], series: [{ name: 'mix', data: [60, 40] }] }),
      palette,
    ) as any;
    expect(sunburst.series[0].type).toBe('sunburst');
  });

  it('maps a funnel from the first series', () => {
    const option = buildChartOption(
      chart({ type: 'chart', chartType: 'funnel', categories: ['Visit', 'Buy'], series: [{ name: 'f', data: [100, 12] }] }),
      palette,
    ) as any;
    expect(option.series[0].type).toBe('funnel');
    expect(option.series[0].data).toEqual([{ name: 'Visit', value: 100 }, { name: 'Buy', value: 12 }]);
  });

  it('builds a gauge with a nice-rounded max and item tooltip', () => {
    const option = buildChartOption(
      chart({ type: 'chart', chartType: 'gauge', series: [{ name: 'Confidence', data: [42] }] }),
      palette,
    ) as any;
    expect(option.series[0].type).toBe('gauge');
    expect(option.series[0].max).toBe(50);
    expect(option.series[0].data[0].value).toBe(42);
    expect(option.tooltip.trigger).toBe('item');
  });

  it('builds a radar with one indicator per category and one series per entry', () => {
    const option = buildChartOption(
      chart({ type: 'chart', chartType: 'radar', categories: ['A', 'B', 'C'], series: [{ name: 's', data: [1, 2, 3] }] }),
      palette,
    ) as any;
    expect(option.series[0].type).toBe('radar');
    expect(option.radar.indicator).toHaveLength(3);
    expect(option.series[0].data[0].value).toEqual([1, 2, 3]);
  });

  it('stacks a waterfall as a transparent base plus a signed bar', () => {
    const option = buildChartOption(
      chart({ type: 'chart', chartType: 'waterfall', categories: ['a', 'b', 'c'], series: [{ name: 'Change', data: [10, -5, 3] }] }),
      palette,
    ) as any;
    expect(option.series).toHaveLength(2);
    expect(option.series[0].stack).toBe('waterfall');
    expect(option.series[0].data).toEqual([0, 5, 5]);
    expect(option.series[1].data[0].value).toBe(10);
    expect(option.series[1].data[1].itemStyle.color).toBe(palette.series[0]);
  });

  it('uses size-carrying triples for bubble charts', () => {
    const option = buildChartOption(
      chart({ type: 'chart', chartType: 'bubble', series: [{ name: 'p', data: [[1, 2, 3], [4, 5, 9]] }] }),
      palette,
    ) as any;
    expect(option.xAxis.type).toBe('value');
    expect(option.series[0].type).toBe('scatter');
    expect(option.series[0].data[0].value).toEqual([1, 2, 3]);
    expect(option.series[0].data[1].symbolSize).toBeGreaterThan(option.series[0].data[0].symbolSize);
  });
});

describe('visual director', () => {
  it('chooses a line for temporal categories', () => {
    const block = chart({
      type: 'chart', chartType: 'auto',
      categories: ['2026-01-01', '2026-02-01', '2026-03-01'],
      series: [{ name: 's', data: [1, 2, 3] }],
    });
    expect(directChartType(block)).toBe('line');
    const option = buildChartOption(block, palette) as any;
    expect(option.series[0].type).toBe('line');
  });

  it('chooses a bar for a short, non-temporal single series', () => {
    const block = chart({
      type: 'chart', chartType: 'auto', categories: ['Alpha', 'Beta', 'Gamma'],
      series: [{ name: 's', data: [1, 2, 3] }],
    });
    expect(directChartType(block)).toBe('bar');
    expect((buildChartOption(block, palette) as any).series[0].type).toBe('bar');
  });

  it('chooses a line for a long single series without temporal labels', () => {
    const block = chart({
      type: 'chart', chartType: 'auto',
      categories: Array.from({ length: 20 }, (_, i) => `Item ${i}`),
      series: [{ name: 's', data: Array.from({ length: 20 }, (_, i) => i) }],
    });
    expect(directChartType(block)).toBe('line');
  });

  it('chooses scatter for non-monotonic pairs and bubble for triples', () => {
    const scatter = chart({
      type: 'chart', chartType: 'auto',
      series: [{ name: 'p', data: [[3, 2], [1, 4], [2, 1]] }],
    });
    const bubble = chart({
      type: 'chart', chartType: 'auto',
      series: [{ name: 'p', data: [[1, 2, 3], [2, 3, 4]] }],
    });
    expect(directChartType(scatter)).toBe('scatter');
    expect(directChartType(bubble)).toBe('bubble');
  });

  it('never overrides an explicit type', () => {
    const block = chart({
      type: 'chart', chartType: 'bar', categories: ['2026-01-01', '2026-02-01'],
      series: [{ name: 's', data: [1, 2] }],
    });
    expect(resolveChartType(block)).toBe('bar');
  });
});

describe('series weight and bands', () => {
  it('maps weight to line width and opacity, leaving absent weight unchanged', () => {
    const plain = buildChartOption(
      chart({ type: 'chart', chartType: 'line', categories: ['a'], series: [{ name: 's', data: [1] }] }),
      palette,
    ) as any;
    const light = buildChartOption(
      chart({ type: 'chart', chartType: 'line', categories: ['a'], series: [{ name: 's', data: [1], weight: 0 }] }),
      palette,
    ) as any;
    const heavy = buildChartOption(
      chart({ type: 'chart', chartType: 'line', categories: ['a'], series: [{ name: 's', data: [1], weight: 1 }] }),
      palette,
    ) as any;
    expect(plain.series[0].lineStyle.width).toBe(2.4);
    expect(plain.series[0].lineStyle.opacity).toBe(1);
    expect(light.series[0].lineStyle.width).toBe(1.2);
    expect(light.series[0].lineStyle.opacity).toBeCloseTo(0.45);
    expect(heavy.series[0].lineStyle.width).toBe(3.6);
    expect(heavy.series[0].lineStyle.opacity).toBeCloseTo(1);
  });

  it('draws a band as a hidden lower/delta stack and keeps it out of the legend', () => {
    const option = buildChartOption(
      chart({
        type: 'chart', chartType: 'line', categories: ['a', 'b'],
        series: [
          {
            name: 'Forecast', data: [10, 20], weight: 1,
            band: { lower: [8, 15], upper: [12, 25], weight: 1 },
          },
          { name: 'Actual', data: [9, 18] },
        ],
      }),
      palette,
    ) as any;
    expect(option.series).toHaveLength(4);
    expect(option.series[2].name).toBe('__band_lower_0');
    expect(option.series[3].name).toBe('__band_0');
    expect(option.series[2].data).toEqual([8, 15]);
    expect(option.series[3].data).toEqual([4, 10]);
    expect(option.series[2].stack).toBe(option.series[3].stack);
    expect(option.series[3].areaStyle.color).toContain('rgba(');
    expect(option.legend.data).toEqual(['Forecast', 'Actual']);
  });

  it('truncates a band to the shortest supplied array', () => {
    const option = buildChartOption(
      chart({
        type: 'chart', chartType: 'line', categories: ['a', 'b'],
        series: [{ name: 's', data: [1, 2], band: { lower: [0.5], upper: [2, 3] } }],
      }),
      palette,
    ) as any;
    expect(option.series[1].data).toEqual([0.5]);
    expect(option.series[2].data).toEqual([1.5]);
  });

  it('does not draw a band on a value axis (pairs)', () => {
    const option = buildChartOption(
      chart({
        type: 'chart', chartType: 'line',
        series: [{ name: 's', data: [[1, 2], [2, 3]], band: { lower: [1, 2], upper: [3, 4] } }],
      }),
      palette,
    ) as any;
    expect(option.series).toHaveLength(1);
  });
});
