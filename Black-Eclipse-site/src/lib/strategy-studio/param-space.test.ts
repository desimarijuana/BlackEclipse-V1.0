import { describe, expect, it } from 'vitest';
import {
  buildAxisValues,
  buildParamSpace,
  defaultRanges,
  deriveParamAxes,
  spaceSize,
  type AxisRange,
} from './param-space';

const spec = {
  strategy: { id: 'ema_cross', name: 'EMA Cross', version: '1.0.0' },
  universe: { symbols: ['BTC-USD'] },
  timeframes: { primary: '1d' },
  indicators: [
    { id: 'ema_fast', type: 'ema', params: { period: 12 } },
    { id: 'ema_slow', type: 'ema', params: { period: 50 } },
    { id: 'atr', type: 'atr', params: { period: 14, smoothing: 'wilder' } },
  ],
  rules: {
    entry: { long: { type: 'group', combine: 'all', conditions: [] } },
    exit: {
      long: { type: 'group', combine: 'all', conditions: [] },
      stop_loss: { type: 'atr', value: 2 },
      take_profit: { type: 'risk_reward', value: 3 },
    },
  },
  position_sizing: { type: 'percent_equity', value: 50 },
  risk: { max_position_pct: 100, max_open_positions: 1, allow_long: true, allow_short: false },
};

function axis(path: string) {
  return deriveParamAxes(spec).find((item) => item.path === path);
}

describe('parameter axes', () => {
  it('derives the numeric indicator params and skips categorical ones', () => {
    expect(axis('indicators.0.params.period')?.base).toBe(12);
    expect(axis('indicators.1.params.period')?.base).toBe(50);
    expect(axis('indicators.2.params.period')?.base).toBe(14);
    expect(axis('indicators.2.params.smoothing')).toBeUndefined();
  });

  it('labels axes with the indicator id', () => {
    expect(axis('indicators.0.params.period')?.label).toBe('ema_fast.period');
  });

  it('treats periods as integers and stops as decimals', () => {
    expect(axis('indicators.0.params.period')?.integer).toBe(true);
    expect(axis('indicators.0.params.period')?.values.every(Number.isInteger)).toBe(true);
    expect(axis('rules.exit.stop_loss.value')?.integer).toBe(false);
    expect(axis('rules.exit.stop_loss.value')?.values).toContain(2);
  });

  it('derives sizing, risk and stop axes', () => {
    expect(axis('position_sizing.value')?.base).toBe(50);
    expect(axis('rules.exit.take_profit.value')?.base).toBe(3);
    expect(axis('risk.max_open_positions')?.integer).toBe(true);
  });

  it('never proposes a zero or negative period', () => {
    const small = { ...spec, indicators: [{ id: 'ema', type: 'ema', params: { period: 2 } }] };
    const axes = deriveParamAxes(small);
    expect(axes[0].values.every((value) => value >= 1)).toBe(true);
  });

  it('returns nothing for a missing or malformed spec', () => {
    expect(deriveParamAxes(null)).toEqual([]);
    expect(deriveParamAxes({ indicators: 'nope', rules: 3 })).toEqual([]);
  });

  it('builds a candidate list from a user-edited range', () => {
    const range: AxisRange = { path: 'x', min: 10, max: 14, step: 2, integer: true };
    expect(buildAxisValues(range)).toEqual([10, 12, 14]);
    expect(buildAxisValues({ ...range, step: 1, min: 2, max: 6 })).toEqual([2, 3, 4, 5, 6]);
  });

  it('caps an absurd range instead of hanging', () => {
    const values = buildAxisValues({ path: 'x', min: 0, max: 1_000_000, step: 0.0001, integer: false });
    expect(values.length).toBeLessThanOrEqual(50);
  });

  it('builds the runtime paramSpace shape', () => {
    const space = buildParamSpace([
      { path: 'indicators.0.params.period', min: 10, max: 12, step: 2, integer: true },
      { path: 'rules.exit.stop_loss.value', min: 1, max: 2, step: 1, integer: false },
    ]);
    expect(space).toEqual({
      'indicators.0.params.period': [10, 12],
      'rules.exit.stop_loss.value': [1, 2],
    });
  });

  it('selects every derived axis by default and reports the grid size', () => {
    const ranges = defaultRanges(deriveParamAxes(spec));
    expect(ranges.length).toBe(deriveParamAxes(spec).length);
    expect(spaceSize(ranges)).toBeGreaterThan(1);
  });
});
