// ─── dashboard ↔ blueprint bridge tests (Phase E) ───────────────────────────
// The reverse sync's correctness hinges on ONE pure property: two layouts that
// differ only in key order compare EQUAL, so a page load never remounts the
// board for nothing. The fetch/publish paths need `window` + the runtime and
// are exercised by the app; the sync decision logic is pinned here.

import { describe, expect, it } from 'vitest';

import { stableLayoutKey } from './dashboard-blueprint';
import type { WorkspaceLayout } from '@/lib/workspace/types';

function layout(): WorkspaceLayout {
  return {
    version: 2,
    sections: [
      {
        id: 'sec_1',
        zone: 'main',
        columns: [
          {
            id: 'col_1',
            weight: 3,
            widgets: [
              { id: 'wid_1', widgetId: 'market-status', height: null, config: { symbol: 'AAPL' } },
            ],
          },
        ],
      },
    ],
  };
}

describe('stableLayoutKey', () => {
  it('is key-order insensitive', () => {
    const a = {
      version: 2,
      sections: [{ id: 's', columns: [{ id: 'c', weight: 3, widgets: [] }] }],
    } as unknown as WorkspaceLayout;
    const b = {
      sections: [{ columns: [{ widgets: [], weight: 3, id: 'c' }], id: 's' }],
      version: 2,
    } as unknown as WorkspaceLayout;
    expect(stableLayoutKey(a)).toBe(stableLayoutKey(b));
  });

  it('distinguishes a real difference (a moved widget is not equal)', () => {
    const base = layout();
    const moved = JSON.parse(JSON.stringify(base)) as WorkspaceLayout;
    moved.sections[0].columns[0].widgets[0] = {
      ...moved.sections[0].columns[0].widgets[0],
      widgetId: 'news',
    };
    expect(stableLayoutKey(base)).not.toBe(stableLayoutKey(moved));
  });

  it('round-trips through JSON unchanged', () => {
    const base = layout();
    const parsed = JSON.parse(JSON.stringify(base)) as WorkspaceLayout;
    expect(stableLayoutKey(parsed)).toBe(stableLayoutKey(base));
  });
});
