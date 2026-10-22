import { describe, expect, it } from 'vitest';
import { parseResponsePayload } from './contract';
import { chartBlockToSpec } from './chart-spec';

describe('a mark that writes points as pairs', () => {
  it('is accepted by the contract', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'chart',
          chartType: 'scatter',
          panels: [
            {
              marks: [
                { type: 'scatter', data: [[1, 258.45], [2, 259.99], [3, 257.2]] },
              ],
            },
          ],
        },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    expect(parsed.blocks[0].type).toBe('chart');
  });

  it('keeps the pairs on the way to the engine', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'chart',
          chartType: 'scatter',
          panels: [
            { marks: [{ type: 'regression', data: [[1, 258.45], [2, 259.99]] }] },
          ],
        },
      ],
    });
    const block = parsed.blocks[0];
    if (block.type !== 'chart') throw new Error('not a chart');
    const mark = chartBlockToSpec(block)?.spec.panels?.[0]?.marks?.[0];
    expect(mark?.data).toEqual([[1, 258.45], [2, 259.99]]);
  });

  it('accepts a pair in the simple form too', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'chart',
          chartType: 'regression',
          series: [{ name: 'Observed', data: [[1, 258.45], [2, 259.99], [3, 257.2]] }],
        },
      ],
    });
    const block = parsed.blocks[0];
    if (block.type !== 'chart') throw new Error('not a chart');
    const mark = chartBlockToSpec(block)?.spec.panels?.[0]?.marks?.[0];
    expect(mark?.type).toBe('regression');
    expect(mark?.x).toEqual([1, 2, 3]);
    expect(mark?.y).toEqual([258.45, 259.99, 257.2]);
  });
});
