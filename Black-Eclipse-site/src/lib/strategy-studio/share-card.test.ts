import { describe, expect, it } from 'vitest';
import { SHARE_DISCLAIMER, buildShareCardMarkdown } from './share-card';

const base = {
  name: 'EMA trend',
  id: 'ema_trend',
  version: '1.2.0',
  description: 'A trend follower.',
  symbols: ['BTC-USD'],
  timeframe: '1d',
  start: '2024-01-01',
  end: '2026-01-01',
};

describe('share card markdown', () => {
  it('includes the identity, window and metrics', () => {
    const markdown = buildShareCardMarkdown({
      ...base,
      metrics: { total_return: 20.5, sharpe: 1.2, trade_count: 40 },
    });
    expect(markdown).toContain('# EMA trend (v1.2.0)');
    expect(markdown).toContain('A trend follower.');
    expect(markdown).toContain('BTC-USD');
    expect(markdown).toContain('2024-01-01 → 2026-01-01');
    expect(markdown).toContain('| Total return | 20.50% |');
    expect(markdown).toContain('| Trades | 40 |');
    expect(markdown).toContain(SHARE_DISCLAIMER);
  });

  it('includes the grade and every flag', () => {
    const markdown = buildShareCardMarkdown({
      ...base,
      grade: 'B',
      score: 72.4,
      flags: [{ code: 'FEW_TRADES', severity: 'warning', message: 'only 12 trades' }],
    });
    expect(markdown).toContain('Grade **B**');
    expect(markdown).toContain('72/100');
    expect(markdown).toContain('`FEW_TRADES`');
  });

  it('omits sections with no data instead of printing empty tables', () => {
    const markdown = buildShareCardMarkdown({ ...base });
    expect(markdown).not.toContain('## Performance');
    expect(markdown).not.toContain('## Evidence');
    expect(markdown).not.toContain('## Paper');
    expect(markdown).not.toContain('## Link');
  });

  it('includes the paper state and link when present', () => {
    const markdown = buildShareCardMarkdown({
      ...base,
      paper: { state: 'stale', headline: 'Last paper run was 41 days ago' },
      link: 'https://example.test/?tab=strategy-studio&strategy=ema_trend',
    });
    expect(markdown).toContain('**stale**');
    expect(markdown).toContain('41 days');
    expect(markdown).toContain('## Link');
  });
});
