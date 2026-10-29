import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ShareCard } from './share-card';
import { SHARE_DISCLAIMER } from '@/lib/strategy-studio/share-card';

const input = {
  name: 'EMA trend',
  id: 'ema_trend',
  version: '1.2.0',
  description: 'A trend follower.',
  symbols: ['BTC-USD'],
  timeframe: '1d',
  start: '2024-01-01',
  end: '2026-01-01',
  metrics: { total_return: 20.5, sharpe: 1.2, trade_count: 40 },
  grade: 'B',
  score: 72,
  flags: [{ code: 'FEW_TRADES', severity: 'warning', message: 'only 12 trades' }],
  paper: { state: 'stale', headline: 'Last paper run was 41 days ago' },
  link: 'https://example.test/?tab=strategy-studio&strategy=ema_trend',
};

describe('ShareCard', () => {
  it('renders the identity, metrics, grade and paper state', () => {
    const html = renderToStaticMarkup(<ShareCard input={input} />);
    expect(html).toContain('Share card');
    expect(html).toContain('EMA trend');
    expect(html).toContain('grade B');
    expect(html).toContain('paper stale');
    expect(html).toContain('Copy Markdown');
    expect(html).toContain('Copy link');
    expect(html).toContain(SHARE_DISCLAIMER);
  });

  it('does not offer a link when there is none', () => {
    const html = renderToStaticMarkup(<ShareCard input={{ ...input, link: null }} />);
    expect(html).not.toContain('Copy link');
  });
});
