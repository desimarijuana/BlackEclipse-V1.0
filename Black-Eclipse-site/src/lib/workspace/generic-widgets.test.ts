import { describe, expect, it } from 'vitest';
import { DASHBOARD_WIDGET_IDS } from '@/lib/dashboard/registry';
import { SOURCE_WIDGETS } from './generic-widgets';

// The cross-language contract: this list MUST equal the Python
// `RENDERABLE_COMPONENTS` (`python/harness/ui/catalog.py`). Duplicated here on
// purpose so drift on either side fails a test.
const CONTRACT = [
  'metric-card', 'data-table', 'list',
  'line-chart', 'area-chart', 'bar-chart', 'pie-chart',
  'markdown', 'status-indicator', 'empty-state', 'error-state',
];

describe('generic widget registry parity', () => {
  it('exposes exactly the renderable contract ids', () => {
    expect([...SOURCE_WIDGETS.map((w) => w.id)].sort()).toEqual([...CONTRACT].sort());
  });

  it('every generic id is registered as a host dashboard widget', () => {
    const host = new Set(DASHBOARD_WIDGET_IDS);
    for (const id of CONTRACT) expect(host.has(id), `${id} missing from DASHBOARD_WIDGET_IDS`).toBe(true);
  });
});
