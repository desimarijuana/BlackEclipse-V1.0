import { describe, expect, it } from 'vitest';
import type { WorkspaceLayout as WireLayout } from '@/lib/harness/ui-client';
import type { WorkspaceLayout as KernelLayout } from '@/lib/workspace/types';
import { blueprintLayoutToKernel, kernelLayoutToWire, pageStorageKey } from './live-page';

const wire: WireLayout = {
  version: 2,
  sections: [
    {
      id: 's1',
      zone: 'left',
      columns: [
        {
          id: 'c1',
          weight: 2,
          widgets: [
            { id: 'w1', widgetId: 'watchlist', height: null, minHeight: 200, config: { market: 'US' } },
            { id: 'w2', widgetId: 'indices', height: 320, defaultHeight: 300, hidden: true },
          ],
        },
      ],
    },
  ],
  hiddenZones: ['right'],
  zoneWidths: { left: 260 },
};

describe('pageStorageKey', () => {
  it('is derived from the blueprint id', () => {
    expect(pageStorageKey('uibp_1')).toBe('be_ui_page_uibp_1');
  });
});

describe('blueprintLayoutToKernel', () => {
  it('maps wire fields to the kernel shape with sane defaults', () => {
    const kernel = blueprintLayoutToKernel(wire);
    expect(kernel.version).toBe(2);
    expect(kernel.sections[0].zone).toBe('left');
    const [w1, w2] = kernel.sections[0].columns[0].widgets;
    expect(w1).toMatchObject({ id: 'w1', widgetId: 'watchlist', height: null, minHeight: 200, config: { market: 'US' } });
    expect(w1.height).toBeNull();
    expect(w2).toMatchObject({ id: 'w2', widgetId: 'indices', height: 320, defaultHeight: 300, hidden: true });
    expect(kernel.hiddenZones).toEqual(['right']);
    expect(kernel.zoneWidths).toEqual({ left: 260 });
  });

  it('coerces a null/absent layout to an empty v2 board', () => {
    const kernel = blueprintLayoutToKernel(null);
    expect(kernel).toEqual({ version: 2, sections: [] });
  });

  it('defaults a non-positive column weight to 3', () => {
    const kernel = blueprintLayoutToKernel({
      ...wire,
      sections: [{ id: 's', columns: [{ id: 'c', weight: 0, widgets: [] }] }],
    } as WireLayout);
    expect(kernel.sections[0].columns[0].weight).toBe(3);
  });
});

describe('kernelLayoutToWire', () => {
  it('round-trips through the kernel form', () => {
    const kernel = blueprintLayoutToKernel(wire);
    const back = kernelLayoutToWire(kernel);
    expect(back.sections[0].columns[0].widgets[0]).toMatchObject({
      id: 'w1', widgetId: 'watchlist', height: null, minHeight: 200, config: { market: 'US' },
    });
    expect(back.hiddenZones).toEqual(['right']);
  });

  it('materializes an omitted zone as main and nulls absent config', () => {
    const kernel: KernelLayout = {
      version: 2,
      sections: [{ id: 's', columns: [{ id: 'c', weight: 3, widgets: [{ id: 'w', widgetId: 'x', height: null }] }] }],
    };
    const out = kernelLayoutToWire(kernel);
    expect(out.sections[0].zone).toBe('main');
    expect(out.sections[0].columns[0].widgets[0].config).toBeNull();
    expect(out.hiddenZones).toBeNull();
  });
});
