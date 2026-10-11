import { describe, expect, it } from 'vitest';
import { backtestClient, formatMetric } from './backtest-client';

describe('backtest client helpers', () => {
  it('formats percentages, ratios and counts', () => {
    expect(formatMetric('total_return', 12.345)).toBe('12.35%');
    expect(formatMetric('max_drawdown', -9.0909)).toBe('-9.09%');
    expect(formatMetric('sharpe', 1.23456)).toBe('1.23');
    expect(formatMetric('profit_factor', 2.5)).toBe('2.50');
    expect(formatMetric('trade_count', 7.0)).toBe('7');
    expect(formatMetric('max_winning_streak', 3.0)).toBe('3');
  });

  it('renders an honest dash for unavailable metrics', () => {
    expect(formatMetric('sharpe', null)).toBe('—');
    expect(formatMetric('profit_factor', undefined)).toBe('—');
    expect(formatMetric('cagr', Number.NaN)).toBe('—');
  });

  it('exposes the research engine calls', () => {
    for (const key of ['optimize', 'walkForward', 'monteCarlo', 'sensitivity', 'robustness'] as const) {
      expect(typeof backtestClient[key]).toBe('function');
    }
  });

  it('exposes the strategy portability calls', () => {
    for (const key of [
      'listVersions', 'getVersionMeta', 'diffVersions', 'exportStrategy', 'getBundle',
      'importStrategy',
    ] as const) {
      expect(typeof backtestClient[key]).toBe('function');
    }
  });

  it('exposes the strategy graph compiler calls', () => {
    for (const key of ['listGraphNodes', 'compileGraph', 'validateGraph'] as const) {
      expect(typeof backtestClient[key]).toBe('function');
    }
  });

  it('exposes the Python strategy lab call', () => {
    expect(typeof backtestClient.runPythonStrategy).toBe('function');
  });

  it('exposes the copilot calls', () => {
    for (const key of ['researchPlan', 'report', 'signals'] as const) {
      expect(typeof backtestClient[key]).toBe('function');
    }
  });
});
