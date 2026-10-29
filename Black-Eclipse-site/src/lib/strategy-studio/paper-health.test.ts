import { describe, expect, it } from 'vitest';
import {
  DRIFT_RETURN_POINTS,
  DRIFT_SHARPE,
  STALE_AFTER_DAYS,
  paperHealth,
} from './paper-health';

const NOW = new Date('2026-10-28T12:00:00Z');

function daysAgo(days: number): string {
  return new Date(NOW.getTime() - days * 86_400_000).toISOString();
}

const baseline = { total_return: 20, sharpe: 1.2, max_drawdown: -10 };

describe('paper health', () => {
  it('reports no track record before the first run', () => {
    expect(paperHealth({ now: NOW }).state).toBe('none');
  });

  it('calls a recent, aligned run fresh', () => {
    const health = paperHealth({
      lastRunAt: daysAgo(5),
      paperMetrics: { total_return: 18, sharpe: 1.1, max_drawdown: -11 },
      baselineMetrics: baseline,
      now: NOW,
    });
    expect(health.state).toBe('fresh');
    expect(health.stalenessDays).toBe(5);
  });

  it('flags a run older than the stated limit as stale', () => {
    const health = paperHealth({
      lastRunAt: daysAgo(STALE_AFTER_DAYS + 10),
      paperMetrics: baseline,
      baselineMetrics: baseline,
      now: NOW,
    });
    expect(health.state).toBe('stale');
    expect(health.stalenessDays).toBe(STALE_AFTER_DAYS + 10);
    expect(health.detail).toContain(String(STALE_AFTER_DAYS));
  });

  it('flags a return drift beyond the stated points', () => {
    const health = paperHealth({
      lastRunAt: daysAgo(2),
      paperMetrics: { ...baseline, total_return: baseline.total_return - DRIFT_RETURN_POINTS - 1 },
      baselineMetrics: baseline,
      now: NOW,
    });
    expect(health.state).toBe('drifting');
    expect(health.drift.find((row) => row.metric === 'total_return')?.delta).toBeLessThan(0);
  });

  it('flags a Sharpe drift beyond the stated limit', () => {
    const health = paperHealth({
      lastRunAt: daysAgo(2),
      paperMetrics: { ...baseline, sharpe: baseline.sharpe - DRIFT_SHARPE - 0.1 },
      baselineMetrics: baseline,
      now: NOW,
    });
    expect(health.state).toBe('drifting');
  });

  it('does not drift when the baseline is missing', () => {
    const health = paperHealth({
      lastRunAt: daysAgo(2),
      paperMetrics: { total_return: 5, sharpe: 0.2, max_drawdown: -30 },
      baselineMetrics: null,
      now: NOW,
    });
    expect(health.state).toBe('fresh');
    expect(health.drift.every((row) => row.delta === null)).toBe(true);
  });

  it('prefers stale over drifting when both apply', () => {
    const health = paperHealth({
      lastRunAt: daysAgo(90),
      paperMetrics: { total_return: -10, sharpe: 0.1, max_drawdown: -30 },
      baselineMetrics: baseline,
      now: NOW,
    });
    expect(health.state).toBe('stale');
    expect(health.detail).toContain('also differ');
  });
});
