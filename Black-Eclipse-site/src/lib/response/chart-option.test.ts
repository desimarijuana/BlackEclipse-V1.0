import { describe, it, expect } from 'vitest';
import { buildChartOption, chartHasData } from './chart-option';
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
});
