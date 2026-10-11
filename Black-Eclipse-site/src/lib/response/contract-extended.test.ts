import { describe, it, expect } from 'vitest';
import { parseResponsePayload } from './contract';

describe('extended response blocks', () => {
  it('validates a financial_chart block (symbol only)', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'financial_chart', symbol: 'btc', market: 'crypto', timeframe: '1D', chartType: 'candlestick' }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('financial_chart');
    if (block.type === 'financial_chart') expect(block.symbol).toBe('btc');
  });

  it('rejects a financial_chart with an unknown timeframe', () => {
    const parsed = parseResponsePayload({ blocks: [{ type: 'financial_chart', symbol: 'BTC', timeframe: '99X' }] });
    expect(parsed.blocks[0].type).toBe('unknown');
  });

  it('validates a mermaid block', () => {
    const parsed = parseResponsePayload({ blocks: [{ type: 'mermaid', diagram: 'sequenceDiagram\n A->>B: hi' }] });
    expect(parsed.blocks[0].type).toBe('mermaid');
  });

  it('validates a controls block', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'controls',
          title: 'Scenario',
          controls: [
            { kind: 'select', id: 'symbol', label: 'Symbol', options: [{ value: 'BTC', label: 'Bitcoin' }] },
            { kind: 'slider', id: 'rate', label: 'Rate', min: 0, max: 10, default: 5 },
          ],
          promptTemplate: 'Run {{symbol}} at {{rate}}',
        },
      ],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('controls');
    if (block.type === 'controls') expect(block.controls).toHaveLength(2);
  });

  it('rejects a controls block with an unknown control kind', () => {
    const parsed = parseResponsePayload({ blocks: [{ type: 'controls', controls: [{ kind: 'teleport', id: 'x', label: 'X' }] }] });
    expect(parsed.blocks[0].type).toBe('unknown');
  });
});
