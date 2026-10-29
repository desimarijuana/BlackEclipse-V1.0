import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SpecBuilder } from './spec-builder';

const spec = {
  strategy: { id: 'ema_trend', name: 'EMA trend', version: '1.0.0' },
  universe: { symbols: ['BTC-USD'] },
  indicators: [
    { id: 'ema_fast', type: 'ema', params: { period: 20 } },
    { id: 'ema_slow', type: 'ema', params: { period: 50 } },
    { id: 'atr', type: 'atr', params: { period: 14 } },
  ],
  rules: {
    entry: {
      long: {
        type: 'group',
        combine: 'all',
        conditions: [
          { type: 'condition', left: { ref: 'ema_fast' }, op: 'cross_above', right: { ref: 'ema_slow' } },
        ],
      },
    },
    exit: {
      long: {
        type: 'group',
        combine: 'all',
        conditions: [{ type: 'condition', left: { ref: 'close' }, op: '<', right: { ref: 'ema_fast' } }],
      },
      stop_loss: { type: 'atr', value: 2 },
      take_profit: { type: 'risk_reward', value: 3 },
    },
  },
  position_sizing: { type: 'percent_equity', value: 50 },
  risk: { max_position_pct: 100, max_open_positions: 1, allow_long: true, allow_short: false },
  execution: {
    commission: { type: 'percentage', value: 0.1 },
    slippage: { type: 'percentage', value: 0.05 },
    spread: { type: 'bps', value: 5 },
  },
};

describe('SpecBuilder', () => {
  it('renders indicator params and condition rows instead of raw JSON', () => {
    const html = renderToStaticMarkup(<SpecBuilder spec={spec} onChange={() => undefined} />);
    expect(html).toContain('ema_fast');
    expect(html).toContain('ema_slow');
    expect(html).toContain('cross_above');
    expect(html).toContain('Entry (long)');
    expect(html).toContain('Risk and exits');
    expect(html).toContain('Execution costs');
  });

  it('warns instead of rewriting an advanced condition', () => {
    const advanced = JSON.parse(JSON.stringify(spec)) as typeof spec;
    advanced.rules.entry.long.conditions = [
      {
        type: 'condition',
        left: { expr: { op: '+', left: { ref: 'close' }, right: { value: 1 } } },
        op: '>',
        right: { value: 0 },
      },
    ] as never;
    const html = renderToStaticMarkup(<SpecBuilder spec={advanced} onChange={() => undefined} />);
    expect(html).toContain('advanced condition 1 — edit in JSON');
  });

  it('edits a nested group in place', () => {
    const nested = JSON.parse(JSON.stringify(spec)) as {
      rules: { entry: { long: { conditions: Array<Record<string, unknown>> } } };
    };
    nested.rules.entry.long.conditions.push({
      type: 'group',
      combine: 'any',
      conditions: [{ type: 'condition', left: { ref: 'rsi' }, op: '<', right: { value: 30 } }],
    });
    const html = renderToStaticMarkup(<SpecBuilder spec={nested} onChange={() => undefined} />);
    expect(html).toContain('group 2');
    expect(html).toContain('+ condition');
    expect(html).toContain('+ group');
  });
});
