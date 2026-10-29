import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ResearchStudio } from './research-studio';
import type { StrategyRecord } from '@/lib/backtest/backtest-client';

const selected: StrategyRecord = {
  id: 'ema_trend',
  name: 'EMA trend',
  latestVersion: '1.0.0',
  version: '1.0.0',
  archived: false,
  spec: {
    strategy: { id: 'ema_trend', name: 'EMA trend', version: '1.0.0' },
    universe: { symbols: ['BTC-USD'] },
    timeframes: { primary: '1d' },
    indicators: [
      { id: 'ema_fast', type: 'ema', params: { period: 20 } },
      { id: 'ema_slow', type: 'ema', params: { period: 50 } },
      { id: 'atr', type: 'atr', params: { period: 14 } },
    ],
    rules: {
      entry: { long: { type: 'group', combine: 'all', conditions: [] } },
      exit: { stop_loss: { type: 'atr', value: 2 }, take_profit: { type: 'risk_reward', value: 3 } },
    },
    position_sizing: { type: 'percent_equity', value: 50 },
  },
};

const noop = async () => null;

describe('ResearchStudio', () => {
  it('derives the tunable parameters from the spec instead of asking for JSON', () => {
    const html = renderToStaticMarkup(
      <ResearchStudio
        selected={selected}
        symbols={['BTC-USD']}
        start="2024-01-01"
        end="2026-01-01"
        initialCapital={100000}
        running={false}
        progress={null}
        onRun={noop}
        onError={() => undefined}
      />,
    );
    expect(html).toContain('ema_fast.period');
    expect(html).toContain('ema_slow.period');
    expect(html).toContain('exit.stop_loss.value');
    expect(html).not.toContain('paramSpace');
  });

  it('offers the one-button suite and the individual runs', () => {
    const html = renderToStaticMarkup(
      <ResearchStudio
        selected={selected}
        symbols={[]}
        start=""
        end=""
        initialCapital={100000}
        running={false}
        onRun={noop}
        onError={() => undefined}
      />,
    );
    expect(html).toContain('Run the robustness suite');
    expect(html).toContain('Walk-forward');
    expect(html).toContain('Monte Carlo');
    expect(html).toContain('Robustness');
    expect(html).toContain('Research plan');
  });
});
