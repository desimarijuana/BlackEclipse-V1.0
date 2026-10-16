// ── Generic data-widget render tests (server-rendered) ───────────────────────
// Renders the REAL widgets with `react-dom/server` (the repo's node-env render
// pattern) so we prove the last hop: resolved source data actually becomes table
// rows / a metric value on screen. `useDataSource` is stubbed with a resolved
// entry (the live fetch is covered by data-source.test.ts).

import { describe, it, expect, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { WidgetPlacement } from '@/lib/workspace/types';

vi.mock('@/lib/workspace/data-source', () => ({
  useDataSource: (source?: string | null) => ({
    source: 'LIVE',
    updatedAt: 1,
    data: source && source.includes('totalValue')
      ? { kind: 'value', value: '1550', label: 'totalValue', provenance: 'LIVE' }
      : {
          kind: 'rows',
          provenance: 'LIVE',
          rows: [{ symbol: 'AAPL', quantity: '10', marketValueBase: '1550' }],
          columns: [
            { key: 'symbol', label: 'Symbol' },
            { key: 'quantity', label: 'Qty', align: 'right' },
            { key: 'marketValueBase', label: 'Value', align: 'right' },
          ],
        },
  }),
}));

import { DataTableWidget, MetricCardWidget } from './generic-widgets';

function placement(widgetId: string, config: Record<string, unknown>): WidgetPlacement {
  return { id: 'w1', widgetId, height: null, config } as WidgetPlacement;
}

describe('DataTableWidget', () => {
  it('renders resolved rows and their columns with provenance', () => {
    const html = renderToStaticMarkup(
      <DataTableWidget placement={placement('data-table', { source: 'portfolio:pf_x:positions' })} />,
    );
    expect(html).toContain('AAPL');
    expect(html).toContain('Symbol');
    expect(html).toContain('Value');
    expect(html).toContain('LIVE');
  });
});

describe('MetricCardWidget', () => {
  it('renders a resolved scalar with its label', () => {
    const html = renderToStaticMarkup(
      <MetricCardWidget placement={placement('metric-card', { metric: 'portfolio:pf_x:summary.totalValue', label: 'Total Value' })} />,
    );
    expect(html).toContain('Total Value');
    expect(html).toContain('1,550');
  });
});
