import { describe, expect, it } from 'vitest';
import { parseResponsePayload } from './contract';
import { chartBlockToSpec } from './chart-spec';

describe('a point written the way a model writes it', () => {
  it('reads an object with named fields', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'chart',
          chartType: 'regression',
          panels: [
            {
              marks: [
                {
                  type: 'regression',
                  data: [
                    { i: '1', close: '188.70' },
                    { i: '2', close: '190.20' },
                    { i: '3', close: '189.40' },
                  ],
                },
              ],
            },
          ],
        },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    if (block.type !== 'chart') throw new Error('not a chart');
    const mark = chartBlockToSpec(block)?.spec.panels?.[0]?.marks?.[0];
    // The named fields became a point: `i` is the x, `close` is the y.
    expect(mark?.data).toEqual([
      [1, 188.7],
      [2, 190.2],
      [3, 189.4],
    ]);
  });

  it('reads an object with x and y', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'chart',
          chartType: 'scatter',
          panels: [{ marks: [{ type: 'scatter', y: [{ x: 1, y: 2 }, { x: 3, y: 4 }] }] }],
        },
      ],
    });
    const block = parsed.blocks[0];
    if (block.type !== 'chart') throw new Error('not a chart');
    const mark = chartBlockToSpec(block)?.spec.panels?.[0]?.marks?.[0];
    expect(mark?.y).toEqual([
      [1, 2],
      [3, 4],
    ]);
  });

  it('reads an object with unnamed numeric fields, in order', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'chart',
          chartType: 'scatter',
          panels: [{ marks: [{ type: 'scatter', y: [{ t: 5, v: 9 }, { t: 6, v: 11 }] }] }],
        },
      ],
    });
    const block = parsed.blocks[0];
    if (block.type !== 'chart') throw new Error('not a chart');
    const mark = chartBlockToSpec(block)?.spec.panels?.[0]?.marks?.[0];
    expect(mark?.y).toEqual([
      [5, 9],
      [6, 11],
    ]);
  });

  it('still reads a plain pair', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'chart',
          chartType: 'scatter',
          panels: [{ marks: [{ type: 'scatter', y: [[1, 2], [3, 4]] }] }],
        },
      ],
    });
    const block = parsed.blocks[0];
    if (block.type !== 'chart') throw new Error('not a chart');
    const mark = chartBlockToSpec(block)?.spec.panels?.[0]?.marks?.[0];
    expect(mark?.y).toEqual([
      [1, 2],
      [3, 4],
    ]);
  });
});
