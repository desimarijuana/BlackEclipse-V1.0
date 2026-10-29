import { describe, expect, it } from 'vitest';
import type { ResearchResult } from '@/lib/backtest/backtest-client';
import { summarizeResearch } from './research-verdict';

function research(partial: Partial<ResearchResult>): ResearchResult {
  return {
    status: 'OK',
    kind: 'walk_forward',
    metrics: {},
    warnings: [],
    observability: {},
    configuration: {},
    ...partial,
  } as ResearchResult;
}

const goodWf = research({
  kind: 'walk_forward',
  inSampleAggregate: { sharpe: 1.2, trade_count: 40 },
  outOfSampleAggregate: { sharpe: 0.9, trade_count: 12 },
});

const goodMc = research({ kind: 'monte_carlo', probabilityOfRuin: 0, probabilityOfLoss: 22, worstDrawdown: 14.2 });

const goodRb = research({ kind: 'robustness', verdict: 'robust', conclusions: [] });

describe('research verdict', () => {
  it('is inconclusive when nothing has been run', () => {
    const summary = summarizeResearch({});
    expect(summary.overall).toBe('inconclusive');
    expect(summary.checks).toEqual([]);
    expect(summary.notes.length).toBe(3);
  });

  it('calls a complete, passing suite robust', () => {
    const summary = summarizeResearch({ walkForward: goodWf, monteCarlo: goodMc, robustness: goodRb });
    expect(summary.overall).toBe('robust');
    expect(summary.checks.filter((check) => check.kind === 'check').every((check) => check.state === 'pass')).toBe(true);
  });

  it('fails on a negative out-of-sample Sharpe', () => {
    const wf = research({ outOfSampleAggregate: { sharpe: -0.2, trade_count: 5 }, inSampleAggregate: { sharpe: 1 } });
    const summary = summarizeResearch({ walkForward: wf, monteCarlo: goodMc, robustness: goodRb });
    expect(summary.overall).toBe('fragile');
    expect(summary.checks.find((check) => check.id === 'oos-sharpe')?.state).toBe('fail');
  });

  it('fails on a high simulated ruin probability', () => {
    const mc = research({ probabilityOfRuin: 12 });
    const summary = summarizeResearch({ walkForward: goodWf, monteCarlo: mc, robustness: goodRb });
    expect(summary.overall).toBe('fragile');
    expect(summary.checks.find((check) => check.id === 'ruin')?.state).toBe('fail');
  });

  it('fails when the engine calls the strategy fragile', () => {
    const rb = research({ verdict: 'fragile' });
    const summary = summarizeResearch({ walkForward: goodWf, monteCarlo: goodMc, robustness: rb });
    expect(summary.overall).toBe('fragile');
  });

  it('keeps missing measurements unknown rather than passing them', () => {
    const wf = research({});
    const summary = summarizeResearch({ walkForward: wf });
    expect(summary.overall).toBe('inconclusive');
    expect(summary.checks.filter((check) => check.kind === 'check').every((check) => check.state === 'unknown')).toBe(true);
  });

  it('reports the worst drawdown and loss probability without scoring them', () => {
    const summary = summarizeResearch({ monteCarlo: goodMc });
    expect(summary.checks.find((check) => check.id === 'worst-drawdown')?.kind).toBe('info');
    expect(summary.checks.find((check) => check.id === 'probability-of-loss')?.detail).toContain('22');
  });

  it('does not claim a robust verdict when the suite is incomplete', () => {
    const summary = summarizeResearch({ walkForward: goodWf, monteCarlo: goodMc });
    expect(summary.overall).toBe('inconclusive');
  });
});
