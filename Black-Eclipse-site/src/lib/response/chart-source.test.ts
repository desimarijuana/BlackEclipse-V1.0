import { describe, expect, it } from 'vitest';
import { parseResponsePayload, validateBlock } from './contract';
import { chartBlockToSpec } from './chart-spec';

describe('a chart that names its series', () => {
  it('is accepted by the contract', () => {
    const validated = validateBlock({
      type: 'chart',
      chartType: 'regression',
      dataSource: { symbol: 'AAPL', market: 'US', interval: '1d' },
    });
    expect(validated.diagnostic).toBeUndefined();
  });

  it('reaches the engine as a source, not as prices', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'chart',
          chartType: 'regression',
          title: "AAPL's daily close",
          dataSource: { symbol: 'AAPL', market: 'US', interval: '1d' },
        },
      ],
    });
    const block = parsed.blocks[0];
    if (block.type !== 'chart') throw new Error('not a chart');
    const plan = chartBlockToSpec(block);
    const mark = plan?.spec.panels?.[0]?.marks?.[0];
    expect(mark?.type).toBe('regression');
    expect(mark?.dataSource?.symbol).toBe('AAPL');
    // The model typed NO prices: that is the whole point.
    expect(mark?.y).toBeUndefined();
  });

  it('carries a scene mark\'s source through', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'chart',
          chartType: 'scatter',
          panels: [
            {
              marks: [
                { type: 'scatter', dataSource: { symbol: 'GC=F', field: 'close' } },
              ],
            },
          ],
        },
      ],
    });
    const block = parsed.blocks[0];
    if (block.type !== 'chart') throw new Error('not a chart');
    const mark = chartBlockToSpec(block)?.spec.panels?.[0]?.marks?.[0];
    expect(mark?.dataSource?.symbol).toBe('GC=F');
    expect(mark?.dataSource?.field).toBe('close');
  });
});
