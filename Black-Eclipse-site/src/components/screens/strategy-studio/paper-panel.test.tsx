import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { PaperPanel } from './paper-panel';
import type { ExperimentSummary, PaperRunRecord } from '@/lib/backtest/backtest-client';

const forwardWindow = {
  mode: 'forward' as const,
  start: '2026-01-01',
  end: '2026-03-01',
  days: 60,
  available: true,
};

const baseProps = {
  hasSaved: true,
  hasResult: true,
  approved: false,
  onApproved: () => undefined,
  busy: false,
  onPromote: () => undefined,
  paper: null,
  onMode: () => undefined,
  track: [] as PaperRunRecord[],
  trackExperiments: {} as Record<string, ExperimentSummary>,
  expected: { total_return: 20, sharpe: 1.2, max_drawdown: -10 },
};

describe('PaperPanel', () => {
  it('shows the exact forward window', () => {
    const html = renderToStaticMarkup(
      <PaperPanel {...baseProps} mode="forward" window={forwardWindow} />,
    );
    expect(html).toContain('forward · 2026-01-01 → 2026-03-01 · 60 days');
    expect(html).toContain('Forward (since the backtest ended)');
  });

  it('labels a replay honestly', () => {
    const html = renderToStaticMarkup(
      <PaperPanel
        {...baseProps}
        mode="replay"
        window={{ ...forwardWindow, mode: 'replay', start: '2024-01-01', end: '2025-01-01' }}
      />,
    );
    expect(html).toContain('it is not forward-looking');
  });

  it('refuses an unavailable forward window instead of downgrading it', () => {
    const html = renderToStaticMarkup(
      <PaperPanel
        {...baseProps}
        mode="forward"
        window={{
          mode: 'forward',
          start: '2026-03-02',
          end: '2026-03-01',
          days: 0,
          available: false,
          reason: 'The research window ends today, so there is no forward period yet.',
        }}
      />,
    );
    expect(html).toContain('no forward period yet');
    expect(html).toContain('disabled');
  });

  it('renders a paper track record with drift', () => {
    const run: PaperRunRecord = {
      id: 'paper_1',
      deploymentId: 'dep_1',
      strategyId: 'ema_trend',
      version: '1.0.0',
      experimentId: 'exp_paper',
      status: 'OK',
      symbols: ['BTC-USD'],
      metrics: { total_return: 18, sharpe: 1.0, max_drawdown: -12 },
      createdAt: '2026-03-02T10:00:00',
      liveExecution: false,
    };
    const experiment = {
      id: 'exp_paper',
      strategyId: 'ema_trend',
      strategyVersion: '1.0.0',
      kind: 'paper',
      symbols: ['BTC-USD'],
      interval: '1d',
      start: '2026-01-01',
      end: '2026-03-01',
      initialCapital: 100000,
      status: 'OK',
      metrics: {},
      warnings: [],
      createdAt: '2026-03-02T10:00:00',
      hasArtifact: true,
    } as ExperimentSummary;

    const html = renderToStaticMarkup(
      <PaperPanel
        {...baseProps}
        mode="forward"
        window={forwardWindow}
        track={[run]}
        trackExperiments={{ exp_paper: experiment }}
      />,
    );
    expect(html).toContain('2026-01-01 → 2026-03-01');
    expect(html).toContain('Δ vs the latest backtest');
    expect(html).toContain('18.00%');
  });
});
