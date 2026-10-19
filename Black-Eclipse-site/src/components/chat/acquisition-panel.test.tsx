// ─── AcquisitionPanel SSR tests (Phase 16) ──────────────────────────────────
// The vitest environment is `node` (no DOM), so — like the video/artifact
// panels — the component renders with `react-dom/server`. What matters here:
// the manifest's source / window / rows / completeness / licence / attribution
// are shown, a partial pull is shown PARTIAL with its reason, and a blob that
// does not coerce renders nothing (never a fabricated panel).

import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

import { AcquisitionPanel } from './acquisition-panel';

function render(manifest: unknown): string {
  return renderToStaticMarkup(<AcquisitionPanel manifest={manifest} />);
}

const complete = {
  purpose: 'two years for the watchlist',
  collectedAt: '2026-10-18T12:00:00Z',
  sources: [
    {
      id: 'prices_daily',
      label: 'Daily price history',
      window: { from: '2024-01-02', to: '2024-01-03' },
      rows: 4821,
      file: 'prices_daily.csv',
      complete: true,
      stoppedReason: null,
      licence: 'vendor terms — see attribution',
      attribution: 'Yahoo Finance (unofficial endpoint)',
    },
  ],
};

describe('AcquisitionPanel', () => {
  it('renders nothing for a blob that does not coerce', () => {
    expect(render(undefined)).toBe('');
    expect(render({})).toBe('');
    expect(render({ sources: [] })).toBe('');
  });

  it('shows the complete pull: source, window, rows, licence and attribution', () => {
    const html = render(complete);
    expect(html).toContain('Collected data');
    expect(html).toContain('two years for the watchlist');
    expect(html).toContain('Daily price history');
    expect(html).toContain('2024-01-02');
    expect(html).toContain('2024-01-03');
    expect(html).toContain('4,821');
    expect(html).toContain('Complete');
    expect(html).not.toContain('Partial');
    expect(html).toContain('vendor terms — see attribution');
    expect(html).toContain('Yahoo Finance (unofficial endpoint)');
  });

  it('shows a partial pull as PARTIAL with the stated reason — never as the dataset', () => {
    const html = render({
      ...complete,
      sources: [
        {
          ...complete.sources[0],
          complete: false,
          stoppedReason: 'reached the collection limit (50,000 rows)',
        },
      ],
    });
    expect(html).toContain('Partial');
    expect(html).not.toContain('>Complete<');
    expect(html).toContain('Stopped early: reached the collection limit (50,000 rows)');
  });

  it('renders an unknown row count honestly instead of 0', () => {
    const html = render({ sources: [{ id: 'x', label: 'X', complete: true }] });
    expect(html).toContain('count unavailable');
    expect(html).not.toContain('>0<');
  });
});
