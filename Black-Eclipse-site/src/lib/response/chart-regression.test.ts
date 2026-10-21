import { describe, expect, it } from 'vitest';
import { parseResponsePayload, validateBlock } from './contract';
import { chartBlockToSpec } from './chart-spec';
import type { ChartBlock } from './contract';

function chartBlockFrom(raw: Record<string, unknown>): ChartBlock {
  const parsed = parseResponsePayload({ blocks: [raw] });
  const block = parsed.blocks[0];
  if (block.type !== 'chart') throw new Error('the block is not a chart');
  return block;
}

describe('a regression chart', () => {
  it('is a kind the contract knows', () => {
    const block = chartBlockFrom({
      type: 'chart',
      chartType: 'regression',
      series: [{ name: 'Price', data: [[1, 2], [2, 4], [3, 6]] }],
    });
    expect(block.chartType).toBe('regression');
  });

  it('reads the synonyms a producer may use', () => {
    for (const spoken of ['linear_regression', 'linear regression', 'trendline', 'ols', 'fit']) {
      const block = chartBlockFrom({
        type: 'chart',
        chartType: spoken,
        series: [{ name: 'Price', data: [[1, 2], [2, 4], [3, 6]] }],
      });
      expect(block.chartType).toBe('regression');
    }
  });

  it('survives an unknown kind instead of losing the whole chart', () => {
    // One odd kind must never cost the reader every other panel.
    const block = chartBlockFrom({
      type: 'chart',
      chartType: 'quantum_bubble',
      series: [{ name: 'Price', data: [[1, 2], [2, 4], [3, 6]] }],
    });
    expect(block.chartType).toBe('auto');
    expect(chartBlockToSpec(block)).not.toBeNull();
  });

  it('is drawn as the points and a regression mark', () => {
    const block = chartBlockFrom({
      type: 'chart',
      chartType: 'regression',
      series: [{ name: 'Price', data: [[1, 2.1], [2, 3.9], [3, 6.2]] }],
    });
    const plan = chartBlockToSpec(block);
    expect(plan).not.toBeNull();
    expect(plan?.kind).toBe('scene');
    const marks = plan?.spec.panels?.[0]?.marks ?? [];
    expect(marks[0]?.type).toBe('regression');
    expect(marks[0]?.x).toEqual([1, 2, 3]);
    expect(marks[0]?.y).toEqual([2.1, 3.9, 6.2]);
  });

  it('uses numeric categories as the x axis', () => {
    const block = chartBlockFrom({
      type: 'chart',
      chartType: 'regression',
      categories: [10, 20, 30],
      series: [{ name: 'Price', data: [2, 4, 6] }],
    });
    const marks = chartBlockToSpec(block)?.spec.panels?.[0]?.marks ?? [];
    expect(marks[0]?.x).toEqual([10, 20, 30]);
    expect(marks[0]?.y).toEqual([2, 4, 6]);
  });

  it('says so when the categories are labels, not numbers', () => {
    const block = chartBlockFrom({
      type: 'chart',
      chartType: 'regression',
      categories: ['Q1', 'Q2', 'Q3'],
      series: [{ name: 'Revenue', data: [2, 4, 6] }],
    });
    const plan = chartBlockToSpec(block);
    expect(plan?.notes.join(' ')).toContain('series order');
    const marks = plan?.spec.panels?.[0]?.marks ?? [];
    expect(marks[0]?.x).toEqual([0, 1, 2]);
  });

  it('draws nothing when there is nothing to fit', () => {
    const block = chartBlockFrom({
      type: 'chart',
      chartType: 'regression',
      series: [{ name: 'Price', data: [[1, 2]] }],
    });
    expect(chartBlockToSpec(block)).toBeNull();
  });

  it('is still a valid block for the validator', () => {
    const validated = validateBlock({
      type: 'chart',
      chartType: 'regression',
      series: [{ name: 'Price', data: [[1, 2], [2, 4]] }],
    });
    expect(validated.diagnostic).toBeUndefined();
    expect(validated.block.type).toBe('chart');
  });

  it('is still a valid block when the kind is unknown', () => {
    const validated = validateBlock({
      type: 'chart',
      chartType: 'quantum_bubble',
      series: [{ name: 'Price', data: [[1, 2], [2, 4]] }],
    });
    expect(validated.diagnostic).toBeUndefined();
    expect(validated.block.type).toBe('chart');
  });
});
