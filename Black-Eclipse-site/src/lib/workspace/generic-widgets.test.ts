import { describe, expect, it } from 'vitest';
import { DASHBOARD_WIDGET_IDS } from '@/lib/dashboard/registry';
import { SOURCE_WIDGETS } from './generic-widgets';

const SOURCE_CONTRACT = [
  'metric-card', 'data-table', 'list',
  'line-chart', 'area-chart', 'bar-chart', 'pie-chart',
  'markdown', 'status-indicator', 'empty-state', 'error-state',
];

const RENDERABLE_CONTRACT = [...SOURCE_CONTRACT, 'clock'];

describe('generic widget registry parity', () => {
  it('exposes exactly the source-renderable contract ids', () => {
    expect([...SOURCE_WIDGETS.map((w) => w.id)].sort()).toEqual([...SOURCE_CONTRACT].sort());
  });

  it('every renderable id is registered as a host dashboard widget', () => {
    const host = new Set(DASHBOARD_WIDGET_IDS);
    for (const id of RENDERABLE_CONTRACT) expect(host.has(id), `${id} missing from DASHBOARD_WIDGET_IDS`).toBe(true);
  });
});
