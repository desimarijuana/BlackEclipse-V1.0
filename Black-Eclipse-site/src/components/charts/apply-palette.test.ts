import { describe, expect, it } from 'vitest';
import { applyChartPalette, withAlpha } from './apply-palette';
import type { ChartPalette } from '@/lib/chart-palette';

const palette: ChartPalette = {
  candles: { up: '#ffffff', down: '#333333', neutral: '#888888' },
  lines: { primary: '#fafafa', series: ['#fafafa', '#a1a1aa', '#52525b'] },
  heatmap: { up: '#eeeeee', mid: '#222222', down: '#555555' },
};

function figure(data: Array<Record<string, unknown>>) {
  return { data, layout: { title: { text: 'Revenue' } } };
}

describe('applyChartPalette', () => {
  it('paints lines with the user palette in order, wrapping the ramp', () => {
    const styled = applyChartPalette(
      figure([
        { type: 'scatter', mode: 'lines', line: { color: '#0ea5e9', width: 2 } },
        { type: 'scatter', mode: 'lines', line: { color: '#a78bfa', width: 2 } },
        { type: 'scatter', mode: 'lines', line: { color: '#22c55e', width: 2 } },
        { type: 'scatter', mode: 'lines', line: { color: '#f59e0b', width: 2 } },
      ]),
      palette,
    );
    expect(styled!.data.map((t) => t.line)).toEqual([
      { color: '#fafafa', width: 2 },
      { color: '#a1a1aa', width: 2 },
      { color: '#52525b', width: 2 },
      { color: '#fafafa', width: 2 },
    ]);
  });

  it('recolours the area fill from the same series colour', () => {
    const styled = applyChartPalette(
      figure([{ type: 'scatter', mode: 'lines', fill: 'tozeroy', line: { color: '#0ea5e9' } }]),
      palette,
    );
    expect(styled!.data[0].fillcolor).toBe(withAlpha('#fafafa', 0.22));
  });

  it('keeps candles semantic: up / down from the candle pair', () => {
    const styled = applyChartPalette(figure([{ type: 'candlestick' }]), palette);
    expect(styled!.data[0].increasing).toEqual({ line: { color: '#ffffff' } });
    expect(styled!.data[0].decreasing).toEqual({ line: { color: '#333333' } });
  });

  it('gives a heatmap the neutral scale instead of a hue', () => {
    const styled = applyChartPalette(figure([{ type: 'heatmap', colorscale: 'RdBu' }]), palette);
    expect(styled!.data[0].colorscale).toEqual([
      [0, '#555555'],
      [0.5, '#222222'],
      [1, '#eeeeee'],
    ]);
  });

  it('cycles pie slices and leaves the layout untouched', () => {
    const styled = applyChartPalette(figure([{ type: 'pie', labels: ['a', 'b', 'c', 'd'], values: [1, 2, 3, 4] }]), palette);
    expect((styled!.data[0].marker as { colors: string[] }).colors).toEqual([
      '#fafafa',
      '#a1a1aa',
      '#52525b',
      '#fafafa',
    ]);
    expect(styled!.layout).toEqual({ title: { text: 'Revenue' } });
  });

  it('does not mutate the engine figure', () => {
    const source = figure([{ type: 'scatter', line: { color: '#0ea5e9' } }]);
    applyChartPalette(source, palette);
    expect((source.data[0].line as { color: string }).color).toBe('#0ea5e9');
  });

  it('passes null through', () => {
    expect(applyChartPalette(null, palette)).toBeNull();
    expect(applyChartPalette(undefined, palette)).toBeUndefined();
  });
});

describe('withAlpha', () => {
  it('builds rgba from long and short hex, and refuses non-hex', () => {
    expect(withAlpha('#ff0000', 0.5)).toBe('rgba(255,0,0,0.5)');
    expect(withAlpha('#abc', 1)).toBe('rgba(170,187,204,1)');
    expect(withAlpha('red', 0.2)).toBe('red');
  });
});
